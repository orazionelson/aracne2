# MCP server

The **Model Context Protocol** (MCP) is a standardised way for assistants like
Claude Desktop, Cursor, and Claude Code to read external data. Aracne2 exposes
itself as an MCP server so an editor can ask Claude *"riassumi le tragedie del
corpus shakespeariano"* and have the answer based on real TEI documents
instead of guesses.

This page explains:

1. how the access model works (corpus + bearer token)
2. how an Admin sets it up
3. how an Editor configures Claude Desktop
4. what tools and resources the server exposes

The MCP server is **read-only** in this version. It cannot publish, edit, or
delete anything — it only surfaces collections that are already public on the
website.

## Access model — corpus + token

The MCP server never exposes the entire instance. Access is scoped through
two primitives:

- a **corpus** is a thematic grouping of public, published collections —
  e.g. `Shakespeare` aggregates `hamlet-folio`, `macbeth-quarto`,
  `lear-tragedy`. Corpora are managed under
  [Administration → Corpora](#).
- an **MCP token** is a bearer string issued for a single corpus. Editor
  Alice receives a token for the `Shakespeare` corpus; editor Bob receives a
  separate token for `Sommaria`. They paste the matching token into Claude
  Desktop and chat — the server filters every read to the matching corpus,
  so Bob's questions never see Alice's documents and vice versa.

The token is also a small isolation tool against domain confusion: when an
LLM analyses *"all the persons mentioned"* across an instance that hosts
both medieval charters and Shakespeare drama, the results blend the two —
useless to either editor. Per-corpus tokens prevent that mix.

If an instance hosts a single domain (most deployments) the workflow is
trivial: one corpus called e.g. `main` containing every public collection,
one token per editor.

## Admin: how to set it up

1. Open `Administration → Corpora` (Admin role required).
2. Click **New corpus**, give it a name and description, tick the public
   collections that belong to it. Save.
3. In the corpus detail panel, scroll to **MCP tokens** → enter a label
   ("Alice — personal laptop") → click **Issue token**.
4. A modal shows the plaintext bearer token **once** plus a Claude Desktop
   `mcpServers` snippet pre-filled with the instance URL. Copy both and send
   them to the editor through a secure channel (Signal, internal vault).
   Closing the modal makes the plaintext unrecoverable; you can only revoke
   and re-issue.
5. The plugin **MCP Server** must be active under `Administration → Plugins`
   for the endpoint to respond. Activation hot-mounts the route — no
   restart.

When you add a new collection to a corpus, every existing token starts
seeing it on the next request — no token rotation needed.

When an editor leaves the project, revoke their token from the same panel.
Revocation is instantaneous.

## Editor: how to plug it into Claude Desktop

You need: the **bearer token** and the **snippet** the Admin sent you.

1. Quit Claude Desktop.
2. Open `claude_desktop_config.json`:
   - macOS — `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows — `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux — `~/.config/Claude/claude_desktop_config.json`
3. Paste the snippet inside the file. If a `mcpServers` block already
   exists, merge the `aracne2` entry into it.

   The snippet looks like this (already filled with your instance URL and
   token):

   ```json
   {
     "mcpServers": {
       "aracne2": {
         "url": "https://your-aracne2.example/api/v1/mcp",
         "headers": {
           "Authorization": "Bearer aracne2_mcp_..."
         }
       }
     }
   }
   ```

4. Save the file and start Claude Desktop.

## Editor: Cursor

Cursor reads MCP servers from `~/.cursor/mcp.json` (the location is the
same on macOS / Linux / Windows — Cursor expands `~` to the user's
home). The schema is identical to Claude Desktop's:

```json
{
  "mcpServers": {
    "aracne2": {
      "url": "https://your-aracne2.example/api/v1/mcp",
      "headers": {
        "Authorization": "Bearer aracne2_mcp_..."
      }
    }
  }
}
```

After saving, restart Cursor. You can verify the server is reachable
in `Settings → MCP` — Aracne2 should appear with a green dot. From the
Composer panel, the assistant can now use the same tools described
below.

## Editor: Claude Code (CLI)

Claude Code reads its config from `~/.claude.json` (or per-project
`.claude/settings.json`). For an HTTP-streamable MCP server like
Aracne2, the entry goes in the `mcpServers` block:

```json
{
  "mcpServers": {
    "aracne2": {
      "type": "http",
      "url": "https://your-aracne2.example/api/v1/mcp",
      "headers": {
        "Authorization": "Bearer aracne2_mcp_..."
      }
    }
  }
}
```

The `"type": "http"` field is what tells Claude Code to use the
Streamable-HTTP transport (instead of the default stdio child-process
mode used by local MCP servers). No restart is required — Claude Code
re-reads the config at the start of every conversation.

In a Claude Code session you can confirm the server is wired up with:

```bash
claude mcp list   # should include "aracne2" as connected
```

In any new conversation you can now ask things like:

- *"List the collections in this corpus and their publication dates."*
- *"Find every persName occurrence of 'Hamlet' and show the surrounding context."*
- *"Summarise the description of the macbeth-quarto collection."*
- *"Open the document hamlet-act1-scene1.xml and show me lines 1–40."*

Claude will pick the right tool from the list, call it, and use the result
to answer.

## What the server exposes

Tools (callable actions):

| Tool | What it does |
|---|---|
| `list_collections` | Page through the corpus's collections (slug, title, description, date). |
| `get_collection` | Single-collection detail: license, schema, document count, editor display name. |
| `list_documents` | Filenames inside a collection, paged. |
| `get_document_source` | Raw TEI XML for one filename. Capped at 2 MB; the response carries a hint when truncated. |
| `tei_to_text` | Strip TEI markup and return the body text. Uses much less LLM context than `get_document_source` when the assistant only needs the prose. |
| `search_entities` | Free-text search of the named-entities index, restricted to the corpus. |
| `find_entity_occurrences` | Document occurrences of one entity, with surrounding context. |
| `lookup_authority` | Resolve a name through Wikidata / ORCID / ROR / VIAF and return canonical id + URI. Useful when the entity is not yet indexed in the local instance. |

Resources (linkable URIs):

| Scheme | What it returns |
|---|---|
| `corpus://<name>` | Markdown manifest of the bearer's corpus (member collections). The bearer's own corpus is also pre-listed in `resources/list` so the LLM finds it without a tool call. |
| `collection://<slug>` | Markdown summary of the collection. |
| `document://<slug>/<filename>` | Raw TEI for one document (size-capped). |
| `entity://<uuid>` | Canonical form, type, and authority URI of one entity. |

### Why there is no `summarize_collection` tool

By design. The MCP client *is* an LLM — it's already capable of
producing a summary once it has read the source material. Adding a
server-side summariser would mean either:

- duplicating the platform's AI rate-limit / audit pipeline for a
  bearer-token context (which has no real `User` row behind it), or
- bypassing the audit trail entirely.

Both have downsides. The current design lets the LLM client read the
collection metadata (`get_collection`) and a sample of documents
(`list_documents` + `tei_to_text`) and write the summary itself, in
the same conversation, with the same model the user already pays
for. No round-trip to the server's own AI infrastructure, no double
audit.

Every tool intersects its query with two filters:

- the collection must be **public AND published** (same gate as the public
  website);
- the collection must belong to the **token's corpus**.

A token whose corpus is empty therefore sees an empty response everywhere —
no error, no leak.

## Operational notes

- Each request is rate-limited to 60 per minute per token.
- The plugin records `last_used_at` on the token so an Admin can spot stale
  tokens at a glance.
- Tokens are bcrypt-hashed at rest. The plaintext value is never stored —
  only its hash. Revocation = setting the `revoked_at` column; rows are
  never hard-deleted, so the audit trail survives rotation.
- The transport is **MCP Streamable HTTP** (single POST endpoint at
  `/api/v1/mcp`). It is JSON-RPC 2.0 over HTTP — Claude Desktop, Cursor,
  and Claude Code all support it natively.
- Future versions may expose write tools (e.g. `crossref_to_tei`,
  `import_from_zotero`) gated behind a separate per-corpus toggle. The
  current Phase-1 scope is intentionally read-only so a misbehaving LLM
  cannot mutate the platform.
