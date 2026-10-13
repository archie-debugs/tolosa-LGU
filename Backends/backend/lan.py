import ipaddress
import os
import socket
from urllib.parse import urlsplit, urlunsplit


def detect_lan_ipv4() -> str | None:
    """Detect the IPv4 address selected for outbound LAN traffic."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
        parsed = ipaddress.ip_address(address)
        if parsed.version == 4 and not parsed.is_loopback and not parsed.is_unspecified:
            return address
    except OSError:
        pass
    return None


def refresh_development_public_urls() -> str | None:
    """Resolve private development URLs once without overriding public domains."""
    if os.getenv("DEV_HTTP", "0").lower() not in {"1", "true", "yes"}:
        return None
    if os.getenv("AUTO_DETECT_LAN_IP", "1").lower() not in {"1", "true", "yes"}:
        return None

    lan_ip = detect_lan_ipv4()
    if not lan_ip:
        print("LAN IP detection unavailable; keeping configured public URLs.")
        return None

    for variable, port in (("PUBLIC_BASE_URL", 8001), ("FRONTEND_PUBLIC_URL", 8550)):
        configured = os.getenv(variable, "").strip().rstrip("/")
        if not configured:
            os.environ[variable] = f"http://{lan_ip}:{port}"
            continue

        parsed = urlsplit(configured)
        try:
            configured_ip = ipaddress.ip_address(parsed.hostname or "")
        except ValueError:
            configured_ip = None
        if configured_ip is None or not (configured_ip.is_private or configured_ip.is_loopback):
            continue

        os.environ[variable] = urlunsplit(
            (parsed.scheme or "http", f"{lan_ip}:{port}", parsed.path, parsed.query, parsed.fragment)
        )

    print(f"Using detected development LAN IP {lan_ip} for public URLs.")
    return lan_ip
