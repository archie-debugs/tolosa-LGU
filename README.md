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
python run_backend.py
```

**Admin frontend:**
```bash
python frontend/frontend_admin/app.py
```

## Local HTTP / HTTPS behavior

This project is configured for local development over HTTP by default. The `.env` file can set `DEV_HTTP=1` to force HTTP even when certificate files are present.

The repository currently contains certificate files named `scanner.crt` and `scanner.key`, and the startup script checks for those names. If they are missing, the backend starts on HTTP instead of HTTPS.

## Backend URL

- Backend: `http://127.0.0.1:8001` (or your machine IP address if you need network access)
