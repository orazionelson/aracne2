"""``python -m aracne_cli`` entry point.

Mirrors the ``aracne`` console script declared in pyproject.toml so
the CLI is reachable both ways. Useful when the entry point is not on
PATH (e.g. inside a venv whose bin/ has not been activated).
"""

from aracne_cli.cli import app

if __name__ == "__main__":
    app()
