"""Your own profile picture, and proving your email is yours by signing in to Google with it.

Google: POST /auth/me/email/google returns Google's sign-in link; Google sends the browser back to
GET /auth/google/callback, which asks Google (server to server, with the client secret) which account
signed in. The email is verified when that Google account's email is the one on the profile.
Setup: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET from a Google Cloud OAuth client ("Web application"),
whose authorized redirect URI is GOOGLE_REDIRECT_URI (default: PUBLIC_BASE_URL + /auth/google/callback).
"""

import base64
import html
import io
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..auth_jwt import ALGORITHM, SECRET_KEY
from ..authentication import get_current_user
from ..core import is_temporary_email, record_audit_log
from ..database import get_db
from .auth import _my_account
from .documents import AVATAR_EXTENSIONS, TEMP_UPLOAD_DIR, _public_base_url, _remove_staged, _tmp_meta

router = APIRouter()

AVATAR_PIXELS = 256
AVATAR_MAX_BYTES = 10 * 1024 * 1024
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
STATE_MINUTES = 15


class AvatarUpload(BaseModel):
    tmp_name: str = Field(..., min_length=1)


@router.post("/auth/me/avatar")
def set_my_avatar(payload: AvatarUpload, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Your profile picture, from a JPG or PNG you staged with purpose "avatar": cropped square, 256 pixels."""
    safe_name = os.path.basename(payload.tmp_name)
    tmp_path = os.path.join(TEMP_UPLOAD_DIR, safe_name)
    meta = _tmp_meta(safe_name)
    # Only the person who uploaded the file may use it.
    if not safe_name or not os.path.isfile(tmp_path) or meta.get("username") != current_user.username:
        raise HTTPException(status_code=404, detail="Uploaded picture not found. Upload it again.")
    if os.path.splitext(safe_name.lower())[1] not in AVATAR_EXTENSIONS or os.path.getsize(tmp_path) > AVATAR_MAX_BYTES:
        _remove_staged([tmp_path, f"{tmp_path}.meta.json"])
        raise HTTPException(status_code=400, detail="Use a JPG or PNG picture of up to 10 MB.")
    try:
        with Image.open(tmp_path) as picture:
            picture = ImageOps.fit(ImageOps.exif_transpose(picture).convert("RGB"), (AVATAR_PIXELS, AVATAR_PIXELS))
            out = io.BytesIO()
            picture.save(out, "JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=400, detail="That file can't be read as a picture. Use a JPG or PNG.") from error
    finally:
        _remove_staged([tmp_path, f"{tmp_path}.meta.json"])
    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    user.avatar = base64.b64encode(out.getvalue()).decode("ascii")
    record_audit_log(db, actor=user.username, action="PROFILE_PICTURE_CHANGED", target_type="User", target_id=str(user.id),
                     details=f"{user.username} changed their profile picture", commit=False)
    db.commit()
    db.refresh(user)
    return _my_account(user)


@router.delete("/auth/me/avatar")
def remove_my_avatar(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user.id).one()
    if user.avatar:
        user.avatar = None
        record_audit_log(db, actor=user.username, action="PROFILE_PICTURE_REMOVED", target_type="User", target_id=str(user.id),
                         details=f"{user.username} removed their profile picture", commit=False)
        db.commit()
        db.refresh(user)
    return _my_account(user)


def _google():
    """(client id, client secret, redirect URI), or None when Google verification is not set up."""
    client_id, secret = os.getenv("GOOGLE_CLIENT_ID", "").strip(), os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        return None
    return client_id, secret, os.getenv("GOOGLE_REDIRECT_URI", "").strip() or f"{_public_base_url()}/auth/google/callback"


@router.post("/auth/me/email/google")
def start_google_verification(current_user: models.User = Depends(get_current_user)):
    """The Google sign-in link that verifies your email; it works for STATE_MINUTES minutes."""
    google = _google()
    if google is None:
        raise HTTPException(status_code=503, detail="Verifying with Google isn't set up on this server yet. Tell a Super Administrator.")
    if is_temporary_email(current_user.email) or not current_user.email:
        raise HTTPException(status_code=400, detail="First change the temporary email to your own Gmail or Google address (Edit profile).")
    if current_user.email_verified_at is not None:
        raise HTTPException(status_code=400, detail="Your email is already verified.")
    client_id, _, redirect_uri = google
    state = jwt.encode({
        "purpose": "verify_email", "uid": current_user.id, "email": current_user.email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=STATE_MINUTES),
    }, SECRET_KEY, algorithm=ALGORITHM)
    query = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": "openid email",
             "state": state, "login_hint": current_user.email, "prompt": "select_account"}
    return {"url": f"{GOOGLE_AUTH_URL}?{urlencode(query)}"}


@router.get("/auth/google/callback", response_class=HTMLResponse)
def finish_google_verification(code: str | None = Query(default=None), state: str | None = Query(default=None),
                               error: str | None = Query(default=None), db: Session = Depends(get_db)):
    """Where Google sends the browser back. Answers with a small page saying whether the email is now verified."""
    google = _google()
    try:
        claims = jwt.decode(state or "", SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return _page(False, "This verification link has expired. Go back to Settings and press Verify with Google again.")
    if claims.get("purpose") != "verify_email" or google is None:
        return _page(False, "This verification link isn't valid. Go back to Settings and try again.")
    if error or not code:
        return _page(False, "Google sign-in was cancelled. Go back to Settings to try again.")
    user = db.query(models.User).filter(models.User.id == claims.get("uid")).first()
    if user is None or user.email != claims.get("email"):
        return _page(False, "Your email changed after you started. Go back to Settings and verify the new one.")
    client_id, secret, redirect_uri = google
    try:
        response = requests.post(GOOGLE_TOKEN_URL, timeout=10, data={
            "code": code, "client_id": client_id, "client_secret": secret, "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        })
        response.raise_for_status()
        # Straight from Google's token endpoint over TLS, so its signature needs no check (OpenID Connect Core 3.1.3.7).
        account = jwt.decode(response.json()["id_token"], options={"verify_signature": False})
    except (requests.RequestException, KeyError, ValueError, jwt.InvalidTokenError):
        return _page(False, "Google couldn't be reached to confirm your account. Try again in a moment.")
    if (account.get("aud") != client_id or account.get("iss") not in GOOGLE_ISSUERS
            or float(account.get("exp") or 0) < datetime.now(timezone.utc).timestamp()):
        return _page(False, "Google's answer couldn't be confirmed. Try again.")
    google_email = str(account.get("email") or "")
    if not account.get("email_verified") or google_email.lower() != (user.email or "").lower():
        return _page(False, f"You signed in to Google as {google_email or 'another account'}, not {user.email}. "
                            "Sign in with the Google account for that email, or change your email in Settings.")
    user.email_verified_at = datetime.now(timezone.utc)
    record_audit_log(db, actor=user.username, action="EMAIL_VERIFIED", target_type="User", target_id=str(user.id),
                     details=f"{user.username} verified {user.email} with Google", commit=False)
    db.commit()
    return _page(True, f"{user.email} is verified. You can close this tab and go back to the system.")


PRIVACY = [
    "This system belongs to the Sangguniang Bayan of the Municipality of Tolosa and is used by its staff to track legislative documents.",
    "When you press Verify with Google, Google tells the system the email address of the Google account you signed in with. "
    "The system only checks that it matches the email on your profile and records the time it was verified. "
    "It asks for nothing else from your Google account, and keeps no Google password or token.",
    "Your name, username, email, profile picture and sign-in activity are kept to run your account and the audit log, "
    "are seen only by the system's administrators, and are never sold or shared.",
    "Questions or requests to correct or remove your information: contact the SB Secretariat of the Municipality of Tolosa.",
]


@router.get("/privacy", tags=["public"], response_class=HTMLResponse)
def privacy_policy():
    """The privacy policy Google's sign-in screen links to."""
    return _html("Privacy Policy", "#0c4279", PRIVACY)


def _page(ok: bool, message: str) -> HTMLResponse:
    """The page Google's redirect lands on."""
    color, title = ("#15803d", "Email verified") if ok else ("#b91c1c", "Not verified")
    return _html(title, color, [message])


def _html(title: str, color: str, paragraphs: list[str]) -> HTMLResponse:
    """A small standalone page; its own CSP lets just its one inline style run."""
    nonce = secrets.token_urlsafe(16)
    text = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style nonce="{nonce}">
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#eef3fb;font-family:Segoe UI,Roboto,Arial,sans-serif;color:#0f2a4a}}
main{{background:#fff;border-radius:18px;padding:36px 32px;max-width:440px;margin:16px;box-shadow:0 10px 30px rgba(12,66,121,.12);text-align:center}}
h1{{color:{color};font-size:24px;margin:0 0 12px}}p{{font-size:15px;line-height:1.6;margin:0 0 10px}}
</style></head><body><main><h1>{title}</h1>{text}</main></body></html>"""
    return HTMLResponse(body, headers={"Content-Security-Policy": f"default-src 'none'; style-src 'nonce-{nonce}'"})
