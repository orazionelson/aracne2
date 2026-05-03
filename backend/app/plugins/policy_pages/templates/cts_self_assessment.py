"""``cts_self_assessment`` — CTS Core Trust Seal self-assessment.

Categories: ``cts:meta``. The most institutional-heavy template:
operator answers each of the 16 R-requirements with their own
declaration; the platform contributes a one-line "what the
platform provides" paragraph alongside each, sourced from
``CTS_COMPLIANCE_ROADMAP.md``.

For v1 the platform-side text is hardcoded here as a static
string per requirement. A future enhancement could parse the
roadmap markdown at runtime to keep the two in sync without code
duplication; for now the operator can edit the static text in
this file when the roadmap shifts.
"""

from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


def _platform_for(req: str) -> str:
    """Static one-liners summarising the platform's CTS contribution.

    Mirrors the "Platform contribution" column of the
    CTS_COMPLIANCE_ROADMAP summary table as of M2 close.
    """
    return _PLATFORM_TEXT.get(req, "(neutral — institutional declaration)")


_PLATFORM_TEXT: dict[str, str] = {
    "R1":  "Platform-neutral; mission is the institutional declaration.",
    "R2":  "License catalogue, per-collection assignment, LOD/OAI-PMH exposure.",
    "R3":  "Multi-target deposit (Zenodo / IA / Codeberg / GH / GL / Dataverse) + static export + native backup + headless ``aracne-cli export --as-of <date>``.",
    "R4":  "GDPR primitives: PII fields, retention defaults, IP hashing in production. Self-service export/delete planned.",
    "R5":  "Platform-neutral; institutional declaration.",
    "R6":  "Platform-neutral; institutional declaration.",
    "R7":  "TEI validation + audit log + role gating + signed JWT + ``document_versions`` + fixity layer (``fixity_records`` re-check + drift report) + ``/admin/audit-log`` admin UI.",
    "R8":  "Platform-neutral; institutional declaration.",
    "R9":  "Storage architecture in ``OPERATIONS.md`` + per-deployment storage policy template (this plugin).",
    "R10": "Format-as-preservation (TEI) + multi-deposit; preservation plan template (this plugin).",
    "R11": "Schema validation + workflow review + entity normalisation + bibliography normaliser.",
    "R12": "Workflow states + audit log + deposit hooks + in-app notifications + email dispatcher.",
    "R13": "OAI-PMH + sitemap + JSON-LD + DOI via Zenodo + 12 authority lookups.",
    "R14": "License exposure + raw TEI + JSON-LD + DOI + embed widget + MCP server.",
    "R15": "TEI / REST / OAI-PMH / JSON-LD / Docker; open source; monitoring.",
    "R16": "Six security reviews + defusedxml + HSTS/CSP + bcrypt + Fernet + ACL + Dependabot + bcrypt-hashed Personal Access Tokens + password reset flow.",
}


def _fields_for_requirement(req: str) -> tuple[Field, ...]:
    """Return three fields per requirement: the platform line and
    two operator declarations (institutional declaration + evidence
    pointer)."""
    return (
        Field(
            f"{req}_platform", "platform",
            source=lambda r=req: _platform_for(r),
            label_key=f"policy.cts_self_assessment.{req}_platform",
        ),
        Field(
            f"{req}_declaration", "textarea", required=True, localized=True,
            label_key=f"policy.cts_self_assessment.{req}_declaration",
        ),
        Field(
            f"{req}_evidence", "textarea", localized=True,
            label_key=f"policy.cts_self_assessment.{req}_evidence",
            hint_key="policy.cts_self_assessment.evidence_hint",
        ),
    )


_REQS: tuple[str, ...] = tuple(f"R{i}" for i in range(1, 17))


TEMPLATE = PolicyTemplate(
    slug="cts_self_assessment",
    title_key="policy.cts_self_assessment.title",
    categories=("cts:meta",),
    fields=tuple(
        f for r in _REQS for f in _fields_for_requirement(r)
    ),
    public_template="_default.md.j2",
)
