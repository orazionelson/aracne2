"""aracne-cli — command-line client for an Aracne2 deployment.

Public entry point: ``aracne_cli.cli.app``. The package is installed
via the ``cli/`` subdirectory of the Aracne2 monorepo (``pip install
-e cli/``); the ``aracne`` console script is wired in
``cli/pyproject.toml`` to ``aracne_cli.cli:app``.
"""

from aracne_cli.version import __version__

__all__ = ["__version__"]
