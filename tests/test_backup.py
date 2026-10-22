import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import backup  # noqa: E402

NOW = datetime(2026, 10, 21, 2, 0)
PG_URL = "postgresql+psycopg2://lgu:s3cret-pw@localhost:5432/legi_sys"


class FakePgDump:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, args, env=None, capture_output=None, text=None):
        self.calls.append((args, env))
        if self.fail:
            return type("Result", (), {"returncode": 1, "stderr": "connection refused"})()
        out = args[args.index("--file") + 1]
        Path(out).write_bytes(b"PGDMP fake dump")
        return type("Result", (), {"returncode": 0, "stderr": ""})()


@pytest.fixture
def storage(tmp_path):
    root = tmp_path / "documents"
    (root / "qr").mkdir(parents=True)
    (root / "a.pdf").write_bytes(b"%PDF a")
    (root / "qr" / "DOC-000001.png").write_bytes(b"png")
    return root


def run(tmp_path, storage, pg_dump=None, url=PG_URL, now=NOW, keep_days=14):
    return backup.run_backup(url, storage, tmp_path / "backups", now=now, keep_days=keep_days,
                             run=pg_dump or FakePgDump(), pg_dump="pg_dump")


def test_a_backup_holds_the_dump_the_storage_copy_and_a_manifest(tmp_path, storage):
    folder = run(tmp_path, storage)

    assert folder.name == "2026-10-21_0200_nightly"
    assert (folder / "legi_sys.dump").read_bytes() == b"PGDMP fake dump"
    assert (folder / "documents_storage" / "a.pdf").read_bytes() == b"%PDF a"
    assert (folder / "documents_storage" / "qr" / "DOC-000001.png").exists()
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["database"] == "legi_sys"
    assert manifest["storage_files"] == 2
    assert len(manifest["dump_sha256"]) == 64
    assert not list((tmp_path / "backups").glob("*.partial"))


def test_the_password_goes_through_the_environment_and_is_never_written(tmp_path, storage):
    pg_dump = FakePgDump()
    folder = run(tmp_path, storage, pg_dump)

    args, env = pg_dump.calls[0]
    assert "s3cret-pw" not in " ".join(args)
    assert env["PGPASSWORD"] == "s3cret-pw"
    assert args[:1] == ["pg_dump"] and "--format=custom" in args
    for path in [folder / "manifest.json", tmp_path / "backups" / "backup.log"]:
        assert "s3cret-pw" not in path.read_text()


def test_a_failed_dump_leaves_no_partial_folder_and_is_logged(tmp_path, storage):
    with pytest.raises(backup.BackupFailed, match="connection refused"):
        run(tmp_path, storage, FakePgDump(fail=True))

    backups = tmp_path / "backups"
    assert [p.name for p in backups.iterdir()] == ["backup.log"]
    assert "FAILED" in (backups / "backup.log").read_text()


def test_old_nightly_backups_are_removed_but_manual_ones_and_the_newest_stay(tmp_path, storage):
    backups = tmp_path / "backups"
    for name in ["2026-09-30_0200_nightly", "2026-10-06_0200_nightly", "2026-10-07_0200_nightly",
                 "2026-09-01_before_document_wipe", "notes"]:
        (backups / name).mkdir(parents=True)

    run(tmp_path, storage)

    assert sorted(p.name for p in backups.iterdir() if p.is_dir()) == [
        "2026-09-01_before_document_wipe", "2026-10-07_0200_nightly", "2026-10-21_0200_nightly", "notes",
    ]


def test_retention_never_removes_the_only_backup(tmp_path, storage):
    backups = tmp_path / "backups"
    run(tmp_path, storage, now=datetime(2026, 1, 1, 2, 0))

    run(tmp_path, storage, pg_dump=None, now=datetime(2026, 10, 21, 2, 0), keep_days=14)

    assert sorted(p.name for p in backups.iterdir() if p.is_dir()) == ["2026-10-21_0200_nightly"]
    with pytest.raises(backup.BackupFailed):
        run(tmp_path, storage, FakePgDump(fail=True), now=datetime(2026, 12, 1, 2, 0))
    assert sorted(p.name for p in backups.iterdir() if p.is_dir()) == ["2026-10-21_0200_nightly"]


def test_a_second_run_in_the_same_minute_gets_its_own_folder(tmp_path, storage):
    first = run(tmp_path, storage)
    second = run(tmp_path, storage)

    assert first != second and second.name.startswith("2026-10-21_0200")


def test_sqlite_databases_are_copied_instead_of_dumped(tmp_path, storage):
    db_file = tmp_path / "sb.db"
    db_file.write_bytes(b"SQLite format 3\x00")
    pg_dump = FakePgDump()

    folder = run(tmp_path, storage, pg_dump, url=f"sqlite:///{db_file}")

    assert pg_dump.calls == []
    assert (folder / "sb.db").read_bytes() == b"SQLite format 3\x00"


def test_missing_storage_folder_is_reported_not_silently_skipped(tmp_path):
    with pytest.raises(backup.BackupFailed, match="storage"):
        run(tmp_path, tmp_path / "nowhere")


def test_a_mirror_gets_a_verified_copy_and_its_own_retention(tmp_path, storage):
    mirror = tmp_path / "mirror"
    (mirror / "2026-09-30_0200_nightly").mkdir(parents=True)
    folder = run(tmp_path, storage)

    copy = backup.mirror_backup(folder, mirror, now=NOW)

    assert copy == mirror / "2026-10-21_0200_nightly"
    assert (copy / "legi_sys.dump").read_bytes() == b"PGDMP fake dump"
    assert (copy / "documents_storage" / "a.pdf").exists()
    assert sorted(p.name for p in mirror.iterdir()) == ["2026-10-21_0200_nightly"]
    assert "MIRROR OK 2026-10-21_0200_nightly" in (tmp_path / "backups" / "backup.log").read_text()


def test_a_mirror_copy_that_does_not_match_the_manifest_is_discarded(tmp_path, storage):
    folder = run(tmp_path, storage)
    manifest = json.loads((folder / "manifest.json").read_text())
    (folder / "manifest.json").write_text(json.dumps({**manifest, "dump_sha256": "0" * 64}))

    with pytest.raises(backup.BackupFailed, match="SHA-256"):
        backup.mirror_backup(folder, tmp_path / "mirror", now=NOW)

    assert list((tmp_path / "mirror").iterdir()) == []
    assert "MIRROR FAILED" in (tmp_path / "backups" / "backup.log").read_text()
