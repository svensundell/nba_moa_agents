"""Source citation helpers for traceable NBA briefings and Copilot answers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.eval.schemas import SourceCitation

if TYPE_CHECKING:
    from app.eval.tracker import RunTracker
    from app.moa.state import AgentEvent, AgentProposal


def provider_for_tool(tool_name: str) -> str:
    """Map an MCP tool name to a human-facing provider label."""
    name = tool_name.lower()
    if name.startswith("espn_") or "espn" in name:
        return "ESPN"
    if name.startswith("reddit_") or "reddit" in name:
        return "Reddit"
    if name.startswith("nba_stats_") or "balldontlie" in name:
        return "balldontlie"
    if "_" in name:
        return name.split("_", 1)[0].upper()
    return "MCP"


def title_for_tool(tool_name: str, *, arguments: dict[str, Any] | None = None) -> str:
    """Short label for a tool invocation."""
    args = arguments or {}
    if tool_name == "nba_stats_get_games" and args.get("date"):
        return f"NBA games ({args['date']})"
    if tool_name == "reddit_search_posts" and args.get("query"):
        return f"Reddit search: {args['query']}"
    if tool_name == "reddit_top_posts":
        sub = args.get("subreddit", "nba")
        return f"Reddit r/{sub} top posts"
    return tool_name.replace("_", " ")


def excerpt_from_payload(text: str, *, max_len: int = 280) -> str:
    """First readable snippet from raw MCP JSON/text."""
    if not text:
        return ""
    preview = text.strip().replace("\n", " ")
    if len(preview) <= max_len:
        return preview
    return preview[: max_len - 1] + "…"


def urls_from_payload(text: str) -> list[str]:
    """Extract HTTP links from tool output."""
    if not text:
        return []
    urls = re.findall(r"https?://[^\s\"'<>\\]+", text)
    cleaned: list[str] = []
    for url in urls:
        u = url.rstrip(".,);]")
        if u and u not in cleaned:
            cleaned.append(u)
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return cleaned

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            link = node.get("link") or node.get("url")
            if isinstance(link, str) and link.startswith("http") and link not in cleaned:
                cleaned.append(link)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return cleaned


def citation_from_mcp(
    *,
    citation_id: int,
    agent: str,
    tool_name: str,
    raw_text: str,
    retrieved_at: datetime,
    arguments: dict[str, Any] | None = None,
) -> SourceCitation:
    """Build a structured citation from one MCP tool result."""
    urls = urls_from_payload(raw_text)
    provider = provider_for_tool(tool_name)
    return SourceCitation(
        id=citation_id,
        provider=provider,
        tool=tool_name,
        agent=agent,
        retrieved_at=retrieved_at,
        url=urls[0] if urls else None,
        title=title_for_tool(tool_name, arguments=arguments),
        excerpt=excerpt_from_payload(raw_text),
    )


def citation_from_legacy_source(
    *,
    citation_id: int,
    source: str,
    agent: str,
) -> SourceCitation:
    """Wrap a legacy proposal source string (URL or mcp: tag)."""
    if source.startswith("http"):
        host = source.split("/")[2] if "/" in source[8:] else "Web"
        provider = "ESPN" if "espn" in host else "Web"
        return SourceCitation(
            id=citation_id,
            provider=provider,
            tool="(proposal)",
            agent=agent,
            retrieved_at=datetime.now(),
            url=source,
            title=source[:80],
            excerpt="",
        )
    tool = source.removeprefix("mcp:").split(":", 1)[-1]
    return SourceCitation(
        id=citation_id,
        provider=provider_for_tool(tool),
        tool=tool,
        agent=agent,
        retrieved_at=datetime.now(),
        url=None,
        title=tool.replace("_", " "),
        excerpt="",
    )


def merge_run_citations(
    tracker: RunTracker | None,
    proposals: list[AgentProposal] | None = None,
) -> list[SourceCitation]:
    """Ordered bibliography: MCP citations first, then proposal-only URLs."""
    out: list[SourceCitation] = []
    seen: set[str] = set()

    if tracker is not None:
        for cite in tracker.list_citations():
            key = f"{cite.tool}|{cite.url or ''}|{cite.agent}"
            if key in seen:
                continue
            seen.add(key)
            out.append(cite)

    next_id = (max((c.id for c in out), default=0)) + 1
    for prop in proposals or []:
        for src in prop.sources or []:
            key = f"legacy|{src}|{prop.agent}"
            if key in seen:
                continue
            seen.add(key)
            out.append(
                citation_from_legacy_source(
                    citation_id=next_id,
                    source=src,
                    agent=prop.agent,
                )
            )
            next_id += 1

    return sorted(out, key=lambda c: c.id)


def format_citation_index(citations: list[SourceCitation]) -> str:
    """Numbered index passed to the editor / Copilot for inline [n] refs."""
    if not citations:
        return "(No external sources recorded for this run.)"
    lines: list[str] = []
    for c in citations:
        when = c.retrieved_at.strftime("%Y-%m-%d %H:%M UTC")
        link = f" | {c.url}" if c.url else ""
        lines.append(f"[{c.id}] {c.provider} — {c.tool} — {c.agent} — {when}{link}")
    return "\n".join(lines)


def apply_citation_to_event(event: AgentEvent, citation: SourceCitation | None) -> AgentEvent:
    """Attach citation metadata to a tool event for the live trace UI."""
    if citation is None:
        return event
    event.citation_id = citation.id
    event.provider = citation.provider
    event.tool = citation.tool
    event.retrieved_at = citation.retrieved_at
    event.source_url = citation.url
    return event
