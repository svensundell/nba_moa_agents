# nba-stats-mcp

A custom **Model Context Protocol** server exposing the [balldontlie.io](https://www.balldontlie.io) NBA API as MCP tools.

## Why a custom MCP server?

This is the differentiating piece of the project: any MCP-aware LLM client (Claude Desktop, Cursor, the LangGraph agents in this repo) can immediately gain access to NBA data without writing custom HTTP integrations.

## Tools exposed

| Tool | Description |
|---|---|
| `get_games(date?)` | Games for an ISO date (defaults to yesterday) |
| `search_players(name, per_page=5)` | Fuzzy player search |
| `player_season_averages(player_id, season?)` | PPG, RPG, APG, FG%, 3P% |
| `list_teams()` | Roster of the 30 NBA teams |
| `team_recent_games(team_id, days=7)` | Last week of games for a team |

## Running standalone

```bash
pip install mcp httpx
python server.py
```

The server speaks MCP over stdio — pipe it from any MCP client.

## Plugging into Claude Desktop

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nba-stats": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_servers/nba_stats/server.py"]
    }
  }
}
```

Restart Claude Desktop and ask it: *"What were last night's NBA scores?"* — it will call `get_games` automatically.

## Plugging into Cursor

Add the same configuration to your Cursor MCP settings. Cursor will pick up the `nba-stats` server and expose its tools to any chat or agent task.
