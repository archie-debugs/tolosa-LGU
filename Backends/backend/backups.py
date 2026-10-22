"""Where backups go, and how the latest ones went (read from the backup.log that scripts/backup.py writes)."""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "").strip() or PROJECT_ROOT.parent / "sb_tolosa_backups")
BACKUP_MIRROR_DIR = Path(os.getenv("BACKUP_MIRROR_DIR").strip()) if os.getenv("BACKUP_MIRROR_DIR", "").strip() else None

# A backup older than this is reported as overdue; a day plus slack for a run that started late.
MAX_AGE = timedelta(hours=26)

LOG_LINE = re.compile(r"^(\S+) (OK|FAILED|MIRROR OK|MIRROR FAILED) ([^:]+)(?:: (.*))?$")


def _read_log(dest):
    try:
        lines = (Path(dest) / "backup.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        match = LOG_LINE.match(line.strip())
        if not match:
            continue
        try:
            at = datetime.fromisoformat(match.group(1))
        except ValueError:
            continue
        entries.append({"at": at, "result": match.group(2), "folder": match.group(3), "message": match.group(4) or ""})
    return entries


def backup_health(dest=None, *, mirror=None, now=None):
    """The `backup` component of /system-health: warning unless the last run worked, is recent and was mirrored."""
    dest = Path(dest) if dest is not None else BACKUP_DIR
    mirror = mirror if mirror is not None else BACKUP_MIRROR_DIR
    now = now or datetime.now()
    entries = _read_log(dest)
    runs = [entry for entry in entries if entry["result"] in {"OK", "FAILED"}]
    copies = [entry for entry in entries if entry["result"].startswith("MIRROR")]
    last_ok = next((entry for entry in reversed(runs) if entry["result"] == "OK"), None)

    problems = []
    if last_ok is None:
        problems.append(f"No backup has been recorded in {dest}.")
    elif now - last_ok["at"] > MAX_AGE:
        problems.append(f"The last backup is more than a day old ({last_ok['at']:%Y-%m-%d %H:%M}).")
    if runs and runs[-1]["result"] == "FAILED":
        problems.append(f"The last backup failed: {runs[-1]['message']}")
    if not mirror:
        problems.append("No off-machine copy is set up (BACKUP_MIRROR_DIR).")
    elif copies and copies[-1]["result"] == "MIRROR FAILED":
        problems.append(f"Copying the last backup to {mirror} failed: {copies[-1]['message']}")

    return {
        "status": "warning" if problems else "operational",
        "detail": {
            # backup.log is in local time; send the offset so clients don't read it as UTC.
            "last_backup_at": last_ok["at"].astimezone().isoformat(timespec="seconds") if last_ok else None,
            "last_backup_folder": last_ok["folder"] if last_ok else None,
            "backup_dir": str(dest),
            "mirror_dir": str(mirror) if mirror else None,
            "problems": problems,
        },
    }
