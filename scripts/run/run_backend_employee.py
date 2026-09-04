#!/usr/bin/env python3
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    from Backends.backend_employee.main import app

    cert_file = project_root / "server.crt"
    key_file = project_root / "server.key"

    dev_http = os.getenv("DEV_HTTP", "0").lower() in ("1", "true", "yes")

    ssl_kwargs = {}
    if dev_http:
        print("DEV_HTTP=1 set — forcing HTTP (no SSL) for development")
    elif cert_file.exists() and key_file.exists():
        ssl_kwargs = {"ssl_certfile": str(cert_file), "ssl_keyfile": str(key_file)}
        print("HTTPS enabled on employee backend with self-signed certificate")
    else:
        print("Certificates not found. Running employee backend on HTTP")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("EMPLOYEE_PORT", "8002")),
        reload=False,
        log_level="debug",
        **(ssl_kwargs if not dev_http else {}),
    )
