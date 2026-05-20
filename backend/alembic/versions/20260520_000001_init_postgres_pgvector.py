"""Initial Postgres schema for eval + memory + pgvector."""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260520_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("date", sa.String(length=32), nullable=False),
        sa.Column("query", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("distinct_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("moa_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("baseline_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("estimated_price", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("final_brief", sa.Text(), nullable=False, server_default=""),
        sa.Column("single_llm_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("idx_runs_started_at", "runs", ["started_at"], unique=False)
    op.create_index("idx_runs_mode", "runs", ["mode"], unique=False)

    op.create_table(
        "agent_metrics",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("llm_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("wall_clock_ms", sa.Float(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "agent"),
    )

    op.create_table(
        "tool_calls",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("tool", sa.String(length=128), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "seq"),
    )
    op.create_index("idx_tool_calls_tool", "tool_calls", ["tool"], unique=False)

    op.create_table(
        "briefs",
        sa.Column("brief_id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("date", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("idx_briefs_date", "briefs", ["date"], unique=False)

    op.create_table(
        "chunks",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brief_id", sa.String(length=64), nullable=False),
        sa.Column("date", sa.String(length=32), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(["brief_id"], ["briefs.brief_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index("idx_chunks_brief_id", "chunks", ["brief_id"], unique=False)
    op.create_index("idx_chunks_date", "chunks", ["date"], unique=False)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("idx_chunks_embedding_hnsw", table_name="chunks")
    op.drop_index("idx_chunks_date", table_name="chunks")
    op.drop_index("idx_chunks_brief_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("idx_briefs_date", table_name="briefs")
    op.drop_table("briefs")

    op.drop_index("idx_tool_calls_tool", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_table("agent_metrics")
    op.drop_index("idx_runs_mode", table_name="runs")
    op.drop_index("idx_runs_started_at", table_name="runs")
    op.drop_table("runs")
