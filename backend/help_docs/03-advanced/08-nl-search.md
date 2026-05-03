# Natural-language search

Aracne2 ships a public, chat-style search experience as an opt-in
plugin called **`nl_search`**. Visitors type a question; the
assistant runs a small set of read-only tools against your published
corpus and returns a synthesised answer with **citations to real
documents** — no hallucinated URLs, no invented filenames.

It lives at `/search-nl` on your deployment. Once enabled, it can
also be surfaced as a tile on the public homepage.

## Two audiences

This page covers both:

- **Setting it up** — for the Admin (configure provider, corpus,
  budget, public link).
- **Using it** — for the visitor (what to type, what to expect).

---

## Setting it up (Admin)

### 1. Activate the plugin

In **Admin → Plugins**, find **Natural-language search** in the list
and click **Activate**. The page does not require a restart.

After activation, the page `/search-nl` is reachable, but you should
**not** advertise it yet — you still need a corpus and a working
provider.

### 2. Choose a provider

In **Admin → Settings → NL search**:

| Setting | What it does | Recommended start |
|---|---|---|
| **Provider** | `ollama` or `anthropic` | `ollama` (local, $0 cost) |
| **Model** | The provider-specific model id | `llama3.1` (Ollama) or `claude-sonnet-4-6` (Anthropic) |
| **API key** | Cloud provider key (Anthropic) | Empty when using Ollama |

**Ollama** runs locally on your server — no cloud, no per-query
cost. Simplest starting point for a private deployment.

**Anthropic** is the cloud alternative — better answers in many
cases, but billed per token. Only choose this if you have a budget
and an API key ready.

### 3. Pick a corpus

The plugin exposes one MCP **corpus** to the public. A corpus is a
named set of collections you have already grouped under
**Admin → Corpora** (this is the same primitive the MCP server uses
for editor integrations).

In **Admin → Settings → NL search → Corpus**, paste the UUID of the
corpus you want to expose. Until this is set, visitors will see a
"the administrator has not selected a corpus" message instead of
results.

### 4. Set a daily budget

The **Daily budget (EUR)** setting (default `2.00`) caps spend per
calendar day for cloud providers. When exceeded the endpoint
returns a "budget exhausted" message until the next day. For
Ollama this is informational — the budget table tracks volume but
not cost.

Set it to a number you are comfortable losing in a worst case.
Better to be conservative and raise it later.

### 5. (Optional) Tune the safety knobs

| Setting | Default | When to change |
|---|---|---|
| **Require login** | `true` | Flip off to allow anonymous access — only after the rest of the configuration is solid |
| **Max concurrent** | `2` | Raise if your server is beefy and you want more parallel queries |
| **Query timeout (s)** | `30` | Bump only if you are seeing legitimate timeouts on long answers |
| **Cache TTL (min)** | `60` | The same question within this window replays the cached answer — no LLM round-trip |
| **Max input chars** | `500` | Raise if your audience asks long questions; keep low to avoid prompt injection surface |
| **Max tool rounds** | `6` | Raise only if the assistant routinely runs out of rounds before answering |

### 6. Show the public link (optional)

By default, even a fully-configured plugin does not appear on the
public home page. To surface it:

1. Open **Public Pages → Pagine → Plugin links**.
2. Flip the toggle next to **Natural-language search**.

A tile labelled *"Cerca in linguaggio naturale"* (or the language-
matched English version) appears below the homepage cover text. The
direct URL `/search-nl` works regardless of this toggle.

See [Plugin links on the public site](/help/page?path=04-publishing/07-plugin-links)
for the full picture of the plugin-links surface.

---

## Using it (visitor)

The page is a single textbox: type a question in your own language
and press **Ask**.

### What you'll see

While the assistant works:

- A *"Thinking…"* hint appears as soon as you submit.
- *"Querying tool: search_entities…"* and similar hints flash by
  while the assistant inspects the corpus.
- The answer streams in word-by-word as the assistant writes it.

When the answer is complete:

- A **Citations** strip appears below, listing the documents the
  assistant actually consulted. Each citation links straight to the
  public page of that document.

### What the assistant will and won't do

**Will**:

- Answer in the language you used.
- Quote sparingly and paraphrase precisely.
- Say *"the corpus does not cover this question"* when it cannot
  answer confidently from the documents it could read.
- Cite only documents it actually retrieved during this search.

**Won't**:

- Invent slugs, filenames, or excerpts. Citations to documents the
  assistant didn't actually read are silently dropped before you
  see them.
- Volunteer information from outside the corpus.
- Address you in a marketing tone — the corpus speaks, not the
  assistant.

### When something goes wrong

| Banner | What it means |
|---|---|
| *"The daily budget has been used up"* | Wait until tomorrow, or ask the administrator to raise the cap. |
| *"The assistant is busy"* | Server reached `Max concurrent`; retry in a moment. |
| *"The AI provider could not be reached"* | The deployment's provider configuration is wrong or the cloud service is down. Contact the administrator. |
| *"An administrator has not selected a corpus yet"* | The plugin is active but no corpus has been chosen — administrator action needed. |
| *"Sign in to use natural-language search"* | This deployment requires login for NL search. |
| *"Too many questions in a short time"* | Per-IP rate limit (3/min, 30/day for anonymous). Wait a moment and try again. |

---

## Tips for editors and admins

- **Start small**: try Ollama first against a single test corpus
  before enabling Anthropic on your real archive.
- **Short questions get better answers**: a 20-word question runs
  cheaper and produces tighter citations than a 200-word essay.
- **Watch the citations**: if you read the cited document and the
  answer doesn't match, that's a signal to refine the system prompt
  (or to switch model).
- **Cache hits are free** (no LLM round-trip, no spend, no
  concurrency slot consumed). The 60-minute default TTL is a good
  starting point — raise it for slowly-changing corpora.
- The plugin is **off by default** after a fresh install. A new
  Admin who deploys Aracne2 sees nothing about NL search until they
  consciously activate it.

---

Technical reference: [`docs/reference/NL_SEARCH.md`](../../docs/reference/NL_SEARCH.md).

Related: [Plugin links on the public site](/help/page?path=04-publishing/07-plugin-links),
[MCP server](/help/page?path=03-advanced/07-mcp-server).
