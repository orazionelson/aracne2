# Email notifications

Aracne2 can send transactional email at three workflow moments
and for the password-reset flow. Email is **off by default**: the
operator must explicitly turn it on, and every user can opt out
of the workflow emails individually.

## What can trigger an email

| Moment | Recipient | Subject (default) |
|---|---|---|
| You **submit a collection for review** | every active EditorInChief / Admin (except yourself) | *Collection submitted for review* |
| EditorInChief **requests revisions** | the editor assigned to the collection | *Revisions requested* |
| EditorInChief **publishes** the collection | the editor assigned to the collection | *Collection published* |
| Anyone uses **Forgot password?** | the user requesting the reset | *Reset your password* |

The actor is always excluded — clicking **Publish** never sends
yourself an email.

## Per-user opt-out

In your **Profile** there is a toggle:

> **Receive workflow email notifications**

Tick it off and you will stop receiving the three workflow
emails. The toggle does **not** affect the password-reset email —
that one always goes out when you click *Forgot password?*.

The default is on for new users. Existing users were defaulted to
on when the feature shipped; you can flip it any time.

## What the email contains

Every workflow email shows:

- who acted (the actor's display name)
- the collection title
- a clickable link to the collection (when the operator has set
  the public base URL)
- the EditorInChief's note when the email is "revisions
  requested" — that is the body of the message you will need to
  act on

The HTML version is a simple branded layout; a plaintext fallback
is attached for clients that do not render HTML.

## Languages

Each email is rendered in the recipient's preferred language
(English or Italian today). If your `preferred_lang` is something
else the deployment falls back to its `default_language` system
setting, then to English. The choice is per-recipient — an EiC who
prefers Italian gets the Italian version even if the editor who
acted speaks English.

## Operator setup

Email is opt-in at deployment time. To turn it on, the operator:

1. Starts the local Postfix container (it ships with the
   compose file under the `email` profile).
2. Configures the upstream relay inside the Postfix container
   (DKIM, TLS, sender domain — whatever the smarthost requires).
3. In **Admin → Settings → Email**:
   - flip `email_enabled` to `true`
   - set `email_from_address` (required)
   - optionally adjust `email_from_name`, `email_subject_prefix`,
     `email_smtp_host`, `email_smtp_port`

Aracne2 itself stores no SMTP credentials — the relay is reached
on the docker network without authentication, and Postfix takes
care of the queue, retry, and DKIM signing.

## Forgot password

The login screen shows **Forgot password?** below the form. It
opens a small page that asks for your email or username. The
platform always confirms the request was received (regardless of
whether the account exists, to prevent fishing for valid logins),
and an email arrives within a minute or two if the address is on
file.

The link in the email is **valid for 24 hours** and works **once**.
Clicking it opens a page where you set a new password; on success
you are redirected to the login screen and every previous session
of yours is logged out, so any device still holding an old token
is forced to sign in again.

If the email never arrives:

- Check that Admin has flipped `email_enabled` on (this is per
  deployment).
- Check the spam folder — first emails from a new domain often
  land there until DKIM/SPF are warmed up.
- Otherwise contact your Admin: there will be Postfix logs on
  the deployment side showing whether the email was queued.

---

Technical reference: [`docs/reference/EMAIL_CHANNELS.md`](../../docs/reference/EMAIL_CHANNELS.md).
