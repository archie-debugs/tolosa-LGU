import importlib
import os


def test_default_access_token_expiration_is_reasonable():
    os.environ.pop("JWT_EXP_MINUTES", None)
    os.environ["JWT_SECRET_KEY"] = "test-secret-key"
    import Backends.backend.auth_jwt as auth_jwt

    importlib.reload(auth_jwt)

    assert auth_jwt.ACCESS_TOKEN_EXPIRE_MINUTES >= 60
