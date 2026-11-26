"""Keep historical runs unclaimed and scope new runs to their owner."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_000003"
down_revision = "20261126_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("owner_id", sa.String(64), nullable=True))
    op.create_index("ix_runs_owner_started", "runs", ["owner_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_owner_started", table_name="runs")
    op.drop_column("runs", "owner_id")
