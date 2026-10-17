"""Copy attachments out of the legacy temp-folder storage into DOCUMENT_STORAGE_DIR.

Attachments used to be stored under the OS temp folder, which Windows may clean
automatically. This copies each such file into the configured document storage
folder, verifies the copy, and repoints Attachment.stored_path. Originals are left
in place so they can be deleted by hand once the migration is confirmed.

Usage (from the project root):
    python scripts/migrate_attachment_storage.py          # dry run, changes nothing
    python scripts/migrate_attachment_storage.py --apply  # copy files and update the database
"""

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Backends.backend import models  # noqa: E402
from Backends.backend.core import LEGACY_UPLOAD_DIR, UPLOAD_DIR  # noqa: E402
from Backends.backend.database import SessionLocal  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="copy files and update stored paths")
    args = parser.parse_args()

    legacy_root = Path(LEGACY_UPLOAD_DIR).resolve()
    target_root = Path(UPLOAD_DIR).resolve()
    if legacy_root == target_root:
        print("DOCUMENT_STORAGE_DIR points at the legacy folder; nothing to migrate.")
        return 0
    print(f"Legacy folder: {legacy_root}")
    print(f"Target folder: {target_root}")

    db = SessionLocal()
    moved = skipped = missing = 0
    try:
        for attachment in db.query(models.Attachment).order_by(models.Attachment.id).all():
            if not attachment.stored_path:
                continue
            source = Path(attachment.stored_path).resolve()
            if legacy_root not in source.parents:
                continue
            if not source.is_file():
                print(f"MISSING  attachment {attachment.id}: file no longer exists")
                missing += 1
                continue
            destination = target_root / source.relative_to(legacy_root)
            if destination.exists():
                print(f"SKIP     attachment {attachment.id}: destination already exists")
                skipped += 1
                continue
            print(f"{'COPY' if args.apply else 'WOULD COPY'}     attachment {attachment.id}: {source.name}")
            if not args.apply:
                moved += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if _sha256(source) != _sha256(destination):
                destination.unlink()
                raise RuntimeError(f"Copy verification failed for attachment {attachment.id}")
            attachment.stored_path = str(destination)
            db.commit()
            moved += 1
    finally:
        db.close()

    verb = "Copied" if args.apply else "Would copy"
    print(f"{verb} {moved}, skipped {skipped}, missing {missing}.")
    if not args.apply and moved:
        print("Run again with --apply to perform the migration.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
