"""Pydantic models for the public REST + WebSocket API."""

from __future__ import annotations

from datetime import date as iso_date
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.eval.schemas import RunMetrics, SourceCitation
from app.moa.state import AgentEvent

LanguageCode = Literal["en", "fr"]


class BriefRequest(BaseModel):
    date: iso_date | None = Field(
        default=None, description="ISO date (YYYY-MM-DD), defaults to yesterday."
    )
    language: LanguageCode = Field(default="en", description="Output language (`en` or `fr`).")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(description="Chat role compatible with NBA Copilot.")
    content: str = Field(min_length=1, max_length=2000)


class QueryRequest(BriefRequest):
    query: str = Field(
        default="",
        max_length=500,
        description="Single-turn input kept for backwards compatibility.",
    )
    messages: list[ChatMessage] = Field(
        default_factory=list,
        max_length=9,
        description="Optional conversation history for multi-turn NBA Copilot chat.",
    )

    @model_validator(mode="after")
    def latest_question(self) -> QueryRequest:
        if self.messages:
            latest = self.messages[-1]
            if latest.role != "user" or not latest.content.strip():
                raise ValueError("The last message must be a question from the user.")
        elif not self.query.strip():
            raise ValueError("Provide a question.")
        return self


class CompareRequest(BriefRequest):
    query: str = Field(
        default="",
        max_length=500,
        description="Optional comparison prompt. Empty query runs daily brief comparison.",
    )


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
    metrics: RunMetrics | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    openrouter_byok: bool = True
    sponsored_runs: bool = False
    demo_daily_runs: int | None = None
    demo_runs_remaining: int | None = None
    has_balldontlie: bool
    database_ok: bool
    mcp_initialised: bool
    mcp_servers: list[str]
    mcp_tools: list[str]
    app_access_required: bool = False
