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

## Run it every night

Register a Windows scheduled task (runs at 2:00 AM while you are signed in):

```powershell
schtasks /Create /TN "SB Tolosa nightly backup" /SC DAILY /ST 02:00 /F /TR "\"C:\Users\archie\OneDrive\Documents\sb_tolosa_tracking\.venv\Scripts\python.exe\" \"C:\Users\archie\OneDrive\Documents\sb_tolosa_tracking\scripts\backup.py\""
```

Check it with `schtasks /Query /TN "SB Tolosa nightly backup"`, run it now with `schtasks /Run /TN "SB Tolosa nightly backup"`, and remove it with `schtasks /Delete /TN "SB Tolosa nightly backup" /F`. If the computer is off at 2:00 AM that night's backup is skipped; check `backup.log`.

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
