#!/usr/bin/env python3
"""Run backend with HTTPS support."""
import os
import sys
from pathlib import Path

# Ensure project root is on Python path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import uvicorn

if __name__ == "__main__":
    from backend.main import app
    
    cert_file = project_root / "scanner.crt"
    key_file = project_root / "scanner.key"

    # Allow forcing HTTP for local/dev tools via DEV_HTTP=1 even if certs exist
    dev_http = os.getenv("DEV_HTTP", "0").lower() in ("1", "true", "yes")

    ssl_kwargs = {}
    if dev_http:
        print("DEV_HTTP=1 set — forcing HTTP (no SSL) for development")
    elif cert_file.exists() and key_file.exists():
        ssl_kwargs = {"ssl_certfile": str(cert_file), "ssl_keyfile": str(key_file)}
        # Use plain ASCII text to avoid encoding errors when stdout is redirected
        print("HTTPS enabled on backend with self-signed certificate")
    else:
        print("Certificates not found. Running backend on HTTP")

    # If DEV_HTTP is set we intentionally don't pass SSL kwargs
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
        reload=False,
        log_level="debug",
        **(ssl_kwargs if not dev_http else {})
    )
