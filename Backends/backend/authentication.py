"""The single path from a bearer access token to an authenticated user.

Every service and every role- or permission-specific dependency builds on
`authenticate_access_token`, so the checks (valid token, existing and active user, live
registered session) cannot drift apart between them again.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models
from .auth_jwt import decode_access_token
from .database import get_db

# auto_error=False so a missing token gets the same 401 as every other failure below.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class AccountNotAuthenticated(HTTPException):
    """No usable account: the token is missing, or its user is unknown or inactive.

    Kept distinct from token and session failures so user-management routes can keep
    answering these with 403, as they did before authentication was shared.
    """

    def __init__(self, detail: str):
        super().__init__(status_code=401, detail=detail)


def validate_registered_session(db: Session, payload: dict, user: models.User) -> None:
    # Every access token must belong to a registered session, so logout, deactivation and
    # administrator revocation always take effect.
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Session is no longer active")
    session = db.query(models.UserSession).filter(
        models.UserSession.session_id == session_id,
        models.UserSession.user_id == user.id,
    ).first()
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at and session.expires_at.tzinfo is None else (session.expires_at if session else None)
    if not session or session.revoked_at or not expires_at or expires_at <= now:
        raise HTTPException(status_code=401, detail="Session is no longer active")
    session.last_activity = now


def ensure_active_user(user: models.User | None) -> models.User:
    if not user:
        raise AccountNotAuthenticated("User not found")
    if not getattr(user, "is_active", False) or getattr(user, "status", None) != "Active":
        raise AccountNotAuthenticated("User no longer active")
    return user


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def authenticate_access_token(db: Session, token: str | None) -> models.User:
    """Return the active user behind `token`, or raise 401."""
    if not token:
        raise AccountNotAuthenticated("Authentication required")
    payload = decode_access_token(token)
    username = payload.get("sub")
    if not username:
        raise AccountNotAuthenticated("Invalid token payload")
    user = ensure_active_user(db.query(models.User).filter(models.User.username == username).first())
    validate_registered_session(db, payload, user)
    return user


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    return authenticate_access_token(db, token)


def get_current_user_for_user_management(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """Like get_current_user, but answers a missing, unknown or inactive account with 403."""
    try:
        return authenticate_access_token(db, token)
    except AccountNotAuthenticated as exc:
        raise HTTPException(status_code=403, detail="Authenticated user required") from exc
