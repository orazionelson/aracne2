"""SSRF guard — shared utility for validating outbound URLs.

Blocks requests to private, loopback, link-local, multicast, and reserved
addresses to prevent Server-Side Request Forgery attacks.

Design: we block private IP ranges rather than maintaining a domain allowlist.
Blocking private IPs prevents the most common SSRF vectors — internal metadata
APIs (169.254.169.254), databases, and other containers on the same Docker
network — while allowing any legitimate public URL.

Note: the DNS lookup (socket.gethostbyname) runs synchronously. It is a
one-time check that completes in under 100 ms in the common case; running it
in a thread executor is intentionally deferred.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.exceptions import DomainValidationError


def check_ssrf(url: str) -> None:
    """Raise DomainValidationError if *url* resolves to a non-public address.

    Checks performed:
    - Scheme must be http or https.
    - Hostname must be present and resolvable.
    - Resolved IP must not be private, loopback, link-local, multicast or reserved.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DomainValidationError("INVALID_URL", "Only http:// and https:// URLs are allowed.")
    hostname = parsed.hostname or ""
    if not hostname:
        raise DomainValidationError("INVALID_URL", "URL must include a hostname.")
    try:
        ip_str = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(ip_str)
    except (socket.gaierror, ValueError) as exc:
        raise DomainValidationError(
            "INVALID_URL", f"Cannot resolve hostname {hostname!r}: {exc}"
        ) from exc
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
    ):
        raise DomainValidationError(
            "SSRF_BLOCKED",
            f"URL resolves to a non-public address ({addr}). "
            "Requests to private or internal hosts are not permitted.",
        )
