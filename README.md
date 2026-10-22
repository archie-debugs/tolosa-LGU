# tolosa-LGU

## Run

### Using VS Code (Recommended)
Use the `Run Full Stack` task to start both services in the local development configuration:
```
Ctrl+Shift+P → Tasks: Run Task → Run Full Stack
```

### Manual Startup

**Backend (port 8001):**
```bash
python scripts/run/run_backend.py
```

**Public/login frontend:**
```bash
python frontend/app.py
```

**Administrator frontend:**
```bash
python frontend/admin/app.py
```

**Employee frontend:**
```bash
python scripts/run/run_flet_employee.py
```

Frontend roles are physically organized under `frontend/admin`, `frontend/employee`, and `frontend/sb_member`. Administrators and employees share the permission-aware document workspace so they see the same records, while each role has its own entrypoint and launcher.

## Database updates

Starting the backend **does** update the database. The main backend and the employee backend both run `alembic upgrade head` on startup (`run_database_migrations()` in `Backends/backend/schema.py`) against whatever `DATABASE_URL` in `.env` points at. An empty database is built from the models and stamped at head instead.

This means the code that is checked out when the backend starts decides the database schema:

- **Start the backend from `main`.** If a branch with an unmerged migration is checked out, starting the backend applies that migration to the real database, and `main` may then refuse to start until the branch is merged.
- **Pull before starting.** A backend whose code is older than the database fails at startup, because Alembic can't find the database's revision.
- **Only the computer that hosts the database applies migrations.** The laptops connect as users that can't create or alter tables, so their backend fails at startup if their checkout has a migration the database doesn't have yet. Start the backend on the database computer first after pulling a migration.

To check where the database is:

```
.venv\Scripts\python.exe -m alembic current
```

`alembic` reads `DATABASE_URL` from `.env`, so there is no need to type the password. `current` should end with `(head)`. Settings → System Information also shows the migration version.

## Two-step login

A Super Admin can turn on two-step login under My Account → Security. Login then asks for the 6-digit code from an authenticator app, or one of the recovery codes shown when it was turned on.

If someone loses both their phone and their recovery codes, turn it off on the server:

```
.venv\Scripts\python.exe scripts\reset_two_step.py <username>
```

## Local HTTP / HTTPS behavior

This project is configured for local development over HTTP by default. The `.env` file can set `DEV_HTTP=1` to force HTTP even when certificate files are present.

The repository currently contains certificate files named `scanner.crt` and `scanner.key`, and the startup script checks for those names. If they are missing, the backend starts on HTTP instead of HTTPS.

## Backend URL

- Backend: `http://127.0.0.1:8001` (or your machine IP address if you need network access)

## Backend layout

All backend services are grouped under `Backends/`:

- `Backends/backend`: main API service
- `Backends/backend_employee`: employee API service
- `Backends/SBmem_backend`: SB Member API service

The root launch scripts remain as convenient entrypoints and now import from these packages.

## Tests

```
python -m pytest
```

By default tests run on a throwaway SQLite file and never touch the database in `.env`.

SQLite ignores row locks and some PostgreSQL-only behaviour, so the handoff concurrency test is skipped there. To run the whole suite on PostgreSQL, point `TEST_DATABASE_URL` at a separate database whose name ends in `_test`. **Every table in it is dropped at the start of the run.**

```
createdb legi_sys_test
TEST_DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/legi_sys_test python -m pytest
```
