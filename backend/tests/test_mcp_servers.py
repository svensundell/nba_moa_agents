"""Unit tests for MCP server helpers (no subprocess, no network)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_server(relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_espn_injury_filter() -> None:
    espn = _load_server("mcp_servers/espn/server.py")
    assert espn._is_injury({"title": "Star ruled out with knee injury", "summary": ""})
    assert not espn._is_injury({"title": "Pacers beat Celtics in overtime thriller", "summary": ""})


def test_espn_format_score_for_game() -> None:
    espn = _load_server("mcp_servers/espn/server.py")
    game = {
        "id": "401585601",
        "name": "Lakers at Celtics",
        "shortName": "LAL @ BOS",
        "date": "2026-05-19T23:30Z",
        "status": {"type": {"description": "Final", "completed": True}},
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": "110",
                        "winner": True,
                        "team": {"abbreviation": "BOS", "displayName": "Boston Celtics"},
                    },
                    {
                        "homeAway": "away",
                        "score": "102",
                        "winner": False,
                        "team": {"abbreviation": "LAL", "displayName": "Los Angeles Lakers"},
                    },
                ]
            }
        ],
    }
    out = espn._format_score_for_game(game)
    assert out["event_id"] == "401585601"
    assert out["completed"] is True
    assert len(out["teams"]) == 2
    assert out["teams"][0]["abbrev"] in {"BOS", "LAL"}


def test_reddit_shape_post() -> None:
    reddit = _load_server("mcp_servers/reddit/server.py")
    shaped = reddit._shape(
        {
            "title": "Game thread",
            "score": 420,
            "num_comments": 88,
            "author": "nba_mod",
            "permalink": "/r/nba/comments/abc/",
            "url": "https://reddit.com",
            "link_flair_text": "Highlight",
            "selftext": "x" * 400,
        }
    )
    assert shaped["title"] == "Game thread"
    assert shaped["permalink"].startswith("https://www.reddit.com")
    assert len(shaped["selftext_excerpt"]) <= 280
