"""Typer entry point.

Single ``app`` instance with four subcommands plus a ``--version``
flag. Each command lives in its own module under ``aracne_cli.commands``
to keep the file under cognitive-load thresholds.
"""

from __future__ import annotations

import typer

from aracne_cli.commands import export as _export
from aracne_cli.commands import import_ as _import
from aracne_cli.commands import login as _login
from aracne_cli.commands import whoami as _whoami
from aracne_cli.version import __version__

app = typer.Typer(
    name="aracne",
    help="Bulk import/export and admin tasks for an Aracne2 deployment.",
    no_args_is_help=True,
    add_completion=False,
)

app.command(name="login", help="Capture a personal access token and save it locally.")(
    _login.login
)
app.command(name="whoami", help="Show the user the saved token resolves to.")(
    _whoami.whoami
)
app.command(
    name="import",
    help="Bulk-upload XML documents from a directory into a collection.",
)(_import.import_documents)
app.command(name="export", help="Download a collection as a ZIP archive.")(
    _export.export_collection
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"aracne-cli {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the CLI version and exit.",
    ),
) -> None:
    """Top-level callback hook for global flags such as ``--version``."""


if __name__ == "__main__":
    app()
