import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import login_lockout, models, two_step
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

START = 1_800_000_000.0


@pytest.fixture
def clock(monkeypatch):
    now = {"t": START}
    monkeypatch.setattr(two_step, "clock", lambda: now["t"])

    def advance(seconds=two_step.STEP_SECONDS):
        now["t"] += seconds

    return advance


@pytest.fixture
def client():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add_all([
            models.User(username="admin", hashed_password=get_password_hash("pw123"), role="Super Administrator",
                        permissions="['*']", status="Active", is_active=True),
            models.User(username="clerk", hashed_password=get_password_hash("pw123"), role="Employee",
                        permissions="['view_documents']", status="Active", is_active=True),
        ])
        db.commit()
    return TestClient(main.app)


def login(client, username="admin", password="pw123", code=None):
    data = {"username": username, "password": password}
    if code is not None:
        data["code"] = code
    return client.post("/auth/login", data=data)


def auth(client, **kwargs):
    response = login(client, **kwargs)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def now_code(secret):
    return two_step.code_at(secret, two_step.current_step())


def turn_on(client, clock):
    headers = auth(client)
    setup = client.post("/auth/two-step/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = client.post("/auth/two-step/enable", headers=headers, json={"code": now_code(secret)})
    assert enabled.status_code == 200, enabled.text
    clock()
    return secret, enabled.json()["recovery_codes"], headers


def audit_actions(username):
    with SessionLocal() as db:
        return [row.action for row in db.query(models.AuditLog).filter_by(target_id=username).order_by(models.AuditLog.id)]


def test_codes_match_the_rfc_6238_test_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
    assert two_step.code_at(secret, 59 // 30) == "287082"
    assert two_step.code_at(secret, 1111111109 // 30) == "081804"
    assert two_step.code_at(secret, 2000000000 // 30) == "279037"


def test_setup_gives_a_qr_and_turning_on_needs_a_right_code(client, clock):
    headers = auth(client)
    body = client.post("/auth/two-step/setup", headers=headers).json()
    assert body["uri"].startswith("otpauth://totp/LGU%20Tolosa%3Aadmin?secret=" + body["secret"])
    assert body["qr_png_base64"]

    wrong = client.post("/auth/two-step/enable", headers=headers, json={"code": "000000" if now_code(body["secret"]) != "000000" else "111111"})
    assert wrong.status_code == 400
    assert client.get("/auth/me", headers=headers).json()["two_step_enabled"] is False

    right = client.post("/auth/two-step/enable", headers=headers, json={"code": now_code(body["secret"])})
    assert right.status_code == 200
    codes = right.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    me = client.get("/auth/me", headers=headers).json()
    assert me["two_step_enabled"] is True
    assert me["two_step_recovery_codes_left"] == 10
    assert "TWO_STEP_ENABLED" in audit_actions("admin")


def test_login_asks_for_the_code_then_accepts_it_once(client, clock):
    secret, _, _ = turn_on(client, clock)

    asked = login(client)
    assert asked.status_code == 401
    assert asked.headers["X-Two-Step"] == "required"
    assert asked.json()["detail"] == "Enter the 6-digit code from your authenticator app."

    code = now_code(secret)
    assert login(client, code=code).status_code == 200
    replay = login(client, code=code)
    assert replay.status_code == 401
    assert replay.headers["X-Two-Step"] == "required"

    clock()
    assert login(client, code=now_code(secret)).status_code == 200
    assert "FAILED_LOGIN" not in audit_actions("admin")[:audit_actions("admin").index("USER_LOGIN")]


def test_a_wrong_code_counts_toward_the_lockout(client, clock):
    secret, _, _ = turn_on(client, clock)
    wrong = "000000" if now_code(secret) != "000000" else "111111"

    for _ in range(login_lockout.LOGIN_MAX_FAILURES):
        response = login(client, code=wrong)
        assert response.status_code == 401
        assert response.json()["detail"] == "That code is not right. Check your authenticator app and try again."

    assert login(client, code=now_code(secret)).status_code == 429


def test_a_wrong_password_never_reaches_the_code_step(client, clock):
    turn_on(client, clock)
    response = login(client, password="wrong")
    assert response.status_code == 401
    assert "X-Two-Step" not in response.headers


def test_each_recovery_code_works_once(client, clock):
    _, codes, headers = turn_on(client, clock)

    assert login(client, code=codes[0].upper()).status_code == 200
    assert login(client, code=codes[0]).status_code == 401
    assert client.get("/auth/me", headers=headers).json()["two_step_recovery_codes_left"] == 9
    assert "TWO_STEP_RECOVERY_CODE_USED" in audit_actions("admin")


def test_turning_off_needs_the_password_and_a_code(client, clock):
    secret, _, headers = turn_on(client, clock)

    bad_password = client.post("/auth/two-step/disable", headers=headers, json={"password": "nope", "code": now_code(secret)})
    assert bad_password.status_code == 400
    bad_code = client.post("/auth/two-step/disable", headers=headers, json={"password": "pw123", "code": "12"})
    assert bad_code.status_code == 400

    done = client.post("/auth/two-step/disable", headers=headers, json={"password": "pw123", "code": now_code(secret)})
    assert done.status_code == 200
    assert login(client).status_code == 200
    assert client.get("/auth/me", headers=headers).json()["two_step_enabled"] is False
    assert "TWO_STEP_DISABLED" in audit_actions("admin")


def test_only_super_admins_can_set_it_up(client, clock):
    headers = auth(client, username="clerk")
    assert client.post("/auth/two-step/setup", headers=headers).status_code == 403
    assert client.post("/auth/two-step/enable", headers=headers, json={"code": "123456"}).status_code == 403
    assert login(client, username="clerk").status_code == 200


def test_setup_is_refused_while_it_is_already_on(client, clock):
    _, _, headers = turn_on(client, clock)
    assert client.post("/auth/two-step/setup", headers=headers).status_code == 400


def test_the_server_script_turns_it_off_for_a_locked_out_admin(client, clock):
    turn_on(client, clock)
    path = Path(__file__).resolve().parents[1] / "scripts" / "reset_two_step.py"
    spec = importlib.util.spec_from_file_location("reset_two_step", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    assert script.reset("admin") is True
    assert script.reset("nobody") is False
    assert login(client).status_code == 200
    assert "TWO_STEP_RESET" in audit_actions("admin")
