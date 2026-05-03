# Command-line tool

Aracne2 ships with `aracne`, a small command-line tool you can run
on your laptop to **bulk-import** XML documents into a collection
and **export** an entire collection as a ZIP. Use it for the heavy
operations that would be tedious through the web UI — onboarding a
corpus from a directory of files, archiving a published state at a
given date, restoring a corpus on a fresh deployment.

The tool talks to the running Aracne2 deployment over HTTPS using
your account, authenticated by a **personal access token** (PAT).

## Installing the CLI

The tool lives inside the monorepo, in the `cli/` directory. It is
not on PyPI — Aracne2 deployments are invite-only and the install
step is:

```bash
git clone https://github.com/orazionelson/aracne2.git
cd aracne2
pip install -e cli/
```

That registers the `aracne` command on your PATH. Run
`aracne --version` to confirm.

You can also invoke it as `python -m aracne_cli` if the entry
point is not on your PATH (for example inside a virtualenv whose
`bin/` is not activated).

## Issuing a personal access token

1. Sign in to Aracne2 in your browser as your usual user
   (Editor or above — the API tokens card is hidden for
   level-1 Users).
2. Open your **Profile** (avatar in the top-right → Profile).
3. Scroll to the **API tokens** card.
4. Click **Issue token**, give it a label that helps future-you
   recognise the device (`my-laptop`, `home-mac`, …) and click
   **Create**.
5. Copy the plaintext shown in the panel that opens. **This is
   your only chance** — Aracne2 stores only a hashed digest, the
   plaintext is shown exactly once.

The new row appears in the table with "never used" until your
first CLI call against the host.

To revoke a token (lost laptop, contractor leaving, periodic
rotation), open the same **API tokens** card and click the trash
icon next to the row. The token is invalidated immediately.

## First run — `login` and `whoami`

Tell the CLI which deployment to talk to and paste the token:

```
$ aracne login --host https://aracne.example.org
Token: <paste the plaintext here, it will not be shown>
✓ Logged in as anna.bianchi (Editor)
Saved to ~/.aracne/config.toml
```

Verify the saved profile:

```
$ aracne whoami
anna.bianchi (Editor) @ https://aracne.example.org
```

The token is stored in `~/.aracne/config.toml` with permissions
`0600` (read/write for you, no one else).

### Multiple deployments

If you work on more than one Aracne2 instance, each gets its own
**profile**:

```
$ aracne login --host https://aracne.work.example --profile work
$ aracne whoami --profile work
```

Every command takes `--profile NAME` (default `default`).

## Bulk-uploading documents — `import`

Drop your `*.xml` files into a single directory, then point the
CLI at it:

```
$ aracne import \
    --collection my-corpus \
    --dir ./tei-files
```

What happens:

- The CLI checks every filename against the same rule the web UI
  enforces (`^[a-zA-Z0-9][a-zA-Z0-9_\-]*\.xml$`). Files with
  invalid names fail fast on the client.
- For each file it asks the server whether the filename already
  exists in the target collection.
- Existing files are **skipped** by default (`--on-conflict skip`).
  Pass `--on-conflict overwrite` to replace them, or
  `--on-conflict fail` to abort the whole run on the first
  conflict.
- Up to 4 uploads run in parallel (tune with
  `--concurrency 1..16`).

A progress bar shows live throughput. At the end the CLI prints a
summary like:

```
OK: 142, skipped: 8, failed: 0
```

The default skip behaviour makes the command **safe to re-run**
on the same directory — useful when only a handful of files have
changed and you want to upload the new ones without thinking
about which.

## Exporting a collection — `export`

### Working tree (what you see in the editor)

```
$ aracne export \
    --collection my-corpus \
    --output corpus.zip
```

Each document is downloaded **at its current state**, even if the
collection is published — the CLI authenticates as you, so it sees
your working tree (which may have unpublished edits in it).

### A specific past publication — `--as-of`

```
$ aracne export \
    --collection my-corpus \
    --as-of 2026-04-01 \
    --output corpus-q1.zip
```

For each document the CLI walks the publication history and picks
the latest version published **on or before** the date. Documents
that did not exist (or had never been published) at that date are
**skipped** with a warning — the manifest records the skip
reason.

You can pass either a plain date (`YYYY-MM-DD`, treated as UTC
midnight) or a full ISO-8601 timestamp (`2026-04-01T15:00:00Z`).

### What's inside the ZIP

```
my-corpus.zip
├── manifest.json
└── documents/
    ├── letter_001.xml
    ├── letter_002.xml
    └── …
```

The `manifest.json` records the export date, the `--as-of`
timestamp (or `null` for working-tree exports), the collection
identity, and one entry per document with its `version_number`,
the SHA-256 of the body, and any skip reason. Useful for fixity
checks when restoring on a fresh deployment.

## Output for scripts

Every command takes a `--json` flag that prints a single
machine-readable object instead of the friendly progress bar.
Convenient for cron jobs, CI pipelines, and ad-hoc shell scripts.

## Quick reference

```
aracne login   --host URL [--profile NAME] [--json]
aracne whoami  [--profile NAME] [--json]
aracne import  --collection SLUG --dir PATH
               [--on-conflict skip|overwrite|fail]
               [--concurrency N] [--profile NAME] [--json]
aracne export  --collection SLUG --output PATH.zip
               [--as-of DATE] [--concurrency N]
               [--profile NAME] [--json]
```

## Tips and pitfalls

- **Treat the token like a password.** Anyone who has the
  plaintext can act as you against that deployment until you
  revoke it.
- **One token per device** is the cleanest pattern: if you lose
  one, you revoke just that one without breaking the others.
- **`import` is not transactional**: if it fails halfway through,
  some files are uploaded, some are not. Re-run with the default
  `--on-conflict=skip` to upload only what's missing.
- **`--as-of` is per-document**: a collection that grew over time
  exports a coherent snapshot at the requested date even if some
  documents did not yet exist (those are skipped with a warning,
  not a failure).
- The CLI talks to the **public** API of the deployment — no
  special network setup needed beyond a working HTTPS connection.

---

Technical reference: [`docs/reference/CLI.md`](../../docs/reference/CLI.md).
