"""Pydantic models for the public REST + WebSocket API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.moa.state import AgentEvent


class BriefRequest(BaseModel):
    date: str | None = Field(default=None, description="ISO date (YYYY-MM-DD), defaults to yesterday.")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(
        description="Chat role compatible with NBA Copilot."
    )
    content: str = Field(min_length=1, max_length=2000)


class QueryRequest(BaseModel):
    query: str = Field(
        default="",
        max_length=500,
        description="Single-turn input kept for backwards compatibility.",
    )
    date: str | None = None
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Optional conversation history for multi-turn NBA Copilot chat.",
    )


class CompareRequest(BaseModel):
    query: str = Field(
        default="",
        max_length=500,
        description="Optional comparison prompt. Empty query runs daily brief comparison.",
    )
    date: str | None = None


class ProposalView(BaseModel):
    agent: str
    model: str
    summary: str
    sources: list[str]


class RefinementView(BaseModel):
    agent: str
    model: str
    content: str


class RunResult(BaseModel):
    mode: Literal["brief", "query", "compare"]
    date: str
    query: str = ""
    final_brief: str
    single_llm_answer: str = ""
    proposals: list[ProposalView] = []
    refinements: list[RefinementView] = []
    events: list[AgentEvent] = []
    started_at: datetime
    finished_at: datetime
    duration_seconds: float


class HealthResponse(BaseModel):
    status: Literal["ok"]
    has_openrouter: bool
    has_balldontlie: bool
    mcp_initialised: bool
    mcp_servers: list[str]
    mcp_tools: list[str]
