# Backups

`scripts/backup.py` backs up the database and the document storage folder (attachments and QR images).

```text
sb_tolosa_backups/                 (next to the project folder, or BACKUP_DIR / --dest)
├── 2026-10-21_0200_nightly/
│   ├── legi_sys.dump              pg_dump custom format
│   ├── documents_storage/         copy of DOCUMENT_STORAGE_DIR
│   └── manifest.json              time, database, file counts, dump SHA-256
└── backup.log                     one line per run: OK or FAILED
```

- A run writes `…_nightly.partial` and renames it only when everything succeeded.
- `*_nightly` folders older than 14 days (`--keep-days`) are removed after a successful run; the newest is always kept. Other folders, such as manual backups, are never touched.
- The database password is passed to `pg_dump` through the environment; it is never printed or logged.
- `pg_dump` is found through `PG_DUMP`, `PATH`, or the newest `C:\Program Files\PostgreSQL\*\bin`.

## Run it by hand

```powershell
.venv\Scripts\python.exe scripts\backup.py
```

## Run it on a schedule

On the computer that hosts the database, register the scheduled task once:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1
```

It runs `scripts\backup.py` daily at 12:00 and 17:30 (change with `-Times 08:00,12:00,17:30`), as the signed-in user, with no stored password. If the computer is off or nobody is signed in at a scheduled time, the run happens as soon as it can, not skipped. Re-running the script replaces the task; `-Remove` deletes it.

Check it with `Get-ScheduledTaskInfo -TaskName "SB Tolosa backup"` (`LastRunTime`, `LastTaskResult` 0 = success) and run it now with `Start-ScheduledTask -TaskName "SB Tolosa backup"`.

## Keep a copy off this computer

A backup on the same disk as the database is lost with that disk. Set `BACKUP_MIRROR_DIR` in `.env` to a folder on another disk or machine (an external drive, a network share, or a synced cloud folder):

```text
BACKUP_MIRROR_DIR=E:\sb_tolosa_backups
```

After each successful backup, the finished folder is copied there, the copied dump is checked against the manifest's SHA-256, and the same 14-day retention applies. `backup.log` (in the main backup folder) gets a `MIRROR OK` or `MIRROR FAILED` line. `--mirror DIR` overrides the setting for one run.

## Checking on backups

Settings → System Information shows **Backups** and **Last backup**. It reads `backup.log` and reports a warning, with the reason, when:

- no backup has been recorded, or the last successful one is more than a day old;
- the most recent run failed;
- `BACKUP_MIRROR_DIR` is not set, or the last copy to it failed.

The backend reads the log on the computer it runs on, so this is only meaningful on the computer that hosts the database and runs the backups.

## Restore

Stop the backend first.

```powershell
# Database: replaces the contents of legi_sys with the backup
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --clean --if-exists --no-owner `
  --host localhost --username <user> --dbname legi_sys `
  "C:\Users\archie\OneDrive\Documents\sb_tolosa_backups\<folder>\legi_sys.dump"

# Files: copy documents_storage back into DOCUMENT_STORAGE_DIR
robocopy "C:\Users\archie\OneDrive\Documents\sb_tolosa_backups\<folder>\documents_storage" `
  "$env:LOCALAPPDATA\sb_tolosa_tracking\documents" /MIR
```

`/MIR` makes the storage folder match the backup exactly, deleting files added since.

### Restore test

Tested 2026-10-22: the `2026-10-22_1525_nightly` dump was restored with `pg_restore --no-owner` into a new, empty database (`legi_sys_restore_check`). All 23 tables had the same row counts as `legi_sys`, and `alembic_version` matched. To repeat the test without touching the real database, restore into a scratch database instead of `legi_sys`:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" --username postgres legi_sys_restore_check
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --no-owner --exit-on-error --username postgres `
  --dbname legi_sys_restore_check "<backup folder>\legi_sys.dump"
# compare, then:
& "C:\Program Files\PostgreSQL\18\bin\dropdb.exe" --username postgres legi_sys_restore_check
```
