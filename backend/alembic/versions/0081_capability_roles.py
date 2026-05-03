"""Add capability-role primitives + PolicyManager — Phase PP-B.

The pre-existing five roles (Admin, EditorInChief, Designer,
Editor, User) form the **hierarchical** ladder ROLE_LEVEL ranks.
Milestone 3's PolicyManager is the first **capability role** —
orthogonal to the ladder; granted by Admin to any user from
``User`` upwards; the granted user gets read+write access to the
``policy_pages`` admin surface without that grant changing their
main hierarchical role at all.

To distinguish the two kinds without breaking ``require_role`` we
add two columns on ``roles``:

- ``kind`` (``hierarchical`` | ``capability``) — drives whether
  the row participates in the ROLE_LEVEL comparison
  ``require_role`` does, or in the ``require_capability``
  membership check the policy_pages plugin uses.
- ``singleton`` (bool) — at most one user can hold the role at
  any moment. Granting it to user B while user A already holds it
  auto-revokes A in the same transaction (per the M3 spec). The
  hierarchical roles are all ``singleton=false``; PolicyManager
  is the first ``singleton=true``.

The ``role_name`` PostgreSQL enum gains the new
``PolicyManager`` value; existing 5 rows are migrated as
``kind='hierarchical', singleton=false``; a new ``PolicyManager``
row is inserted as ``kind='capability', singleton=true``.

Revision ID: 0081
Revises: 0080
Create Date: 2026-05-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL enum extension: ``ALTER TYPE … ADD VALUE`` cannot run
    # inside a transaction block, so we run it in autocommit mode.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE role_name ADD VALUE IF NOT EXISTS 'PolicyManager'"
            )

    op.add_column(
        "roles",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'hierarchical'"),
        ),
    )
    op.add_column(
        "roles",
        sa.Column(
            "singleton",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Insert the new row. Must be in a separate transaction from the
    # ALTER TYPE above so the new enum value is visible.
    op.execute(
        """
        INSERT INTO roles (name, description, kind, singleton)
        VALUES (
            'PolicyManager',
            'Edits institutional policy pages (singleton capability role)',
            'capability',
            true
        )
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name = 'PolicyManager'")
    op.drop_column("roles", "singleton")
    op.drop_column("roles", "kind")
    # We cannot remove a value from a PostgreSQL enum without rebuilding
    # the type. Leave 'PolicyManager' in the enum on downgrade — harmless;
    # the row is gone so no code path references it. Reinstating the
    # plugin re-creates the row via the upgrade path.
