# tolosa-LGU

## Run

Start the backend on port 8001:

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

Start the standalone phone scanner on port 8002:

```bash
python -m uvicorn frontend_scanner.app:app --reload --host 127.0.0.1 --port 8002
```

The scanner app talks to the backend through `BACKEND_URL`, and QR codes now point phones at `SCANNER_PUBLIC_URL`.

If you are in VS Code, use the `Run Full Stack` task to start both services together.
