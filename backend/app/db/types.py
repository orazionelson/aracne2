from typing import Any

from sqlalchemy import JSON, BigInteger, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.types import TypeDecorator, TypeEngine


class InetType(TypeDecorator[str]):
    """INET on PostgreSQL, VARCHAR(45) on other dialects (e.g. SQLite in tests)."""

    impl = String(45)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[str]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(INET())
        return dialect.type_descriptor(String(45))


class JsonbType(TypeDecorator[Any]):
    """JSONB on PostgreSQL, JSON on other dialects (e.g. SQLite in tests)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())


class SmallIntType(TypeDecorator[int]):
    """SMALLINT on PostgreSQL, INTEGER on other dialects.

    SQLite only recognises INTEGER PRIMARY KEY as a rowid alias (autoincrement).
    SMALLINT PRIMARY KEY does not trigger that behaviour, causing NOT NULL
    constraint failures when the id is omitted from INSERT statements.
    """

    impl = SmallInteger
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[int]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(SmallInteger())
        return dialect.type_descriptor(Integer())


class BigIntType(TypeDecorator[int]):
    """BIGINT on PostgreSQL, INTEGER on other dialects.

    Same SQLite rowid-alias constraint as SmallIntType.
    """

    impl = BigInteger
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[int]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(BigInteger())
        return dialect.type_descriptor(Integer())
