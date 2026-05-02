"""``aracne login``: interactive PAT capture + verification.

Prompts for a host (or accepts ``--host``) and a token (always
prompted, never on the command line — leaking the token through the
shell history would defeat the point), then verifies the pair with a
``GET /auth/me`` round-trip before persisting to
``~/.aracne/config.toml``.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console

from aracne_cli.api import ApiClient, ApiError
from aracne_cli.config import DEFAULT_PROFILE, Profile, save_profile

console = Console()


def login(
    host: str = typer.Option(
        ...,
        "--host",
        help="Aracne2 base URL, e.g. https://aracne.example.org",
        prompt=True,
    ),
    profile: str = typer.Option(
        DEFAULT_PROFILE,
        "--profile",
        help="Config profile name (override with --profile to manage multiple deployments).",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON instead of human text."
    ),
) -> None:
    """Capture a PAT and verify it against *host*.

    The PAT is read interactively (``hide_input=True``) so it never
    lands in shell history. On success the credentials are written
    to ``~/.aracne/config.toml`` with permissions ``0600``.
    """
    token = typer.prompt(
        "Personal access token (paste from your Profile page)",
        hide_input=True,
        confirmation_prompt=False,
    ).strip()
    if not token:
        typer.secho("Empty token, aborting.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    profile_obj = Profile(name=profile, host=host.rstrip("/"), token=token)

    # Verify the pair before persisting — saving a bad token is worse
    # than failing the login (the user would only discover the error
    # later when running an actual command).
    try:
        with ApiClient(profile_obj.host, profile_obj.token) as client:
            me = client.get("/auth/me")
    except ApiError as exc:
        if json_output:
            typer.echo(
                _json.dumps(
                    {"ok": False, "code": exc.code, "message": exc.message}
                )
            )
        else:
            typer.secho(
                f"Login failed: {exc.code}: {exc.message}",
                fg=typer.colors.RED,
                err=True,
            )
        raise typer.Exit(code=1) from exc

    config_path = save_profile(profile_obj)

    if json_output:
        typer.echo(
            _json.dumps(
                {
                    "ok": True,
                    "profile": profile,
                    "host": profile_obj.host,
                    "username": me.get("username"),
                    "role": me.get("role"),
                    "config_path": str(config_path),
                }
            )
        )
        return

    console.print(
        f"[green]Logged in[/green] as "
        f"[bold]{me.get('username')}[/bold] "
        f"([italic]{me.get('role')}[/italic]) at {profile_obj.host}"
    )
    console.print(
        f"Credentials saved to [bold]{config_path}[/bold] (profile [italic]{profile}[/italic])."
    )
