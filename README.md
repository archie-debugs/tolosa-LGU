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

**Scanner (port 8002 with HTTPS):**
```bash
python frontend_scanner/app.py
```

## HTTPS Setup

The system now runs on **HTTPS** to enable camera access on mobile phones. Self-signed certificates have been generated:
- `scanner.crt` - SSL certificate
- `scanner.key` - SSL private key

When accessing from your phone, you'll see a security warning. Tap **"Continue anyway"** to proceed.

## Phone Access

1. Start the services (Run Full Stack task)
2. On your PC: Generate QR code in admin app pointing to `https://192.168.1.4:8002`
3. On your phone: Scan QR code with Chrome
4. Accept SSL warning
5. Camera should now work for automatic QR scanning

## Backend & Scanner URLs

- Backend: `https://192.168.1.4:8001` (or localhost `https://127.0.0.1:8001`)
- Scanner: `https://192.168.1.4:8002` (or localhost `https://127.0.0.1:8002`)

QR codes automatically point to the correct HTTPS endpoints.
