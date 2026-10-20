"""Two-step login: 6-digit authenticator-app codes (RFC 6238 TOTP) and one-time recovery codes.

Codes change every 30 seconds. One step either side of now is accepted so a phone clock that is a
little off still works, and a step is never accepted twice for the same user (User.totp_last_step).
"""

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

ISSUER = "LGU Tolosa"
STEP_SECONDS = 30
DIGITS = 6
RECOVERY_CODE_COUNT = 10


def clock():
    return time.time()


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def current_step():
    return int(clock() // STEP_SECONDS)


def code_at(secret, step):
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret, code, last_step=None):
    """The step `code` belongs to, or None if it is wrong or was already used."""
    code = "".join((code or "").split())
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = current_step()
    for step in (now, now - 1, now + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def setup_uri(secret, username):
    label = quote(f"{ISSUER}:{username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={STEP_SECONDS}"


def _hash_recovery_code(code):
    return hashlib.sha256(code.replace("-", "").strip().lower().encode("utf-8")).hexdigest()


def new_recovery_codes():
    """(codes to show once, JSON of their hashes to store)."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(5)
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, json.dumps([_hash_recovery_code(code) for code in codes])


def recovery_codes_left(stored):
    try:
        return len(json.loads(stored or "[]"))
    except ValueError:
        return 0


def use_recovery_code(stored, code):
    """The stored hashes without `code`, or None if `code` is not one of them."""
    try:
        hashes = json.loads(stored or "[]")
    except ValueError:
        return None
    wanted = _hash_recovery_code(code or "")
    for index, value in enumerate(hashes):
        if hmac.compare_digest(value, wanted):
            return json.dumps(hashes[:index] + hashes[index + 1:])
    return None


def looks_like_recovery_code(code):
    return "-" in (code or "") or len("".join((code or "").split())) == 10
