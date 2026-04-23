"""ORCID identifier validation.

Implements the canonical ``XXXX-XXXX-XXXX-XXXX`` shape plus the ISO
7064 Mod 11-2 checksum the ORCID spec requires on the last digit (the
checksum character may be ``X`` when the value is 10). This prevents
a typo in the profile field from leaking into downstream metadata
(Zenodo, LOD) where it would be hard to notice.

Pure stdlib — no DB, no framework imports.
"""

from __future__ import annotations

import re

_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dXx]$")


def _mod_11_2_checksum(digits: str) -> str:
    """Compute the Mod 11-2 check character for the first 15 digits."""
    total = 0
    for d in digits:
        total = (total + int(d)) * 2
    remainder = total % 11
    result = (12 - remainder) % 11
    return "X" if result == 10 else str(result)


def is_valid_orcid(value: str) -> bool:
    """Return True iff *value* is a well-formed ORCID with a valid checksum."""
    if not _ORCID_RE.match(value):
        return False
    digits_only = value.replace("-", "")
    core, check = digits_only[:-1], digits_only[-1].upper()
    return _mod_11_2_checksum(core) == check


def normalise_orcid(raw: str) -> str:
    """Strip common pastes (``https://orcid.org/…``, ``orcid:…``) and
    upper-case the checksum character. Does **not** validate — call
    :func:`is_valid_orcid` on the result."""
    cleaned = raw.strip()
    for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid:"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return cleaned.upper()
