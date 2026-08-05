# tolosa-LGU

## Run

### Using VS Code (Recommended)
Use the `Run Full Stack` task to start both services with HTTPS enabled:
```
Ctrl+Shift+P → Tasks: Run Task → Run Full Stack
```

### Manual Startup

**Backend (port 8001 with HTTPS):**
```bash
python run_backend.py
```

**Admin frontend:**
```bash
python frontend/frontend_admin/app.py
```

## HTTPS Setup

The backend can run with HTTPS if valid certificates are available in the repository root as `server.crt` and `server.key`.

If certificate files are not present, the backend falls back to HTTP by default. Use `DEV_HTTP=1` in `.env` to force HTTP during local development.

## Backend URL

- Backend: `http://127.0.0.1:8001` (or your machine IP address if you need network access)
