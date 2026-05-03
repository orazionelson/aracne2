# Webhooks — push-notify external systems

A **webhook** is a URL Aracne2 calls every time something
significant happens — a collection goes public, a document gets
uploaded, a user is created. Every time the event fires the
platform sends a small JSON HTTP POST to the URL you chose and
moves on; whatever lives at that URL decides what to do with the
news (rebuild a static index, ping a Slack channel, kick off a
Codeberg deploy, fan out to a queue, …).

Webhooks are the loose-coupling equivalent of the platform's
internal hook system: the same lifecycle events power both. Plugins
live inside Aracne2; webhooks reach outside of it.

Configuration: **`/admin/webhooks`**, Admin only.

## Quick start: 60 seconds to a working delivery

1. Open `/admin/webhooks` → **+ Nuovo webhook**.
2. Give it a label (e.g. *"Slack — published collections"*) and a
   destination URL.
3. Tick at least one event in the **Events** list.
4. *(Optional)* paste a shared secret for signature verification.
5. Save.
6. Click **Test** on the new row — Aracne2 sends a synthetic
   `test.ping` event to the URL and shows the resulting status code
   on the row. Anything in the 2xx range means delivery succeeded.

That's it. From now on every matching event triggers a real
delivery in the background.

## Supported events

| Event | Fires when |
|---|---|
| `collection.submitted` | An Editor submits a draft for review |
| `collection.published` | An EditorInChief / Admin publishes a collection |
| `collection.unpublished` | A previously-public collection is taken back to draft |
| `document.uploaded` | A new TEI file is added to a collection (or an existing file is replaced) |
| `document.deleted` | A TEI file is removed from a collection |
| `user.created` | A new user account is created (admin or self-registration) |

A webhook can subscribe to any non-empty subset; a single endpoint
typically takes either everything or one specific event.

The event list is fixed for the platform — you can't define new
event names from the admin UI. If you need something custom,
write a plugin (see the Plugins section in `docs/reference/`); the
webhook framework is deliberately a passive consumer of the
existing hook registry.

## The HTTP request

Every delivery looks like this:

```
POST <your-url>
Content-Type: application/json
User-Agent: Aracne2-Webhook/1.0
X-Aracne-Event: collection.published
X-Aracne-Signature: sha256=<hmac-hex>      ← only when a secret is set

{
  "event": "collection.published",
  "timestamp": "2026-04-27T10:14:23.881+00:00",
  "payload": {
    "collection_id": "5cb3...",
    "slug": "registrum-karoli-i",
    "title": "Registrum Karoli I",
    "is_public": true,
    "doc_count": 14,
    "status": "published",
    "published_at": "2026-04-27T10:14:23.450+00:00"
  }
}
```

For document-level events the payload also carries `"filename":
"R1.1.1.xml"`. For `user.created`, payload contains the username,
display name and role — never the password hash.

## Signing requests with a shared secret

When a `secret` is configured, Aracne2 computes
`HMAC-SHA256(secret, raw_body)` and ships the hex digest as the
`X-Aracne-Signature: sha256=<hex>` header. The receiving service
should:

1. Read the raw request body **before** any JSON parsing — the HMAC
   is computed over the bytes-as-sent, including any field ordering
   choices.
2. Compute the same HMAC with its copy of the secret.
3. Compare in constant time (`hmac.compare_digest` in Python,
   `crypto.timingSafeEqual` in Node).
4. Reject the request when they don't match.

A signature gives you tamper-evidence and proof-of-origin for free,
without TLS client certs or a per-request token. Use one whenever
the receiver isn't a server that you also operate.

The secret is stored plaintext on the platform side (Admin-only
table), and is never exposed in the API response — only a
`secret_set: true/false` flag is returned to the frontend. To
rotate, edit the endpoint and paste a new value.

## Delivery guarantees

The dispatcher tries hard to deliver but doesn't promise to. The
exact contract:

- **Up to 3 attempts** per event, with exponential backoff
  (immediate → 2s → 4s).
- **Network errors** (timeout, connection refused, DNS fail) are
  retried.
- **HTTP 4xx / 5xx** is *not* retried — the receiver gave a
  deterministic answer; spamming retries doesn't help.
- The per-attempt timeout is 10 seconds.
- Delivery is **fire-and-forget** from the editor's point of view:
  publishing a collection never waits for a webhook to ack.

The last attempt's outcome is persisted on the endpoint row and
shown in the admin list:

- `last_triggered_at` — the timestamp of the most recent attempt.
- `last_status_code` — the HTTP status code returned (or null on
  network failure).
- `last_error` — short error message when the delivery didn't
  succeed; cleared on the next successful attempt.

There is **no per-event delivery log** today — only the rolling
"latest outcome" row per endpoint. If your integration needs an
audit trail, log delivery on your side. (A historical log surface
is on the Future Ideas backlog — see `docs/TO_DO.md`.)

## SSRF protection

Webhook URLs are validated server-side against a small SSRF
denylist:

- Loopback (`127.0.0.0/8`, `::1`) and link-local
  (`169.254.0.0/16`) ranges are rejected.
- Private network ranges (`10.0.0.0/8`, `172.16.0.0/12`,
  `192.168.0.0/16`) are rejected unless the platform was
  explicitly configured to allow them (rarely useful in
  production).
- Only `http://` and `https://` schemes pass.

So you cannot accidentally point a webhook at the platform's own
internal services or someone else's intranet — every URL must
resolve to a public host. If you need on-prem reachability, run
the receiving service behind a proper public hostname (or a
tunnel like ngrok / Cloudflare Tunnel for development).

## Common recipes

### Slack notification on `collection.published`

Slack accepts inbound webhooks at `https://hooks.slack.com/services/...`,
which already speak JSON-on-POST. The body Aracne2 sends matches the
event shape, not Slack's expected format, so you'll need a tiny
proxy (a Cloudflare Worker, a `serverless` function, anything) that
takes our payload and re-shapes it into a Slack message. The proxy
URL is what you paste into the webhook's URL field.

Skip the secret when the proxy lives in the same trust boundary as
Slack itself; use one when it crosses the public internet.

### Trigger a static-site rebuild

If your published edition lives on a static host (Netlify, Cloudflare
Pages, GitHub Pages via Actions), the host already exposes a "build
hook" URL — a token-bearing URL that triggers a rebuild on POST.
Paste that URL into the webhook, subscribe to
`collection.published` and `document.uploaded`, and you're done:
every editorial change rebuilds the site in the background.

Most static-host build hooks accept the body as opaque — they don't
read our payload — so the signature is optional here.

### Mirror to an external search index

Subscribe to `document.uploaded` and `document.deleted`. Your
receiver pulls the full document from the platform's public API
(`/api/v1/public/collections/<slug>/documents/<filename>`,
content-negotiable to RDF/Turtle/JSON-LD) and pushes it into your
search backend. The webhook is the *trigger*; the platform stays
the *source of truth*.

### Health-monitor your own integrations

The **Test** button delivers a synthetic event and persists the
result. Hit it after every receiver deploy: a 200 means the
contract still holds, anything else means the integration broke
before any real event noticed.

## Troubleshooting

> Last status code is 401 / 403.

The receiver rejected the request because it expected
authentication. Either drop the auth on the receiver for this
endpoint, or move the auth to a request signature (`X-Aracne-
Signature`) — the receiver verifies the HMAC instead of trusting
a header that only Aracne2 might send.

> Last status code is null + last_error is "Request timed out".

The receiver isn't reachable, or it accepted the connection but
didn't respond within 10 seconds. Common causes: cold-start delays
on serverless functions (workaround: pre-warm the function on a
schedule), strict firewall rules, or a receiver that processes the
event synchronously instead of acking and queuing.

> The signature my code computes doesn't match Aracne2's.

Almost always a body-encoding issue. We HMAC the **raw bytes** of
the request body, before any framework re-serialises the JSON.
Make sure your receiver reads the body as bytes, not as a parsed
object. (In Express: `app.use(express.json({ verify: (req, _, buf) =>
{ req.rawBody = buf; }}))`. In FastAPI: `await request.body()`.)

> I want to know who triggered the publication that fired this event.

Webhook payloads are deliberately blast-radius-small — they carry
the *what*, not the *who*. If your integration needs the actor,
look it up by `collection_id` against the platform's audit log
(or, in the future, the admin audit-log view). Adding actor
metadata to webhook payloads is a deliberate non-feature: it
keeps the surface stable and avoids leaking PII to any receiver
that subscribes to a feed.

> I disabled an endpoint but it's still receiving events.

Check the `active` flag on the row — it's the master switch.
Inactive endpoints are skipped at dispatch time without any other
state being touched, so re-activating them resumes deliveries
without losing their secret or event subscriptions.
