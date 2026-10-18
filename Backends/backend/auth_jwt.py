import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import HTTPException, status

load_dotenv()


# Tokens signed with a guessable key can be forged for any user, so there is no fallback.
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is required to sign and verify authentication tokens.")

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS512")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXP_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "7"))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {
        "sub": data.get("sub"),
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": data.get("session_id") or str(uuid.uuid4()),
        "type": "access",
    }
    to_encode.update(data)
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode = {
        "sub": data.get("sub"),
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": data.get("session_id") or str(uuid.uuid4()),
        "type": "refresh",
    }
    to_encode.update(data)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _create_file_token(data: dict, token_type: str, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=2))
    to_encode = {
        "sub": data.get("sub"),
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": str(uuid.uuid4()),
        "type": token_type,
    }
    to_encode.update(data)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_preview_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return _create_file_token(data, "preview", expires_delta)


def create_download_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """A short-lived link token, so the viewer's browser can fetch an attachment itself."""
    return _create_file_token(data, "download", expires_delta)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid") from exc


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")
        return payload
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalid") from exc


def _decode_file_token(token: str, token_type: str) -> dict:
    label = token_type.capitalize()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid {token_type} token type")
        return payload
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"{label} token expired") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"{label} token invalid") from exc


def decode_preview_token(token: str) -> dict:
    return _decode_file_token(token, "preview")


def decode_download_token(token: str) -> dict:
    return _decode_file_token(token, "download")
