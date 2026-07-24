#!/usr/bin/env python3
"""Generate a self-signed certificate for HTTPS testing using trustme."""
from pathlib import Path
import trustme

cert_dir = Path(__file__).parent
cert_file = cert_dir / "scanner.crt"
key_file = cert_dir / "scanner.key"

if cert_file.exists() and key_file.exists():
    print("Certificate files already exist. Skipping generation.")
    print(f"Cert: {cert_file}")
    print(f"Key: {key_file}")
else:
    # Generate CA and server cert
    ca = trustme.CA()
    server = ca.issue_cert("192.168.1.4")
    
    # Write certificate
    with open(cert_file, "wb") as f:
        for blob in server.cert_chain_pems:
            f.write(blob.bytes())
    
    # Write key
    with open(key_file, "wb") as f:
        f.write(server.private_key_pem.bytes())
    
    print(f"✓ Certificate generated: {cert_file}")
    print(f"✓ Key generated: {key_file}")
    print(f"\nYour phone will show a security warning—tap 'Continue anyway' to proceed.")
