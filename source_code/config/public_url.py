"""Build email links that remain reachable from other devices on the LAN.

Use ``PUBLIC_BASE_URL=auto`` for local/LAN development. Auto mode derives the
server machine's LAN IPv4 address instead of trusting the HTTP Host header. For
a deployed site, set PUBLIC_BASE_URL to the real HTTPS domain/IP.
"""

from __future__ import annotations

import ipaddress
import socket

from django.conf import settings


def _usable_ipv4(value: str | None) -> bool:
    if not value:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (
        address.version == 4
        and not address.is_loopback
        and not address.is_unspecified
        and not address.is_link_local
    )


def detect_lan_ip() -> str:
    """Best-effort detection of the IPv4 address used by this server machine."""
    candidates: list[str] = []

    # Asking the OS for the source address of a UDP route is usually the most
    # reliable way to identify the active Wi-Fi/Ethernet interface. No payload
    # is sent by this operation.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        candidates.append(sock.getsockname()[0])
    except OSError:
        pass
    finally:
        sock.close()

    try:
        candidates.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass

    # Prefer RFC/private addresses for LAN use when available.
    for candidate in candidates:
        if _usable_ipv4(candidate) and ipaddress.ip_address(candidate).is_private:
            return candidate

    for candidate in candidates:
        if _usable_ipv4(candidate):
            return candidate

    return "127.0.0.1"


def _configured_base_url() -> str:
    value = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if value.lower() in {"", "auto", "dynamic"}:
        return ""
    return value


def _auto_scheme_and_port(request=None) -> tuple[str, int]:
    if request is not None:
        scheme = (getattr(request, "scheme", "http") or "http").lower()
        try:
            port = int(request.get_port())
        except (AttributeError, TypeError, ValueError):
            port = 443 if scheme == "https" else 80
        return scheme, port

    scheme = (getattr(settings, "AUTO_BASE_URL_SCHEME", "http") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        scheme = "http"
    try:
        port = int(getattr(settings, "AUTO_BASE_URL_PORT", 8000))
    except (TypeError, ValueError):
        port = 8000
    return scheme, port


def get_public_base_url(request=None) -> str:
    """Return a manual public URL or an automatically detected LAN URL."""
    configured = _configured_base_url()
    if configured:
        return configured

    scheme, port = _auto_scheme_and_port(request)
    default_port = 443 if scheme == "https" else 80
    port_suffix = f":{port}" if port != default_port else ""
    return f"{scheme}://{detect_lan_ip()}{port_suffix}"


def build_public_url(path: str, request=None) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{get_public_base_url(request)}{path}"
