"""Defensive URL helpers — host-class blocklist for outbound bases.

Plugins that accept a user-configurable ``base_url`` (the forge
integrations and Dataverse) used to validate only the URL scheme,
which let an Admin / EditorInChief point an integration at a private
network address. Beyond the usual SSRF surface, the plugin then sends
the configured PAT in the ``Authorization`` header against whatever
host the URL resolved to — so a typo could leak a personal access
token into an unrelated service's logs.

``assert_public_http_url`` rejects URLs whose host is an IP literal
in the loopback, link-local, private, multicast, reserved, or
unspecified ranges (both IPv4 and IPv6). It runs at write time
(Pydantic validator).

Hostname-based checks would require DNS resolution, which is
fragile: search-domain suffixes on developer machines (e.g.
``example.edu`` → ``example.edu.homenet.X``) make a strict resolver
reject perfectly fine self-hosted-forge URLs in tests. Stronger
egress controls belong in the deployment's network layer (firewall,
proxy with allowlist) — this helper closes the common typo path
(``http://127.0.0.1/``, ``http://169.254.169.254/``) without making
the schema flaky.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def assert_public_http_url(url: str) -> None:
    """Raise ValueError unless *url* is a public http(s) URL.

    Steps:
    1. Parse the URL and require an ``http://`` or ``https://`` scheme
       and a non-empty host.
    2. If the host is an IP literal, reject any address in the
       loopback / link-local / private / multicast / reserved /
       unspecified ranges.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must use http:// or https://")

    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host component")

    # IPv6 literals show up here without their surrounding brackets.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # hostname — out of scope for this check

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise ValueError(f"URL host resolves to a non-routable address: {ip}")
