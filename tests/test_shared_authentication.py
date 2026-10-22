import inspect as pyinspect
import os

from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import authentication, models
from Backends.backend.core import TEMP_UPLOAD_DIR, get_password_hash
from Backends.backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.add(models.User(
            username="registrar",
            hashed_password=get_password_hash("pw123"),
            role="Employee",
            permissions="['register_documents']",
            status="Active",
            is_active=True,
        ))
        db.commit()


def login_token(client):
    response = client.post("/auth/login", data={"username": "registrar", "password": "pw123"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def upload(client, token, via):
    url = "/documents/uploads/tmp/tmp_shared_auth.pdf"
    if via == "query":
        return client.put(f"{url}?token={token}", content=b"%PDF-1.4")
    return client.put(url, content=b"%PDF-1.4", headers={"Authorization": f"Bearer {token}"})


def test_upload_accepts_a_live_session():
    for via in ("header", "query"):
        reset_db()
        client = TestClient(main.app)

        response = upload(client, login_token(client), via)
        uploaded = os.path.join(TEMP_UPLOAD_DIR, "tmp_shared_auth.pdf")
        if os.path.exists(uploaded):
            os.remove(uploaded)

        assert response.status_code == 200, (via, response.text)


def test_upload_rejects_a_token_whose_session_was_revoked():
    for via in ("header", "query"):
        reset_db()
        client = TestClient(main.app)
        token = login_token(client)
        with SessionLocal() as db:
            for session in db.query(models.UserSession).all():
                session.revoked_at = session.created_at
            db.commit()

        assert upload(client, token, via).status_code == 401, via


def test_upload_rejects_a_deactivated_user():
    for via in ("header", "query"):
        reset_db()
        client = TestClient(main.app)
        token = login_token(client)
        with SessionLocal() as db:
            user = db.query(models.User).filter_by(username="registrar").one()
            user.is_active = False
            user.status = "Inactive"
            db.commit()

        assert upload(client, token, via).status_code == 401, via


def test_no_service_decodes_access_tokens_outside_the_shared_module():
    import Backends.SBmem_backend.main as sb_member_main
    from Backends.backend import core
    from Backends.backend.routes import analytics, audit, documents, offices

    for module in (core, sb_member_main, analytics, audit, documents, offices):
        source = pyinspect.getsource(module)
        assert "decode_access_token(" not in source, module.__name__
        assert "jwt.decode(" not in source, module.__name__
    assert "decode_access_token(" in pyinspect.getsource(authentication)
