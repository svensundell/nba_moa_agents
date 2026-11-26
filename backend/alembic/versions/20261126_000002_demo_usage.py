"""Reserve shared demo requests atomically per UTC day."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_000002"
down_revision = "20260520_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("demo_usage")
