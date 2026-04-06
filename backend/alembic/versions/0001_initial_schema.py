"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, INET, JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # 2. Enum types — DO block handles the case where the type already exists
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE role_name AS ENUM ('Admin', 'EditorInChief', 'Designer', 'Editor', 'User');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE plugin_status AS ENUM ('active', 'inactive', 'error');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # 3. roles
    op.create_table(
        "roles",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("name", ENUM(name="role_name", create_type=False), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 4. users
    op.create_table(
        "users",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column(
            "preferred_lang", sa.String(5), server_default=sa.text("'it'"), nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False
        ),
        sa.Column(
            "is_verified", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    # 5. user_roles
    op.create_table(
        "user_roles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.Column("assigned_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by", UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # UNIQUE NULLS NOT DISTINCT — PostgreSQL 15 syntax, not supported by sa.UniqueConstraint
    op.execute(
        "ALTER TABLE user_roles ADD CONSTRAINT uq_user_active_role "
        "UNIQUE NULLS NOT DISTINCT (user_id, role_id, revoked_at)"
    )

    # 6. sessions
    op.create_table(
        "sessions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("access_jti", UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_jti", UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "issued_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("access_expires", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("refresh_expires", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("access_jti"),
        sa.UniqueConstraint("refresh_jti"),
    )

    # 7. system_settings
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(256), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "type", sa.String(32), server_default=sa.text("'string'"), nullable=False
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    # 8. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("actor_username", sa.String(64), nullable=True),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("target_label", sa.Text(), nullable=True),
        sa.Column("ip_address", INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 9. plugins
    op.create_table(
        "plugins",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("author", sa.String(256), nullable=True),
        sa.Column("entry_point", sa.Text(), nullable=True),
        sa.Column(
            "status",
            ENUM(name="plugin_status", create_type=False),
            server_default=sa.text("'inactive'"),
            nullable=False,
        ),
        sa.Column(
            "config", JSONB(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "hooks", JSONB(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "installed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("installed_by", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["installed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 10. notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column(
            "is_read", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 11. Indexes for query performance
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_access_jti", "sessions", ["access_jti"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    # 12. Triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_set_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $func$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $func$;
    """)
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_assign_default_role()
        RETURNS TRIGGER LANGUAGE plpgsql AS $func$
        BEGIN
            INSERT INTO user_roles (user_id, role_id)
            SELECT NEW.id, id FROM roles WHERE name = 'User';
            RETURN NEW;
        END;
        $func$;
    """)
    op.execute("""
        CREATE TRIGGER trg_default_role
        AFTER INSERT ON users
        FOR EACH ROW EXECUTE FUNCTION fn_assign_default_role();
    """)


def downgrade() -> None:
    # Triggers and functions
    op.execute("DROP TRIGGER IF EXISTS trg_default_role ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS fn_assign_default_role()")
    op.execute("DROP FUNCTION IF EXISTS fn_set_updated_at()")

    # Indexes
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_id", table_name="audit_log")
    op.drop_index("ix_sessions_access_jti", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")

    # Tables in reverse FK order
    op.drop_table("notifications")
    op.drop_table("plugins")
    op.drop_table("audit_log")
    op.drop_table("system_settings")
    op.drop_table("sessions")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")

    # Enum types
    op.execute("DROP TYPE IF EXISTS plugin_status")
    op.execute("DROP TYPE IF EXISTS role_name")

    # Extensions — commented out to avoid breaking other databases in the same cluster
    # op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    # op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    # op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
