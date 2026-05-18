"""Tests for structured source citations."""

from datetime import datetime

from app.moa.citations import (
    citation_from_mcp,
    format_citation_index,
    merge_run_citations,
    provider_for_tool,
    urls_from_payload,
)
from app.moa.state import AgentProposal


def test_provider_for_tool() -> None:
    assert provider_for_tool("espn_nba_headlines") == "ESPN"
    assert provider_for_tool("reddit_hot_posts") == "Reddit"
    assert provider_for_tool("nba_stats_get_games") == "balldontlie"


def test_urls_from_payload_json() -> None:
    text = '{"items":[{"link":"https://www.espn.com/nba/story"}]}'
    assert "https://www.espn.com/nba/story" in urls_from_payload(text)


def test_citation_from_mcp() -> None:
    cite = citation_from_mcp(
        citation_id=1,
        agent="news",
        tool_name="espn_nba_headlines",
        raw_text='{"items":[{"link":"https://espn.com/x"}]}',
        retrieved_at=datetime(2026, 5, 18, 12, 0, 0),
    )
    assert cite.id == 1
    assert cite.provider == "ESPN"
    assert cite.url == "https://espn.com/x"


def test_format_citation_index() -> None:
    cite = citation_from_mcp(
        citation_id=2,
        agent="scores",
        tool_name="nba_stats_get_games",
        raw_text="{}",
        retrieved_at=datetime(2026, 5, 18, 12, 0, 0),
    )
    block = format_citation_index([cite])
    assert "[2]" in block
    assert "balldontlie" in block


def test_merge_run_citations_adds_proposal_urls() -> None:
    proposals = [
        AgentProposal(
            agent="news",
            model="m",
            summary="x",
            sources=["https://example.com/article"],
        )
    ]
    merged = merge_run_citations(None, proposals)
    assert len(merged) == 1
    assert merged[0].url == "https://example.com/article"
