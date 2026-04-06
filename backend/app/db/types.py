from sqlalchemy import String
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.types import TypeDecorator


class InetType(TypeDecorator):
    """INET on PostgreSQL, VARCHAR(45) on other dialects (e.g. SQLite in tests)."""

    impl = String(45)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(INET())
        return dialect.type_descriptor(String(45))
