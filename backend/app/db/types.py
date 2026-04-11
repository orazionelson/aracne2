from typing import Any

import sqlalchemy as sa
from sqlalchemy import JSON, BigInteger, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.types import TypeDecorator, TypeEngine


class InetType(TypeDecorator[str]):
    """INET on PostgreSQL, VARCHAR(45) on other dialects (e.g. SQLite in tests)."""

    impl = String(45)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[str]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(INET())  # type: ignore[no-any-return]
        return dialect.type_descriptor(String(45))  # type: ignore[no-any-return]


class JsonbType(TypeDecorator[Any]):
    """JSONB on PostgreSQL, JSON on other dialects (e.g. SQLite in tests)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call, no-any-return]
        return dialect.type_descriptor(JSON())  # type: ignore[no-any-return]


class TextArrayType(TypeDecorator[list[str]]):
    """ARRAY(Text) on PostgreSQL, JSON on other dialects (e.g. SQLite in tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(sa.Text))  # type: ignore[no-any-return]
        return dialect.type_descriptor(JSON())  # type: ignore[no-any-return]

    def process_bind_param(self, value: list[str] | None, dialect: Any) -> Any:
        return value

    def process_result_value(self, value: Any, dialect: Any) -> list[str]:
        if value is None:
            return []
        return list(value)


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
            return dialect.type_descriptor(SmallInteger())  # type: ignore[no-any-return]
        return dialect.type_descriptor(Integer())  # type: ignore[no-any-return]


class BigIntType(TypeDecorator[int]):
    """BIGINT on PostgreSQL, INTEGER on other dialects.

    Same SQLite rowid-alias constraint as SmallIntType.
    """

    impl = BigInteger
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[int]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(BigInteger())  # type: ignore[no-any-return]
        return dialect.type_descriptor(Integer())  # type: ignore[no-any-return]
