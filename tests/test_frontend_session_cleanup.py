import importlib.util
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "frontend" / "frontend_admin" / "app.py"
SPEC = importlib.util.spec_from_file_location("frontend_admin_app", APP_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_clear_stale_session_state_resets_auth_state():
    state = {
        "current_user": "a",
        "current_user_role": "Super Administrator",
        "current_user_permissions": ["*"],
        "runtime_token": "expired-token",
        "refresh_token": "expired-refresh",
    }

    cleared = MODULE.clear_stale_session_state(state)

    assert cleared["current_user"] is None
    assert cleared["current_user_role"] is None
    assert cleared["current_user_permissions"] == []
    assert cleared["runtime_token"] is None
    assert cleared["refresh_token"] is None
