"""Exception hierarchy for the git-forge adapters.

All adapters raise instances of these types so plugin services
(codeberg / github / gitlab) can translate a single error tree
into HTTP responses without caring which forge produced the
underlying failure.
"""

from __future__ import annotations


class GitForgeError(Exception):
    """Base class for every git-forge adapter error."""


class AuthFailed(GitForgeError):
    """The supplied PAT was rejected (401 / invalid token)."""


class Forbidden(GitForgeError):
    """The PAT authenticates but lacks the required scope (403)."""


class RepoNotFound(GitForgeError):
    """The ``owner/name`` pair does not resolve on the forge (404)."""


class BranchNotFound(GitForgeError):
    """The named branch does not exist on the repo (404 on ref lookup)."""


class RateLimited(GitForgeError):
    """The forge answered with 429 or an equivalent rate-limit signal."""


class PushConflict(GitForgeError):
    """The server refused the push because the branch moved under us
    (stale base SHA). Callers may retry with a fresh head."""


class UpstreamError(GitForgeError):
    """Any other non-success status — network hiccup, 5xx, malformed
    JSON. The original cause is attached via ``__cause__``."""
