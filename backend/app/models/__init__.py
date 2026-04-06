# Import all models so that Alembic autogenerate can discover them
from app.models.audit_log import AuditLog
from app.models.collection import Collection
from app.models.collection_permission import CollectionPermission
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
    "CollectionPermission",
]
