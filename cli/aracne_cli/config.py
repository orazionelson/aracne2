"""Read/write ``~/.aracne/config.toml``.

Layout::

    [default]
    host = "https://aracne.example.org"
    token = "aracne2_pat_..."

    [work]
    host = "https://aracne.work.example"
    token = "aracne2_pat_..."

Each top-level table is a *profile*. ``aracne login`` writes one;
``--profile NAME`` selects which one to use at runtime. A missing
profile raises :class:`ProfileNotFoundError` so the user gets a clear
"run aracne login first" message.

The file is chmod-ed to ``0600`` on every write — even though TOML
is readable, the embedded plaintext PAT must not be world-readable.
We hand-roll TOML serialisation (the schema is two strings per
profile, no need for a writer dependency) and parse with the stdlib
``tomllib`` available since Python 3.11.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover — Python <3.11
    import tomli as tomllib  # type: ignore[no-redef,import-not-found]


CONFIG_HOME_ENV = "ARACNE_CLI_CONFIG_HOME"
"""Override the config directory for tests / sandboxed runs.

Set ``ARACNE_CLI_CONFIG_HOME`` to a directory path and the CLI uses
``$ARACNE_CLI_CONFIG_HOME/config.toml`` instead of
``~/.aracne/config.toml``. Pytest fixtures use this to keep the
developer's real ``~/.aracne`` untouched.
"""

DEFAULT_PROFILE = "default"


class ConfigError(Exception):
    """Base for all config-related failures."""


class ProfileNotFoundError(ConfigError):
    """Raised when the requested profile is missing from the file.

    Carries the profile name and the config path so the CLI can print
    a helpful "run ``aracne login --profile {name}`` first" message.
    """

    def __init__(self, profile: str, path: Path) -> None:
        super().__init__(
            f"Profile '{profile}' not found in {path}. "
            f"Run 'aracne login --profile {profile}' to create it."
        )
        self.profile = profile
        self.path = path


@dataclass(frozen=True)
class Profile:
    """The per-profile pair the CLI cares about — host + bearer."""

    name: str
    host: str
    token: str


def config_dir() -> Path:
    """Return the directory holding ``config.toml``.

    Honours :data:`CONFIG_HOME_ENV` for tests; otherwise
    ``~/.aracne``. The directory is *not* created here — write
    operations call :func:`_ensure_config_dir` lazily.
    """
    env = os.environ.get(CONFIG_HOME_ENV)
    if env:
        return Path(env)
    return Path.home() / ".aracne"


def config_path() -> Path:
    """Absolute path of the config file."""
    return config_dir() / "config.toml"


def _ensure_config_dir() -> Path:
    """Create the config dir with ``0700`` permissions if missing."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    # Best-effort tighten — on Windows ``chmod`` is a no-op.
    try:
        os.chmod(d, stat.S_IRWXU)
    except OSError:
        pass
    return d


def _read_all() -> dict[str, dict[str, str]]:
    """Parse the whole file. Returns an empty dict when the file is missing.

    Other exceptions (corrupt TOML, unreadable file) propagate so the
    CLI can surface them — there's no recovery a generic helper can
    perform.
    """
    p = config_path()
    if not p.exists():
        return {}
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    out: dict[str, dict[str, str]] = {}
    for name, value in data.items():
        if isinstance(value, dict):
            out[name] = {str(k): str(v) for k, v in value.items()}
    return out


def _write_all(profiles: dict[str, dict[str, str]]) -> None:
    """Render *profiles* to TOML and atomically replace the config file.

    Permissions are forced to ``0600`` on the new file; we use a
    rename instead of an overwrite so a SIGKILL between writes can
    never leave the file half-flushed.
    """
    _ensure_config_dir()
    body_lines: list[str] = []
    for name in sorted(profiles):
        body_lines.append(f"[{_quote_table_name(name)}]")
        for key in sorted(profiles[name]):
            value = profiles[name][key]
            body_lines.append(f'{key} = "{_escape_basic_string(value)}"')
        body_lines.append("")
    body = "\n".join(body_lines).rstrip() + "\n"

    final = config_path()
    tmp = final.with_suffix(".toml.tmp")
    fd = os.open(
        tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, final)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    # Re-tighten in case ``os.replace`` reset the mode on this platform.
    try:
        os.chmod(final, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _quote_table_name(name: str) -> str:
    """Quote a TOML table name when needed.

    Bare keys are made of [A-Za-z0-9_-]; anything else gets quoted.
    """
    if all(c.isalnum() or c in "_-" for c in name) and name:
        return name
    return f'"{_escape_basic_string(name)}"'


def _escape_basic_string(value: str) -> str:
    """Escape a TOML basic string."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\f", "\\f")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def load_profile(name: str = DEFAULT_PROFILE) -> Profile:
    """Return the profile *name*, raising :class:`ProfileNotFoundError`
    when missing or incomplete.

    "Incomplete" means missing ``host`` or ``token`` — the user pretty
    much always meant to run ``aracne login`` first in that case.
    """
    profiles = _read_all()
    raw = profiles.get(name)
    if raw is None or "host" not in raw or "token" not in raw:
        raise ProfileNotFoundError(name, config_path())
    return Profile(name=name, host=raw["host"].rstrip("/"), token=raw["token"])


def save_profile(profile: Profile) -> Path:
    """Upsert *profile* into the config file. Returns the file path."""
    profiles = _read_all()
    profiles[profile.name] = {
        "host": profile.host.rstrip("/"),
        "token": profile.token,
    }
    _write_all(profiles)
    return config_path()
