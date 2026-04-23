# Logging in and your profile

## Logging in

Navigate to the Aracne2 URL provided by your system administrator. Enter
your email (or username) and password. Your session is maintained
automatically — you do not need to log in again until the session
expires (typically 60 minutes of inactivity, extended automatically when
you are active).

If you forget your password, use the "Forgot password" link on the login
page; Aracne2 will email you a one-time reset link.

## Your profile

Click your name or avatar at the bottom of the left sidebar to open the
profile page. From there you can:

- Change your display name
- Change your password
- Switch the interface language (Italian or English)
- Set your **ORCID iD** (if you have one)

Your language preference is saved and applied automatically every time
you log in.

### About the ORCID iD

ORCID is an international registry of persistent identifiers for
researchers. Set yours once in the profile page and Aracne2 will use it
automatically wherever your authorship is declared:

- Public collection and document pages show a clickable ORCID link next
  to your display name.
- RDF / Linked Open Data output (JSON-LD, schema.org, Dublin Core)
  emits `schema:sameAs` pointing at your ORCID record.
- If the Zenodo deposit plugin is active, your ORCID is attached to the
  `creators` entry on every record deposited for a collection you
  edited.

Expected format: `0000-0002-1825-0097` (the hyphenated short form). The
form accepts the full URL too (`https://orcid.org/0000-…`) and stores
the short form. The checksum is validated before saving — a typo in the
last digit is rejected immediately.

If you do not have an ORCID, leave the field empty: nothing downstream
breaks, the public pages simply show your name without a link.
