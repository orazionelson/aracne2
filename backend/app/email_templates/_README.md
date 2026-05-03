# Email templates

Each event has a directory tree:

```
{event_name}/
  {lang}/
    subject.txt   # one-line subject; rendered without autoescape
    body.html     # HTML body; rendered with autoescape ON
    body.txt      # plaintext body; rendered without autoescape
```

`{lang}` is one of `en`, `it`. The renderer
([`services/email.py:render`](../services/email.py)) falls back to the
platform's `default_language` system setting when the user's
`preferred_lang` does not have a matching directory.

Context variables are documented per-event inline in each `body.html` /
`body.txt`. The `_stub` event under this directory is used by the
infrastructure tests in `app/tests/test_email_infrastructure.py` only —
it is not wired to any hook.

Phase EM-B will add real templates for the three workflow events
(`collection_submitted`, `collection_rejected`, `collection_published`).
Phase EM-C adds `password_reset`.
