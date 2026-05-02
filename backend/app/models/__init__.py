# Import all models so that Alembic autogenerate can discover them
from app.models.audit_log import AuditLog
from app.models.collection import Collection
from app.models.collection_bibliography import CollectionBibliography
from app.models.corpus import Corpus, McpToken
from app.models.document_version import DocumentVersion, VersionOrigin
from app.models.nl_search_budget import NlSearchBudgetDay
from app.models.nl_search_cache import NlSearchCache
from app.models.password_reset_token import PasswordResetToken
from app.models.personal_access_token import PersonalAccessToken
from app.models.tei_schema import TeiSchema
from app.models.collection_permission import CollectionPermission
from app.models.plugin_data import PluginData
from app.models.notification import Notification
from app.models.plugin import Plugin
from app.models.role import Role, UserRole
from app.models.session import Session
from app.models.system_setting import SystemSetting
from app.models.user import User

__all__ = [
    "User",
    "Role",
    "UserRole",
    "Session",
    "AuditLog",
    "Plugin",
    "Notification",
    "SystemSetting",
    "Collection",
    "CollectionBibliography",
    "CollectionPermission",
    "Corpus",
    "DocumentVersion",
    "McpToken",
    "NlSearchBudgetDay",
    "NlSearchCache",
    "PasswordResetToken",
    "PersonalAccessToken",
    "PluginData",
    "TeiSchema",
    "VersionOrigin",
]
