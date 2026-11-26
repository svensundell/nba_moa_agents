"""The citation the model sees also appears in the WebSocket tool event."""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.api.runner import run_streaming
from app.moa import open_query


class FakeCopilot(FakeMessagesListChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


@tool
def espn_nba_scoreboard() -> str:
    """Return a game result."""
    return '{"url":"https://www.espn.com/nba/scoreboard/_/date/20250622","score":"103-91"}'


async def test_copilot_stream_tool_event_links_to_its_source(monkeypatch):
    model = FakeCopilot(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "espn_nba_scoreboard", "args": {}, "id": "fixture-score"}],
            ),
            AIMessage(content="OKC won 103-91 [1]."),
        ]
    )
    monkeypatch.setattr(open_query, "get_model", lambda *args, **kwargs: model)
    monkeypatch.setattr(
        open_query.mcp_registry, "_tools", {"espn_nba_scoreboard": espn_nba_scoreboard}
    )
    frames = [frame async for frame in run_streaming("query", query="What was the score?")]
    event = next(
        frame["event"]
        for frame in frames
        if frame["kind"] == "event" and frame["event"]["type"] == "tool"
    )
    result = frames[-1]["result"]
    source = result["source_citations"][0]
    assert event["citation_id"] == source["id"] == 1
    assert event["source_url"] == source["url"]
    assert result["metrics"]["tool_call_count"] == 1
