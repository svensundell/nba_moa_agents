# espn-mcp

Custom **Model Context Protocol** server wrapping ESPN's NBA RSS feed.

## Tools

| Tool | Description |
|---|---|
| `nba_headlines(limit=15)` | Most recent NBA headlines (title, summary, link, published date). |
| `nba_injury_headlines(limit=10)` | Same, filtered to injury / availability news. |

## Running standalone

```bash
pip install mcp httpx feedparser
python server.py
```

## Plugging into Claude Desktop / Cursor

```json
{
  "mcpServers": {
    "espn-nba": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_servers/espn/server.py"]
    }
  }
}
```
