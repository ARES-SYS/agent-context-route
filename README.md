# Agent Context Route — MCP stdio Context Router

**Decides WHAT context the agent needs and HOW MUCH token budget to allocate.**

Zero dependencies. Python 3.10+ stdlib only.
Protocol: MCP (Model Context Protocol) via stdio JSON-RPC.

## Philosophy

"Importance over recency."

Most context systems give you the most recent chunks. This one
classifies the intent FIRST, then assigns a token budget based on
importance — not chronology.

## Usage

```bash
# Register as MCP tool in your agent config
python server.py
```

### MCP tool: `route_context`

```json
{
  "query": "How do I configure the firewall?",
  "session_id": "session-abc"
}
```

Response:

```json
{
  "handler": "operations",
  "confidence": 0.8,
  "importance": 0.75,
  "token_budget": 2048,
  "ttl": 3600,
  "session_id": "session-abc"
}
```

## Handlers

| Handler | Token Budget | TTL | When |
|---------|-------------|-----|------|
| `code` | 4096 | 1h | Writing/fixing code |
| `chat` | 2048 | 30m | General conversation |
| `threat_intel` | 8192 | 2h | Security analysis |
| `operations` | 2048 | 1h | Infrastructure tasks |
| `research` | 8192 | 4h | Deep research |
| `default` | 2048 | 30m | Fallback |

## Architecture

```
Query → classify_intent → assign_token_budget → record_route → return
                              │
                         SQLite persistence
                         (importance score, TTL, history)
```

## Why this exists

Context windows are expensive real estate. Throwing 8K tokens at a
"hello" query burns money. Throwing 512 tokens at a threat analysis
misses the threat. This router allocates budget based on what the
agent is actually doing.
