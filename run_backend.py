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

    # Use HTTPS if certificates exist, otherwise HTTP
    ssl_kwargs = {}
    if cert_file.exists() and key_file.exists():
        ssl_kwargs = {"ssl_certfile": str(cert_file), "ssl_keyfile": str(key_file)}
        print("✓ HTTPS enabled on backend with self-signed certificate")
    else:
        print("⚠ Certificates not found. Running backend on HTTP")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
        reload=False,
        **ssl_kwargs
    )
