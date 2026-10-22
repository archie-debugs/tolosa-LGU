"""Back up the database and the document storage folder.

Each run writes <dest>/YYYY-MM-DD_HHMM_nightly/ with:
  legi_sys.dump        pg_dump custom-format dump (restore with pg_restore), or a copy of a SQLite file
  documents_storage/   a copy of DOCUMENT_STORAGE_DIR (attachments and QR images)
  manifest.json        when, which database, file counts and the dump's SHA-256

The folder is written as .partial and renamed only when everything succeeded. Afterwards,
*_nightly folders older than --keep-days are removed (the newest is always kept); other
folders, such as manual backups, are never touched. Every run appends a line to backup.log.
With --mirror, the finished folder is also copied there (checked against the manifest's SHA-256)
and the same retention applies to the mirror.

Usage:  python scripts/backup.py [--dest DIR] [--mirror DIR] [--keep-days 14]
Settings come from .env: DATABASE_URL, DOCUMENT_STORAGE_DIR, and optionally BACKUP_DIR,
BACKUP_MIRROR_DIR and PG_DUMP.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NIGHTLY = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_nightly(?:_\d+)?$")


class BackupFailed(Exception):
    pass


def find_pg_dump():
    """PG_DUMP, pg_dump on PATH, or the newest PostgreSQL install under Program Files."""
    configured = os.getenv("PG_DUMP", "").strip()
    if configured:
        return configured
    on_path = shutil.which("pg_dump")
    if on_path:
        return on_path
    def major(path):
        found = re.search(r"PostgreSQL[\\/](\d+)", path)
        return int(found.group(1)) if found else 0

    installs = sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"), key=major)
    return installs[-1] if installs else "pg_dump"


def _log(dest, line):
    dest.mkdir(parents=True, exist_ok=True)
    with open(dest / "backup.log", "a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _new_folder(dest, now):
    base = f"{now.strftime('%Y-%m-%d_%H%M')}_nightly"
    name, n = base, 1
    while (dest / name).exists() or (dest / f"{name}.partial").exists():
        n += 1
        name = f"{base}_{n}"
    return dest / name


def _dump_database(database_url, folder, run, pg_dump):
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        source = Path(url.database or "")
        if not source.is_file():
            raise BackupFailed(f"SQLite database file not found: {source}")
        shutil.copy2(source, folder / source.name)
        return source.stem, folder / source.name
    if url.get_backend_name() != "postgresql":
        raise BackupFailed(f"Unsupported database: {url.get_backend_name()}")
    out = folder / f"{url.database}.dump"
    args = [pg_dump, "--format=custom", "--no-owner", "--file", str(out),
            "--host", url.host or "localhost", "--port", str(url.port or 5432), "--username", url.username or "postgres", url.database]
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    result = run(args, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise BackupFailed(f"pg_dump failed: {(result.stderr or '').strip() or 'exit code ' + str(result.returncode)}")
    return url.database, out


def _remove_old(dest, now, keep_days, keep):
    cutoff = now - timedelta(days=keep_days)
    removed = []
    for path in dest.iterdir():
        match = NIGHTLY.match(path.name)
        if not path.is_dir() or not match or path == keep:
            continue
        taken = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H%M")
        if taken < cutoff:
            shutil.rmtree(path)
            removed.append(path.name)
    return removed


def run_backup(database_url, storage_dir, dest, *, now=None, keep_days=14, run=subprocess.run, pg_dump=None):
    """Write one backup folder under `dest` and return it; raise BackupFailed and leave nothing partial."""
    now = now or datetime.now()
    dest, storage_dir = Path(dest), Path(storage_dir)
    dest.mkdir(parents=True, exist_ok=True)
    folder = _new_folder(dest, now)
    partial = folder.with_name(folder.name + ".partial")
    try:
        if not storage_dir.is_dir():
            raise BackupFailed(f"Document storage folder not found: {storage_dir}")
        partial.mkdir()
        database, dump = _dump_database(database_url, partial, run, pg_dump or find_pg_dump())
        shutil.copytree(storage_dir, partial / "documents_storage")
        files = [p for p in (partial / "documents_storage").rglob("*") if p.is_file()]
        manifest = {
            "created_at": now.isoformat(timespec="seconds"),
            "database": database,
            "dump_file": dump.name,
            "dump_bytes": dump.stat().st_size,
            "dump_sha256": _sha256(dump),
            "storage_source": str(storage_dir),
            "storage_files": len(files),
            "storage_bytes": sum(p.stat().st_size for p in files),
        }
        (partial / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        partial.rename(folder)
    except Exception as exc:
        shutil.rmtree(partial, ignore_errors=True)
        _log(dest, f"FAILED {folder.name}: {exc}")
        raise exc if isinstance(exc, BackupFailed) else BackupFailed(str(exc)) from exc
    removed = _remove_old(dest, now, keep_days, keep=folder)
    _log(dest, f"OK {folder.name}: {manifest['storage_files']} files, dump {manifest['dump_bytes']} bytes"
               + (f"; removed {', '.join(sorted(removed))}" if removed else ""))
    return folder


def mirror_backup(folder, mirror, *, now=None, keep_days=14):
    """Copy a finished backup folder into `mirror` (another disk or machine); raise BackupFailed on failure."""
    now = now or datetime.now()
    folder, mirror = Path(folder), Path(mirror)
    target = mirror / folder.name
    partial = target.with_name(target.name + ".partial")
    try:
        mirror.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(partial, ignore_errors=True)
        shutil.copytree(folder, partial)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if _sha256(partial / manifest["dump_file"]) != manifest["dump_sha256"]:
            raise BackupFailed("the copied dump does not match the manifest's SHA-256")
        partial.rename(target)
        removed = _remove_old(mirror, now, keep_days, keep=target)
    except Exception as exc:
        shutil.rmtree(partial, ignore_errors=True)
        _log(folder.parent, f"MIRROR FAILED {folder.name}: {exc}")
        raise exc if isinstance(exc, BackupFailed) else BackupFailed(str(exc)) from exc
    _log(folder.parent, f"MIRROR OK {folder.name}: copied to {mirror}"
                        + (f"; removed {', '.join(sorted(removed))}" if removed else ""))
    return target


def main(argv=None):
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    from Backends.backend.backups import BACKUP_DIR, BACKUP_MIRROR_DIR
    from Backends.backend.core import UPLOAD_DIR

    parser = argparse.ArgumentParser(description="Back up the database and document storage.")
    parser.add_argument("--dest", default=str(BACKUP_DIR))
    parser.add_argument("--mirror", default=str(BACKUP_MIRROR_DIR or ""),
                        help="also copy the backup here (another disk or machine); BACKUP_MIRROR_DIR in .env")
    parser.add_argument("--keep-days", type=int, default=14)
    args = parser.parse_args(argv)

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        _log(Path(args.dest), "FAILED (not started): DATABASE_URL is not set in .env")
        print("DATABASE_URL is not set in .env", file=sys.stderr)
        return 1
    try:
        folder = run_backup(database_url, UPLOAD_DIR, args.dest, keep_days=args.keep_days)
    except BackupFailed as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Backup written to {folder}")
    if args.mirror:
        try:
            copy = mirror_backup(folder, args.mirror, keep_days=args.keep_days)
        except BackupFailed as exc:
            print(f"Copying the backup to {args.mirror} failed: {exc}", file=sys.stderr)
            return 1
        print(f"Copied to {copy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
