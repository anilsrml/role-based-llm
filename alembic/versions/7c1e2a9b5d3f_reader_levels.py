"""one SELECT-only reader per role level

Revision ID: 7c1e2a9b5d3f
Revises: 4fec6db1eb8a
Create Date: 2026-11-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

from rolchat.models import TABLE_LEVELS


# revision identifiers, used by Alembic.
revision: str = '7c1e2a9b5d3f'
down_revision: Union[str, Sequence[str], None] = '4fec6db1eb8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEVELS = sorted(set(TABLE_LEVELS.values()))


def upgrade() -> None:
    """Create reader_l1..3 and grant SELECT on the tables at or below each level."""
    for level in LEVELS:
        user = f"reader_l{level}"
        # Roles are cluster-wide and the server may be shared, so creation must be idempotent.
        op.execute(f"""
            DO $$ BEGIN
                CREATE ROLE {user} LOGIN PASSWORD '{user}';
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)
        op.execute(f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {user}', current_database()); END $$;")
        op.execute(f"GRANT USAGE ON SCHEMA public TO {user}")
        tables = ", ".join(t for t, t_level in TABLE_LEVELS.items() if t_level <= level)
        op.execute(f"GRANT SELECT ON {tables} TO {user}")


def downgrade() -> None:
    """Revoke the grants in this database; the roles stay, other databases may use them."""
    for level in LEVELS:
        user = f"reader_l{level}"
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {user}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {user}")
        op.execute(f"DO $$ BEGIN EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM {user}', current_database()); END $$;")
