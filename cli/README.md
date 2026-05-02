# aracne-cli

Command-line tool for bulk operations against an Aracne2 deployment.
Wraps the existing REST API; never touches the database directly.

## Install

From a checkout of the Aracne2 monorepo:

```bash
pip install -e cli/
```

That installs the `aracne` entry point (and the `aracne_cli` package)
into your active Python environment.

## Authenticate

`aracne-cli` authenticates with a long-lived **Personal Access Token**
(PAT) issued by the user from their profile page in the web UI.

1. Sign in to Aracne2 in a browser, navigate to **Profile → API
   tokens**, click **Issue token**, give it a label (e.g.
   `my-laptop`), and copy the plaintext value shown in the modal.
2. Run `aracne login` and paste the token when prompted:

   ```bash
   aracne login --host https://aracne.example.org
   ```

   The credentials are written to `~/.aracne/config.toml` with
   permissions restricted to `0600`.

3. Verify the token is valid:

   ```bash
   aracne whoami
   ```

`aracne login`/`whoami`/`import`/`export` all support `--profile NAME`
for switching between hosts; the default profile is `default`.

## Commands

### Bulk import

```bash
aracne import \
  --collection my-corpus \
  --dir ./tei-files/ \
  --on-conflict skip      # default: skip|overwrite|fail
```

The CLI walks `--dir` for `*.xml` files (no recursion in v1) and
uploads each one. Filenames must match
`^[a-zA-Z0-9][a-zA-Z0-9_\-]*\.xml$` — the same regex the backend
enforces; non-matching files are skipped before upload with a clear
error.

Re-running the same import is idempotent under the default
`--on-conflict skip` mode: existing filenames are left untouched.
`--on-conflict overwrite` PUTs the new body over the existing
document (the backend's working/published split means the public
view is unaffected until a re-publish). `--on-conflict fail` aborts
on the first collision.

### Export

```bash
aracne export \
  --collection my-corpus \
  --output ./corpus.zip
```

Produces a ZIP with this layout:

```
my-corpus.zip
├── manifest.json    # collection metadata + per-doc fingerprints
└── documents/
    ├── doc1.xml
    └── ...
```

By default the export reflects the editor's **working tree** — what
they're actively editing, not what the public sees. Use
`--as-of YYYY-MM-DD` to walk the document-versioning history and
pick, per document, the most recent `publication`-origin row whose
`created_at <= as-of`:

```bash
aracne export \
  --collection my-corpus \
  --as-of 2026-04-01 \
  --output corpus-q1.zip
```

A document with no publication snapshot at or before the date is
skipped with a warning.

### JSON output

Every command supports `--json` to print machine-readable output for
CI/scripting use cases.

## Multiple deployments

Switch between Aracne2 instances with named profiles:

```bash
aracne login --profile work --host https://aracne.work.example
aracne login --profile home --host https://aracne.home.example

aracne whoami --profile work
aracne import --profile home --collection ...
```

`~/.aracne/config.toml` becomes:

```toml
[default]
host = "https://aracne.example.org"
token = "aracne2_pat_..."

[work]
host = "https://aracne.work.example"
token = "aracne2_pat_..."
```

## Tests

```bash
cd cli
pip install -e .[dev]
pytest
```

Tests use `httpx.MockTransport` and `respx`, no real backend required.
