"""named_entities.type: convert from entity_type enum to VARCHAR(64)

Allows arbitrary TEI tag names to be used as entity types instead of
the hardcoded person/place/org enum values.

Revision ID: 0046
Revises: 0045
Create Date: 2026-04-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: alter the column from enum to varchar, casting existing values.
    op.execute("""
        ALTER TABLE named_entities
        ALTER COLUMN type TYPE VARCHAR(64)
        USING type::text;
    """)

    # Step 2: drop the now-unused enum type.
    op.execute("DROP TYPE IF EXISTS entity_type;")


def downgrade() -> None:
    # Recreate the enum with the original three values.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE entity_type AS ENUM ('person', 'place', 'org');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Rows with types outside the original three are cast to 'person'
    # as a safe fallback so the cast never fails.
    op.execute("""
        ALTER TABLE named_entities
        ALTER COLUMN type TYPE entity_type
        USING CASE
            WHEN type IN ('person', 'place', 'org') THEN type::entity_type
            ELSE 'person'::entity_type
        END;
    """)
