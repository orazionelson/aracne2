import asyncio
import shutil
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.models.ai_prompt import AiPrompt
from app.models.body_template import BodyTemplate
from app.models.license import License
from app.models.role import Role, UserRole
from app.models.session import Session  # noqa: F401 — ensure model is registered
from app.models.system_setting import SystemSetting
from app.models.tei_schema import SchemaFormat, TeiSchema
from app.models.user import User

# Path to bundled TEI schemas shipped with the application.
_BUNDLED_SCHEMAS_DIR: Path = Path(__file__).parent.parent / "tei_schemas"

logger = structlog.get_logger()

ROLES: list[tuple[str, str]] = [
    ("Admin", "Full platform access"),
    ("EditorInChief", "Manages collections and publication workflow"),
    ("Designer", "Manages XSLT templates and CSS themes"),
    ("Editor", "Creates and edits documents"),
    ("User", "Read-only access to published content"),
]

DEFAULT_SETTINGS: list[tuple[str, str, str]] = [
    ("platform_name", settings.platform_name, "string"),
    ("default_language", "it", "string"),
    ("jwt_access_expiry_min", str(settings.jwt_access_expiry_minutes), "int"),
    ("jwt_refresh_expiry_days", str(settings.jwt_refresh_expiry_days), "int"),
    ("public_registration", str(settings.public_registration).lower(), "bool"),
    ("bcrypt_rounds", str(settings.bcrypt_rounds), "int"),
    ("max_upload_size_mb", str(settings.max_upload_size_mb), "int"),
    ("search_results_per_page", "10", "int"),
    ("audit_log_retention_days", "90", "int"),
    ("expired_sessions_retention_days", "30", "int"),
    ("zip_max_size_mb", "50", "int"),
    ("zip_max_extracted_mb", "200", "int"),
    ("zip_max_files", "500", "int"),
    ("media_max_upload_size_mb", "50", "int"),
    ("platform_logo_url", "/aracne-logo.png", "string"),
    ("navbar_bg_color", "#1e40af", "string"),
    ("public_home_enabled", "false", "bool"),
    ("home_show_collections", "true", "bool"),
    ("home_show_search", "true", "bool"),
    ("home_show_login_button", "true", "bool"),
    ("home_propagate_css", "false", "bool"),
    ("evt_enabled", "false", "bool"),
    # AI integration settings (encrypted values are written empty; Admin fills them).
    ("ai_provider", "disabled", "string"),
    ("ai_openai_api_key", "", "string"),
    ("ai_openai_model", "gpt-4o", "string"),
    ("ai_anthropic_api_key", "", "string"),
    ("ai_anthropic_model", "claude-opus-4-6", "string"),
    ("ai_gemini_api_key", "", "string"),
    ("ai_gemini_model", "gemini-1.5-pro", "string"),
    ("ai_max_requests_per_hour", "20", "int"),
    ("ai_privacy_warning_enabled", "false", "bool"),
    # Dynamic/Hybrid website caching
    ("dynamic_cache_ttl", "300", "int"),
    # Named entity index: TEI tag names to extract (JSON array of strings).
    # The tag name is used directly as the entity type stored in the DB.
    ("entity_index_tags", '["persName","placeName","orgName"]', "string"),
]

# Default Creative Commons licenses (name, target).
# All are seeded as active. Admins can add, edit or deactivate them.
DEFAULT_LICENSES: list[tuple[str, str]] = [
    (
        "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    ),
    (
        "Attribution 4.0 International (CC BY 4.0)",
        "https://creativecommons.org/licenses/by/4.0/",
    ),
    (
        "Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)",
        "https://creativecommons.org/licenses/by-sa/4.0/",
    ),
    (
        "Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)",
        "https://creativecommons.org/licenses/by-nc/4.0/",
    ),
    (
        "Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)",
        "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    ),
    (
        "Attribution-NoDerivatives 4.0 International (CC BY-ND 4.0)",
        "https://creativecommons.org/licenses/by-nd/4.0/",
    ),
    (
        "Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)",
        "https://creativecommons.org/licenses/by-nc-nd/4.0/",
    ),
]


async def seed_roles(db: AsyncSession) -> None:
    for name, desc in ROLES:
        exists = await db.scalar(select(Role).where(Role.name == name))
        if not exists:
            db.add(Role(name=name, description=desc))
    await db.flush()
    logger.info("seed_roles_done")


async def seed_settings(db: AsyncSession) -> None:
    for key, value, type_ in DEFAULT_SETTINGS:
        exists = await db.get(SystemSetting, key)
        if not exists:
            db.add(SystemSetting(key=key, value=value, type=type_))
    await db.flush()
    logger.info("seed_settings_done")


async def seed_licenses(db: AsyncSession) -> None:
    """Seed default Creative Commons licenses if not already present (matched by name)."""
    for name, target in DEFAULT_LICENSES:
        exists = await db.scalar(select(License).where(License.name == name))
        if not exists:
            db.add(License(name=name, target=target, is_active=True))
    await db.flush()
    logger.info("seed_licenses_done")


DEFAULT_BODY_TEMPLATES: list[tuple[str, str]] = [
    (
        "generic",
        "<docDate>\n  <date>YYYY-MM-DD</date>\n</docDate>\n"
        "<div type=\"protocollo\"/>\n"
        "<div type=\"testo\"/>\n"
        "<div type=\"escatocollo\"/>",
    ),
    (
        "epistola",
        "<docDate>\n  <date/>\n</docDate>\n"
        "<div type=\"inscriptio\"/>\n"
        "<div type=\"rubrica\"/>\n"
        "<div type=\"salutatio\"/>\n"
        "<div type=\"exordium\"/>\n"
        "<div type=\"narratio\"/>\n"
        "<div type=\"petitio\"/>\n"
        "<div type=\"conclusio\"/>",
    ),
]


async def seed_body_templates(db: AsyncSession) -> None:
    """Seed default body templates if not already present (matched by label)."""
    for label, snippet in DEFAULT_BODY_TEMPLATES:
        exists = await db.scalar(select(BodyTemplate).where(BodyTemplate.label == label))
        if not exists:
            db.add(BodyTemplate(label=label, snippet=snippet, is_native=True))
    await db.flush()
    logger.info("seed_body_templates_done")


# slug, label, description, template, context_vars, target_context
DEFAULT_AI_PROMPTS: list[tuple[str, str, str, str, list[str], str | None]] = [
    (
        "validate_errors_explain",
        "Explain validation errors",
        "Analyzes XML validation errors and explains how to fix each one.",
        (
            "You are a TEI P5 XML expert. Analyze the following validation errors "
            "and explain clearly and concisely how to fix each one.\n\n"
            "File: {filename}\n"
            "Schema: {schema}\n\n"
            "Validation errors:\n{errors}"
        ),
        ["filename", "schema", "errors"],
        "validation",
    ),
    (
        "document_edit_suggest",
        "Suggest TEI encoding improvements",
        "Reviews a selected XML fragment and suggests improved TEI P5 encoding.",
        (
            "You are a TEI P5 XML expert. Review the following XML selection "
            "and suggest improvements to the TEI encoding. "
            "Return ONLY the corrected XML, with no explanations, no markdown, "
            "no code fences, no ``` delimiters — raw XML only.\n\n"
            "File: {filename}\n"
            "Collection: {collection_slug}\n\n"
            "Selection:\n{selection}"
        ),
        ["filename", "collection_slug", "selection"],
        "editor",
    ),
    (
        "document_discuss",
        "Discuss document content",
        "Opens a free multi-turn conversation about the selected XML fragment.",
        (
            "You are a TEI P5 XML expert. The user wants to discuss the following "
            "XML fragment from their document.\n"
            "Answer in clear, natural language. You may include corrected XML "
            "snippets when helpful, but focus on explaining and guiding rather "
            "than producing raw XML only.\n\n"
            "File: {filename}\n"
            "Collection: {collection_slug}\n\n"
            "Selection:\n{selection}"
        ),
        ["filename", "collection_slug", "selection"],
        "editor",
    ),
    (
        "xslt_debug",
        "Debug XSLT stylesheet",
        "Analyzes an XSLT 1.0 stylesheet and explains the reported error.",
        (
            "You are an XSLT 1.0 expert. Analyze the following stylesheet "
            "and the reported error. Explain the cause and suggest a fix.\n\n"
            "Error:\n{error_msg}\n\n"
            "Stylesheet:\n{xslt_source}"
        ),
        ["error_msg", "xslt_source"],
        "xslt",
    ),
    (
        "xslt_discuss",
        "Discuss XSLT stylesheet",
        "Opens a free multi-turn conversation about an XSLT 1.0 stylesheet.",
        (
            "You are an XSLT 1.0 expert. The user wants to discuss the following "
            "XSLT stylesheet.\n"
            "Answer in clear, natural language. You may include corrected XSLT "
            "snippets when helpful, but focus on explaining and guiding.\n\n"
            "Stylesheet:\n{xslt_source}"
        ),
        ["xslt_source"],
        "xslt",
    ),
    (
        "bibliobuilder",
        "Bibliography Normalizer",
        (
            "Normalizes raw TEI <bibl>/<biblStruct> entries into a deduplicated, "
            "normalized <listBibl>. Feed the AI a flat XML file of extracted entries."
        ),
        (
            "You normalize bibliographic entries into TEI <biblStruct>.\n\n"
            "INPUT: an XML file with raw <bibl> and <biblStruct> elements, each carrying\n"
            "a @source attribute (original document id) and an optional @n (sequence number).\n\n"
            "OUTPUT: a single <listBibl> with deduplicated, normalized <biblStruct> entries.\n\n"
            "RULES:\n\n"
            "1. CLASSIFY each entry as: journalArticle | book | bookSection | webpage | manuscript | other\n\n"
            "2. NORMALIZE to <biblStruct> using this minimal structure:\n\n"
            "   <biblStruct xml:id=\"ID\" type=\"TYPE\">\n"
            "     <analytic>          <!-- only for articles/chapters -->\n"
            "       <author><persName><surname/><forename/></persName></author>\n"
            "       <title level=\"a\"/>\n"
            "     </analytic>\n"
            "     <monogr>\n"
            "       <author/>         <!-- only for monographs -->\n"
            "       <editor/>         <!-- if applicable -->\n"
            "       <title level=\"m|j|s\"/>\n"
            "       <imprint>\n"
            "         <pubPlace/>\n"
            "         <publisher/>\n"
            "         <date when=\"ISO\"/>\n"
            "       </imprint>\n"
            "       <biblScope unit=\"volume|issue|page\"/>\n"
            "     </monogr>\n"
            "     <idno type=\"DOI|URL|ISBN\"/>\n"
            "   </biblStruct>\n\n"
            "   Omit empty elements. Keep only what is present or safely inferable.\n\n"
            "3. xml:id FORMAT: bib_<surname>_<year>[a-z] (ASCII lowercase, disambiguate as needed).\n"
            "   No author → bib_<first_3_title_words>_<year>. Manuscripts → ms_<repo>_<shelfmark>.\n\n"
            "4. DEDUPLICATE: match on ≥2 of {{author, title, date, identifier}}.\n"
            "   Keep the richest entry, merge missing fields from others.\n"
            "   Record source documents in <note type=\"sources\">source1, source2</note>.\n\n"
            "5. PARSE FREE TEXT in <bibl> without child elements:\n"
            "   \"Smith 1998, pp. 45-67\" → extract author, date, pages.\n"
            "   Flag anything ambiguous in <note type=\"editorNote\"/>.\n\n"
            "6. Do NOT invent data. Uncertain dates → @notBefore/@notAfter. Missing fields → omit.\n\n"
            "7. SORT output: author A-Z, then date ascending.\n\n"
            "Respond ONLY with the <listBibl> XML block. No commentary.\n"
            "If entries exceed 80, process in batches of 80 and say NEXT to continue."
        ),
        [],
        None,
    ),
]


async def seed_ai_prompts(db: AsyncSession) -> None:
    """Seed native AI prompt templates; insert new ones and update existing ones.

    Updating on re-seed keeps native prompts in sync with the seed definition,
    so template fixes and label changes propagate without manual SQL.
    """
    for slug, label, description, template, context_vars, target_context in DEFAULT_AI_PROMPTS:
        existing = await db.scalar(select(AiPrompt).where(AiPrompt.slug == slug))
        if not existing:
            db.add(
                AiPrompt(
                    slug=slug,
                    label=label,
                    description=description,
                    template=template,
                    context_vars=context_vars,
                    target_context=target_context,
                    is_native=True,
                )
            )
        else:
            # Keep native prompts in sync with the seed definition so that
            # template fixes and label updates are applied on re-seed.
            existing.label = label
            existing.description = description
            existing.template = template
            existing.context_vars = context_vars
            existing.target_context = target_context
    await db.flush()
    logger.info("seed_ai_prompts_done")


# Bundled native schemas: (name, filename, format)
_BUNDLED_TEI_SCHEMAS: list[tuple[str, str, SchemaFormat]] = [
    ("TEI All (P5 v4.11.0)", "tei_all.rng", SchemaFormat.rng),
]


async def seed_tei_schemas(db: AsyncSession) -> None:
    """Seed bundled TEI schemas shipped with the application.

    For each entry in _BUNDLED_TEI_SCHEMAS:
    - Skip if a TeiSchema row with the same name already exists.
    - Create the DB row, copy the bundled file to schemas_dir, and update
      validation_filename / validation_format on the row.

    Idempotent: safe to call on every startup or `make seed` run.
    """
    for name, filename, fmt in _BUNDLED_TEI_SCHEMAS:
        exists = await db.scalar(select(TeiSchema).where(TeiSchema.name == name))
        if exists:
            continue

        src = _BUNDLED_SCHEMAS_DIR / filename
        if not src.exists():
            logger.warning("bundled_schema_missing", filename=filename)
            continue

        row = TeiSchema(
            name=name,
            validation_filename=filename,
            validation_format=fmt,
        )
        db.add(row)
        await db.flush()  # assigns row.id

        dest_dir = settings.schemas_dir / str(row.id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = fmt.value  # "rng" | "dtd" | "xsd"
        shutil.copy2(src, dest_dir / f"validation.{ext}")

        logger.info("seed_tei_schema_created", name=name, schema_id=str(row.id))

    logger.info("seed_tei_schemas_done")


async def seed_admin(db: AsyncSession) -> None:
    if not settings.admin_password:
        logger.warning(
            "seed_admin_skipped",
            reason="ADMIN_PASSWORD not set in environment — set it and re-run `make seed`",
        )
        return
    exists = await db.scalar(select(User).where(User.username == settings.admin_username))
    if exists:
        logger.info("seed_admin_skipped", reason="already exists")
        return

    from app.core.password import hash_password

    admin = User(
        username=settings.admin_username,
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        is_active=True,
        is_verified=True,
    )
    db.add(admin)
    await db.flush()

    # The trigger assigns the 'User' role — revoke it and assign 'Admin'
    user_role = await db.scalar(
        select(UserRole).where(
            UserRole.user_id == admin.id,
            UserRole.revoked_at.is_(None),
        )
    )
    if user_role:
        from datetime import UTC, datetime

        user_role.revoked_at = datetime.now(UTC)

    admin_role = await db.scalar(select(Role).where(Role.name == "Admin"))
    assert admin_role is not None, "Admin role not found — run seed_roles first"
    db.add(UserRole(user_id=admin.id, role_id=admin_role.id))
    logger.info("seed_admin_created", username=settings.admin_username)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed_roles(db)
        await seed_settings(db)
        await seed_licenses(db)
        await seed_body_templates(db)
        await seed_ai_prompts(db)
        await seed_tei_schemas(db)
        await seed_admin(db)
        await db.commit()
    print("Seed completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
