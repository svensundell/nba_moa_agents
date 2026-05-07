"""Shared state schema for the LangGraph MoA pipeline.

The state flows through three layers:
    Layer 1 (proposers)  → fills in `proposals`
    Layer 2 (refiners)   → fills in `refinements`
    Layer 3 (aggregator) → fills in `final_brief`

The `events` channel is append-only and is what the WebSocket streams to the
frontend so the user can watch each agent think in real time.
"""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

# ─── Public payloads (also used by the API layer) ────────────────────────────


class AgentEvent(BaseModel):
    """A single event emitted by any agent — streamed over WebSocket."""

    agent: str
    layer: Literal["proposer", "refiner", "aggregator", "system"]
    type: Literal["start", "chunk", "tool", "done", "error"]
    content: str = ""
    model: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentProposal(BaseModel):
    agent: str
    model: str
    summary: str
    sources: list[str] = []
    raw: str = ""


class AgentRefinement(BaseModel):
    agent: str
    model: str
    content: str


# ─── LangGraph state ─────────────────────────────────────────────────────────


def _take_last(_left: Any, right: Any) -> Any:
    """Reducer that simply replaces the left value (last write wins)."""
    return right


class MoAState(TypedDict, total=False):
    """The state passed through every node in the graph.

    Channels using `operator.add` accumulate values from parallel branches,
    which is essential for the proposer / refiner layers that fan out.
    """

    # input
    mode: Literal["brief", "query", "compare"]
    language: Literal["en", "fr"]
    query: str
    date: str  # ISO date the briefing/query is anchored on

    # outputs of layer 1
    proposals: Annotated[list[AgentProposal], operator.add]

    # outputs of layer 2
    refinements: Annotated[list[AgentRefinement], operator.add]

    # output of layer 3
    final_brief: Annotated[str, _take_last]

    # baseline for comparison mode
    single_llm_answer: Annotated[str, _take_last]

    # streaming channel (UI consumes this)
    events: Annotated[list[AgentEvent], operator.add]


def initial_state(
    mode: Literal["brief", "query", "compare"],
    query: str = "",
    date: str | None = None,
    language: Literal["en", "fr"] = "en",
) -> MoAState:
    return MoAState(
        mode=mode,
        language=language,
        query=query,
        date=date or datetime.now().date().isoformat(),
        proposals=[],
        refinements=[],
        final_brief="",
        single_llm_answer="",
        events=[],
    )
