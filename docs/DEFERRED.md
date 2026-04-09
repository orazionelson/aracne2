# Deferred Implementations

Items that are architecturally sound but deliberately postponed.
Each entry explains **why** it is deferred and **what trigger** should
prompt revisiting it.

---

## 1. Async task queue (Celery / ARQ / Dramatiq)

**Why deferred**
The current stack has no message broker. Adding one (Redis + Celery worker)
doubles the number of services in docker-compose and introduces a new failure
mode. The first phases do not yet have operations that exceed ~1 s.

**What needs it**
- TEI schema validation at save time (can be slow on large documents)
- XSLT transformation on batch of documents
- Full collection export as ZIP
- Any operation triggered by a publication-state change that touches
  more than a handful of documents

**Trigger to implement**
First user-facing operation that blocks a request for more than 3 seconds,
or the first publication workflow endpoint.

**Preferred stack when the time comes**
ARQ (async-native, uses Redis, no Celery overhead) or Celery with Redis
broker. Worker runs as a separate Docker service. Task status tracked in
a `background_tasks` table (id, status, result, created_at, completed_at).

---

## 2. Plugin hot-reload (activate/deactivate without restart)

**Why deferred**
FastAPI does not support removing mounted routers at runtime. Implementing
hot-reload requires either: (a) a custom router that checks plugin status
on every request, or (b) a subprocess/worker model. Both add significant
complexity with no current use case — all plugins are currently native.

**Trigger to implement**
First non-native plugin that needs to be toggled in production without
a maintenance window.

---

## 3. Plugin data table

**Why deferred**
Non-native plugins with structured relational data need a place to store it
without owning Alembic migrations. A generic `plugin_data` table
`(plugin_id, entity_type, entity_id, data JSONB)` would serve this, but
no non-native plugin exists yet to justify it.

**Trigger to implement**
First non-native plugin that needs more than `system_settings` key-value pairs.

---

## 4. Collection ACL — multi-editor support

**Why deferred**
The current model uses a single `editor_id` on the `collections` table.
If future requirements call for multiple simultaneous editors on one
collection, a `collection_collaborators` table will be needed.

**Trigger to implement**
First explicit request for collaborative editing on a single collection.

---

## 5. TEI schema validation

**Why deferred**
Validating an XML document against TEI P5 requires loading the RelaxNG/XSD
schema (several MB), which is slow unless cached. Synchronous validation
at save time would block the HTTP worker for potentially > 5 s on large
documents. Needs the async task queue (item 1) as a prerequisite.

**Design note**
Use `lxml` (not `defusedxml` — defusedxml explicitly disables schema
validation). Validation runs in a background task; the document is saved
immediately with `validation_status = "pending"`, updated to `"valid"` or
`"invalid"` when the task completes. The user receives a notification
(via the existing notification system) on completion.

**Trigger to implement**
After the async task queue is in place and the document CRUD exists.

---

## 6. XSLT template management (Designer role)

**Why deferred**
The Designer role is defined in ACL but has no dedicated endpoints.
Managing XSLT templates requires: storage (filesystem or eXist-db),
versioning, and a frontend editor. It is a self-contained feature that
depends on the XML layer being in place first.

**Trigger to implement**
Phase 05+ — after document CRUD and collection management.

---

## 7. Document versioning

**Why deferred**
eXist-db has built-in versioning (versioning module), but enabling it
requires per-collection configuration. Whether to use eXist-db versioning
or a manual snapshot table in PostgreSQL is an open architectural decision.

**Open question**
- eXist-db versioning: automatic, no extra code, but opaque and hard to
  expose via API.
- PostgreSQL snapshot table: full control, queryable diff history, but
  requires storing XML blobs or diffs.

**Trigger to implement**
Phase 05+ — decide the approach when document CRUD is designed.

---

## 8. Full-text search across collections

**Why deferred**
eXist-db has native XQuery full-text search (KWIC, Lucene index).
PostgreSQL has `pg_trgm` (already installed) for user/metadata search.
Cross-layer search (metadata + document content in one query) requires
a coordination layer that does not yet have a use case.

**Trigger to implement**
When the first "search documents by content" endpoint is requested.

---

## 9. WebSocket / Server-Sent Events for real-time notifications

**Why deferred**
The current notification system is pull-based (frontend calls
`/notifications/unread-count` at boot). Real-time push requires either
WebSockets or SSE, both of which need connection state management and
are incompatible with simple horizontal scaling behind a load balancer
without a shared pub/sub layer (Redis).

**Trigger to implement**
When polling latency becomes a visible UX problem, or when the async
task queue (item 1) is in place and can publish events to a Redis channel.

---

## 10. Production hardening checklist

Items that must be completed before any public-facing deployment but are
out of scope during development phases:

| Item | Status | Notes |
|------|--------|-------|
| HTTPS enforcement | deferred | Uncomment HSTS header in nginx.conf |
| Content-Security-Policy | deferred | Header template exists in nginx.conf |
| Rate limit tuning | deferred | Current limits are defaults |
| `bcrypt_rounds` review | deferred | Default 12; increase to 14 for production |
| `ADMIN_PASSWORD` rotation policy | deferred | Document in ops runbook |
| Postgres connection pooling | deferred | Consider PgBouncer under load |
| eXist-db admin password rotation | deferred | Same var as backend — enforce secret manager |
| Log shipping | deferred | structlog JSON → ELK / Loki in production |
| Backup strategy | deferred | PostgreSQL dump + eXist-db backup API |

---

## 11. Email / external notification channels

**Why deferred**
The `notification_dispatcher` plugin currently writes only in-app
notifications. Email delivery requires an SMTP integration (or SES/Postmark)
and an email template system (HTML + plaintext). No email use case exists yet.

**Trigger to implement**
First user-facing flow that requires out-of-band notification:
password reset, publication approval, or account verification.

---

---

## 12. Full-collection validation — performance optimisation

**Current behaviour**
`_run_validation_task` runs entirely inside the FastAPI process on the main asyncio
event loop.  Each document is validated with `lxml` (CPU-bound) and fetched from
eXist-db (I/O-bound), but because `lxml` is synchronous it occupies the event loop
and degrades response times for all other requests during the run.

**Measured impact**
On a local setup with small collections (< 50 docs, simple schema) the slowdown
is perceptible but tolerable.  On collections of several hundred documents, or
with the full TEI All RelaxNG schema (≈ 5 MB), the validation of a single document
can take 1–3 s, making the entire application unresponsive for the duration.

**Optimisation options (in ascending complexity)**

| Option | Effort | Gain | Notes |
|--------|--------|------|-------|
| Offload `lxml` call to a thread pool with `asyncio.to_thread()` | Low | Medium | Keeps other coroutines running between docs; CPU cores still contend |
| Process pool via `concurrent.futures.ProcessPoolExecutor` | Medium | High | True parallelism; schema must be picklable or reloaded per worker |
| Dedicated async task queue (ARQ + Redis worker) | High | Very high | Worker process separate from the API; prerequisite: DEFERRED item 1 |
| Pre-parse and cache the schema object in the API process | Low | Medium | Amortises lxml schema loading (≈ 80 % of per-doc cost for large schemas) |

**Recommended short-term fix**
Wrap the `validate_xml()` call in `await asyncio.to_thread(validate_xml, xml_bytes, schema)`.
This alone is sufficient to keep the API responsive while the validation loop runs.
Schema caching (one `lxml.etree.RelaxNG` / `XMLSchema` instance per schema file,
invalidated on schema upload) multiplies the benefit.

**Trigger to implement**
First complaint about API unresponsiveness during a collection validation run in a
non-development environment.

*Last updated: 2026-04-08*

---

## 13. XSLT Designer — Phase D: AI sidebar nel CodeMirror

### Contesto e stato attuale

Il tab Document in `WebsitesView.vue` dispone ora (Phase C) di:

- Un editor CodeMirror 5 XML per la sorgente `custom` (modifica inline dell'XSLT).
- Un endpoint `POST /api/v1/websites/{slug}/preview-doc/{filename}` che applica
  l'XSLT salvato (o un override non salvato) a un singolo documento e restituisce
  il frammento HTML risultante.
- Un pannello iframe che mostra l'anteprima in tempo reale.

Phase D aggiunge una **sidebar AI** affiancata all'editor CodeMirror che consente
al Designer di descrivere in linguaggio naturale una trasformazione desiderata e
ricevere XSLT generato o modificato dall'IA.

---

### Funzionalità attese (Phase D)

1. **Prompt field + "Generate" button**
   Un campo testo nella sidebar accetta una descrizione in linguaggio naturale,
   ad esempio: *"Rendi il titolo un `<h1>` con classe `tei-title`, mostra autore in
   corsivo sotto, ometti tutto ciò che non è teiHeader o text/body"*.

2. **Modalità Generate vs. Refine**
   - *Generate*: la sidebar invia il prompt al backend; il backend chiama il modello
     AI e restituisce un XSLT completo da zero. L'output sostituisce il contenuto
     dell'editor CodeMirror.
   - *Refine*: il backend riceve sia il prompt sia l'XSLT attualmente nell'editor;
     il modello suggerisce modifiche mirate. L'output sostituisce o affianca
     (con diff highlight) il contenuto corrente.

3. **"Insert into editor"**
   L'utente può accettare la risposta (insert) o scartarla (keep current).
   L'editor CodeMirror riceve il nuovo valore via `xsltCm.setValue(newContent)`.

4. **Preview immediata**
   Dopo l'insert, il pulsante Preview nel pannello sottostante viene attivato
   automaticamente per verificare il risultato.

---

### Decisione aperta: integrazione AI

La questione centrale è **quale infrastruttura AI usare** e **come integrarla
nel backend**. Le opzioni sono due:

#### Opzione A — Stesso sistema dei Preset Prompts (endpoint `/ai/generate-xslt`)

Il backend espone un endpoint dedicato `POST /api/v1/ai/generate-xslt` con schema:

```json
{
  "description": "Descrizione in linguaggio naturale",
  "current_xslt": "... testo XSLT corrente, omettibile in modalità generate ...",
  "mode": "generate | refine"
}
```

Il backend:
1. Recupera la chiave API AI e il modello da `system_settings`
   (stessa voce usata dai Preset Prompts, es. `ai_model`, `ai_api_key`).
2. Costruisce il system prompt specializzato per XSLT
   (es. *"Sei un esperto di XSLT 1.0/2.0 e TEI P5. Restituisci solo il codice
   XSLT senza spiegazioni, completo e valido."*).
3. Chiama il provider AI (Anthropic o OpenAI a seconda della config) via `httpx`.
4. Restituisce `{ "data": { "xslt": "..." } }`.

**Pro:**
- Riuso dell'infrastruttura già pianificata per i Preset Prompts (stessa tabella
  `system_settings`, stesso pattern di chiamata, stessa ACL `[D+]`).
- Il backend è il solo a conoscere la chiave API — nessuna chiave esposta al frontend.
- Facilmente testabile (mock dell'endpoint AI nel test suite).

**Contro:**
- Richiede che il sistema dei Preset Prompts sia già implementato e che la
  configurazione AI (`ai_model`, `ai_api_key`, `ai_base_url`) sia disponibile in
  `system_settings`. Se non lo è, bisogna aggiungere quelle voci.

#### Opzione B — Nuovo endpoint specifico con propria configurazione

Un endpoint separato `POST /api/v1/websites/{slug}/xslt-ai-assist` che accetta
gli stessi parametri ma legge la propria config AI da un set dedicato di
`system_settings` (`xslt_ai_model`, `xslt_ai_api_key`, ecc.).

**Pro:**
- Disaccoppiato dal sistema dei Preset Prompts; può usare un modello diverso
  (es. un modello con context window più grande, adatto a documenti XML lunghi).
- Può essere abilitato/disabilitato indipendentemente.

**Contro:**
- Duplica la logica di chiamata AI.
- Introduce una seconda configurazione AI nella Settings UI.

#### Raccomandazione

**Preferire Opzione A**, con una piccola estensione: aggiungere un `system_settings`
specifico `xslt_ai_system_prompt` (tipo `text`) che il Designer può personalizzare
dalla Settings → Design tab, ma riusare il provider/modello/chiave già configurati.
L'endpoint `/ai/generate-xslt` è generico e parametrico: il system prompt viene
iniettato dal backend, non hardcoded.

Se al momento dell'implementazione i Preset Prompts non sono ancora operativi,
implementare la configurazione AI minima (`ai_provider`, `ai_api_key`, `ai_model`)
come `system_settings` e condividerla tra i due sistemi.

---

### Architettura frontend (Phase D)

**Nuovo componente**: `XsltAiSidebar.vue` (o integrazione diretta nel Document tab).

Struttura UI consigliata (pannello laterale a destra del CodeMirror, larghezza ~30%):

```
┌──────────────────────────────────────────────┐
│  AI XSLT Assistant                           │
│  ─────────────────────────────────────────   │
│  Mode: [● Generate] [○ Refine]               │
│                                              │
│  Describe the transformation:                │
│  ┌──────────────────────────────────────┐   │
│  │ <textarea rows=4>                    │   │
│  └──────────────────────────────────────┘   │
│  [Generate XSLT]                            │
│                                              │
│  ─── Result ────────────────────────────    │
│  <pre class="xslt-preview">...</pre>        │
│  [Insert into editor]  [Discard]            │
└──────────────────────────────────────────────┘
```

**Store change**: aggiungere `generateXslt(slug, description, currentXslt?, mode)` in
`stores/websites.ts`, oppure creare `stores/xslt_ai.ts` se la logica diventa ampia.

**Layout change in WebsitesView.vue**: quando source = `custom` e l'AI è disponibile,
il Document tab si divide in due colonne: editor CodeMirror a sinistra (70%),
sidebar AI a destra (30%). Su viewport stretto, la sidebar collassa sotto l'editor.

---

### Prerequisiti tecnici

| Prerequisito | Stato | Note |
|---|---|---|
| CodeMirror editor nel Document tab | ✅ Phase C | `xsltCm.setValue()` disponibile |
| Preview endpoint | ✅ Phase C | `POST /websites/{slug}/preview-doc/{filename}` |
| Sistema Preset Prompts / config AI | ❓ Da verificare | Necessario per Opzione A |
| `system_settings`: `ai_provider`, `ai_api_key`, `ai_model` | ❓ Da verificare | Verificare se già implementati |
| `system_settings`: `xslt_ai_system_prompt` | ❌ Non implementato | Aggiungere seed in `db/seed.py` |
| `XsltAiSidebar.vue` | ❌ Non implementato | Nuovo componente |
| `POST /api/v1/ai/generate-xslt` | ❌ Non implementato | Nuovo endpoint |

---

### Trigger per l'implementazione

Quando il Designer richiede attivamente la funzionalità AI, oppure quando il
sistema dei Preset Prompts è operativo e la configurazione AI è già in
`system_settings` — in quel caso l'effort di Phase D si riduce a:
1. Aggiungere un endpoint (≈ 60 righe Python).
2. Creare il componente `XsltAiSidebar.vue` (≈ 120 righe Vue).
3. Integrarlo nel layout del Document tab.

*Aggiunto: 2026-04-09*
