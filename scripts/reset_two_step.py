"""Turn off two-step login for a user who lost their phone and their recovery codes.

Run on the server, which needs access to the database in .env:
    python scripts/reset_two_step.py <username>
They can then log in with their password alone and turn it on again from My Account.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from Backends.backend import models  # noqa: E402
from Backends.backend.core import record_audit_log  # noqa: E402
from Backends.backend.database import SessionLocal  # noqa: E402


def reset(username):
    """True if `username` exists; their two-step login is then off."""
    with SessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            return False
        user.totp_secret = user.totp_pending_secret = user.totp_enabled_at = None
        user.totp_last_step = user.totp_recovery_codes = None
        db.commit()
        record_audit_log(db, actor="System", action="TWO_STEP_RESET", target_type="Auth", target_id=username,
                         details="Two-step login turned off with scripts/reset_two_step.py")
        return True


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python scripts/reset_two_step.py <username>", file=sys.stderr)
        return 2
    if not reset(args[0]):
        print(f"No user named {args[0]!r}.", file=sys.stderr)
        return 1
    print(f"Two-step login is off for {args[0]}. They can log in with their password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
