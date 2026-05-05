# reddit-mcp

Custom **Model Context Protocol** server wrapping the public Reddit JSON endpoints (no auth required).

## Tools

| Tool | Description |
|---|---|
| `top_posts(subreddit, limit, timeframe)` | Top posts of a subreddit. `subreddit` defaults to `nba`, `timeframe` to `day`. |
| `hot_posts(subreddit, limit)` | Currently trending posts (recent engagement velocity). |
| `search_posts(query, subreddit, limit)` | Relevance-sorted search inside a subreddit. |

## Configuration

Reddit asks clients to set a User-Agent. Configure with the `REDDIT_USER_AGENT` env var.

## Running standalone

```bash
pip install mcp httpx
python server.py
```

## Plugging into Claude Desktop / Cursor

```json
{
  "mcpServers": {
    "reddit-nba": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_servers/reddit/server.py"],
      "env": { "REDDIT_USER_AGENT": "your-app/0.1" }
    }
  }
}
```
