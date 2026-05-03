"""``privacy_dpia`` — privacy + Data Protection Impact Assessment.

Categories: ``core``, ``cts:R4`` (Confidentiality / Ethics).
Mixes platform-introspected fields (PII handled, retention, IP
hashing) with operator declarations (DPO contact, lawful basis,
takedown SLA).
"""

from app.plugins.policy_pages.platform import retention_defaults
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


def _pii_fields_handled() -> list[str]:
    """Return the canonical PII the platform stores. Hardcoded —
    the list does not change at runtime; updating it requires a
    code release."""
    return [
        "users.email",
        "sessions.ip_address (hashed in production)",
        "sessions.user_agent",
        "audit_log.ip_address (hashed in production)",
        "audit_log.user_agent",
        "audit_log.actor_username",
    ]


def _ip_hashing_status() -> str:
    """Production hashes IPs with the JWT_SECRET salt before the
    request_logger middleware writes them to the table. Reflected
    here as a static "yes" — the middleware is unconditional."""
    return "Yes — SHA-256 with JWT_SECRET salt, applied by RequestLoggerMiddleware in production"


TEMPLATE = PolicyTemplate(
    slug="privacy_dpia",
    title_key="policy.privacy_dpia.title",
    categories=("core", "cts:R4"),
    fields=(
        Field("pii_fields", "platform", source=_pii_fields_handled,
              label_key="policy.privacy_dpia.pii_fields"),
        Field("retention", "platform", source=retention_defaults,
              label_key="policy.privacy_dpia.retention"),
        Field("ip_hashing", "platform", source=_ip_hashing_status,
              label_key="policy.privacy_dpia.ip_hashing"),
        Field("data_controller", "text", required=True, localized=True,
              label_key="policy.privacy_dpia.data_controller"),
        Field("dpo_contact", "text", required=True,
              label_key="policy.privacy_dpia.dpo_contact"),
        Field("lawful_basis", "textarea", required=True, localized=True,
              label_key="policy.privacy_dpia.lawful_basis",
              hint_key="policy.privacy_dpia.lawful_basis_hint"),
        Field("takedown_sla_days", "integer", required=True, min=1, max=90,
              label_key="policy.privacy_dpia.takedown_sla_days"),
        Field("notes", "textarea", localized=True,
              label_key="policy.privacy_dpia.notes"),
    ),
    public_template="_default.md.j2",
)
