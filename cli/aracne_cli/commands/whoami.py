"""``aracne whoami``: prints the user the saved PAT resolves to.

Acts as the smoke-check after ``login`` ("is my config valid?") and a
quick verification when troubleshooting "why is the CLI behaving
weirdly?" (a token revoked from the web UI fails here).
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console

from aracne_cli.api import ApiClient, ApiError
from aracne_cli.config import DEFAULT_PROFILE, ProfileNotFoundError, load_profile

console = Console()


def whoami(
    profile: str = typer.Option(
        DEFAULT_PROFILE, "--profile", help="Config profile name."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON instead of human text."
    ),
) -> None:
    try:
        prof = load_profile(profile)
    except ProfileNotFoundError as exc:
        if json_output:
            typer.echo(_json.dumps({"ok": False, "error": str(exc)}))
        else:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    try:
        with ApiClient(prof.host, prof.token) as client:
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
                f"Failed: {exc.code}: {exc.message}",
                fg=typer.colors.RED,
                err=True,
            )
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            _json.dumps(
                {
                    "ok": True,
                    "profile": profile,
                    "host": prof.host,
                    "username": me.get("username"),
                    "role": me.get("role"),
                    "display_name": me.get("display_name"),
                }
            )
        )
        return

    console.print(
        f"[bold]{me.get('username')}[/bold] "
        f"([italic]{me.get('role')}[/italic]) at {prof.host} "
        f"(profile [italic]{profile}[/italic])"
    )
