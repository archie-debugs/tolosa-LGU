from datetime import datetime

from Backends.backend.backups import backup_health

NOW = datetime(2026, 10, 22, 18, 0)


def write_log(dest, *lines):
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "backup.log").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def test_a_recent_mirrored_backup_is_operational(tmp_path):
    write_log(tmp_path, "2026-10-22T12:00:05 OK 2026-10-22_1200_nightly: 10 files, dump 100 bytes",
              "2026-10-22T12:00:09 MIRROR OK 2026-10-22_1200_nightly: copied to E:\backups")

    health = backup_health(tmp_path, mirror="E:\backups", now=NOW)

    assert health["status"] == "operational"
    assert health["detail"]["problems"] == []
    assert health["detail"]["last_backup_folder"] == "2026-10-22_1200_nightly"
    assert datetime.fromisoformat(health["detail"]["last_backup_at"]).utcoffset() is not None


def test_no_log_means_no_backup_has_been_recorded(tmp_path):
    health = backup_health(tmp_path / "missing", mirror="E:\backups", now=NOW)

    assert health["status"] == "warning"
    assert health["detail"]["last_backup_at"] is None
    assert "No backup has been recorded" in health["detail"]["problems"][0]


def test_an_old_backup_and_a_failed_run_are_both_reported(tmp_path):
    write_log(tmp_path, "2026-10-20T23:23:34 OK 2026-10-20_2323_nightly: 219 files, dump 118534 bytes",
              "2026-10-22T12:00:01 FAILED 2026-10-22_1200_nightly: pg_dump failed: connection refused")

    problems = backup_health(tmp_path, mirror="E:\backups", now=NOW)["detail"]["problems"]

    assert any("more than a day old" in problem for problem in problems)
    assert any("connection refused" in problem for problem in problems)


def test_a_missing_or_failing_mirror_is_a_warning(tmp_path):
    write_log(tmp_path, "2026-10-22T12:00:05 OK 2026-10-22_1200_nightly: 10 files, dump 100 bytes")
    assert "BACKUP_MIRROR_DIR" in backup_health(tmp_path, mirror="", now=NOW)["detail"]["problems"][0]

    write_log(tmp_path, "2026-10-22T12:00:05 OK 2026-10-22_1200_nightly: 10 files, dump 100 bytes",
              "2026-10-22T12:00:06 MIRROR FAILED 2026-10-22_1200_nightly: [WinError 3] path not found")
    health = backup_health(tmp_path, mirror="E:\backups", now=NOW)
    assert health["status"] == "warning"
    assert "WinError 3" in health["detail"]["problems"][0]
