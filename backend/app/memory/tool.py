"""LangChain tool exposing brief memory search to NBA Copilot."""

from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.memory.service import get_memory_service


class SearchBriefMemoryInput(BaseModel):
    query: str = Field(
        description=(
            "Natural-language search over archived Daily Briefs "
            "(storylines, teams, players, trends)."
        )
    )
    days: int = Field(
        default=14,
        ge=1,
        le=90,
        description="How many days back to search (default 14).",
    )


async def _search_brief_memory(query: str, days: int = 14) -> str:
    service = get_memory_service()
    result = await service.search(query, days=days)
    return service.format_hits_for_tool(result)


def build_memory_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_search_brief_memory,
        name="search_brief_memory",
        description=(
            "Search past Daily Brief archives by semantic similarity. "
            "Use for trends, recurring storylines, 'why is everyone talking about X', "
            "or context over the last 1-4 weeks. "
            "Prefer live MCP tools (ESPN, balldontlie, Reddit) for current scores, "
            "injuries, and breaking news."
        ),
        args_schema=SearchBriefMemoryInput,
    )
