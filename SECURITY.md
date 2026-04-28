# Security Policy

## Reporting a vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**
Public disclosure before a fix lands in `main` exposes every running
instance of the platform.

Send a private report to **alfredo.cosco@gmail.com** with:

- a description of the issue;
- the affected version (commit hash or tag);
- a minimal proof of concept, if possible;
- the impact you believe it has (data exposure, privilege escalation,
  DoS, etc.);
- whether you intend to publish a write-up, and if so on what date.

You should expect:

- an **acknowledgement within 7 days** that the report was received;
- an initial **triage within 14 days** with a planned fix timeline
  or a justification for not treating it as a vulnerability;
- a public credit in the release notes when the fix ships, unless
  you ask to remain anonymous.

The project is maintained by a single person on best-effort time;
realistic SLAs above are commitments, not aspirations.

## Supported versions

Aracne2 is a continuously-released codebase tracked via the `main`
branch. Security fixes land in `main` and are immediately available
to anyone who pulls. There are no separate LTS branches.

| Version  | Supported          |
| -------- | ------------------ |
| `main`   | :white_check_mark: |
| < `main` | :x:                |

If you run a pinned commit / tag, you are on your own for backports.
The deployment-rebuild path is fast (`git pull && make migrate &&
docker compose restart backend`); rolling forward is almost always
the right answer.

## Security review trail

Past security audits performed by the maintainer are committed under
[`docs/Security_review_*.md`](docs/). All findings have been
remediated; the files are kept as an audit trail.

## Out of scope

Reports about the following will be acknowledged but not treated as
vulnerabilities:

- Issues that require an attacker to already control the host or
  have a valid Admin session. Defense-in-depth fixes are welcome
  via normal PRs, but they aren't security advisories.
- Missing security headers on `/api/v1/health`, the OpenAPI docs
  endpoint, or other endpoints intentionally exposed for
  diagnostics — those endpoints are explicitly disabled in
  production via the `ENVIRONMENT=production` flag.
- Rate-limit values being "too low" for legitimate users.
  Tunable per-deployment.
- Self-XSS that requires the user to paste an attacker-supplied
  string into a privileged form on their own behalf.
