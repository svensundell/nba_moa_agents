"""SQLAlchemy models for evaluation persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    date: Mapped[str] = mapped_column(String(32), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    moa_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_price: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    final_brief: Mapped[str] = mapped_column(Text, nullable=False, default="")
    single_llm_answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    agents: Mapped[list[AgentMetricRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[list[ToolCallRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentMetricRow(Base):
    __tablename__ = "agent_metrics"

    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    agent: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    llm_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    wall_clock_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    run: Mapped[RunRow] = relationship(back_populates="agents")


class ToolCallRow(Base):
    __tablename__ = "tool_calls"

    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    run: Mapped[RunRow] = relationship(back_populates="tool_calls")
