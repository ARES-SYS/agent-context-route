# Agent Context Route — Design Reasoning

## Origin

Agents waste tokens. A "hello" gets 8K of context. A threat analysis gets 512.
Both are wrong. Both burn money. Both degrade the agent.

I built this because the context window is the most expensive real estate
in AI agents, and no one was managing it properly.

## The problem with "recent first"

Every RAG system defaults to recency. The most recent chunks win.
This is wrong for three reasons:

1. **Recency != relevance.** The code snippet from 3 hours ago is more
   important than the chat message from 30 seconds ago when the agent
   is writing code.

2. **Token budgets are fixed.** Most systems use a flat N chunks or
   fixed token count. A threat analysis needs 8K tokens to surface
   IOCs. A "hello" needs 128. Same budget for both burns money.

3. **No memory of decisions.** Without persistence, every query starts
   from zero. The router should remember that this session is doing
   threat intel and bias future routes accordingly.

## Design decisions

### Importance over recency

The router classifies intent FIRST, then assigns a token budget.
The query "analyze this C2 beacon" gets 8192 tokens and 2h TTL
regardless of when it was asked. "Hello" gets 2048 and 30m TTL.

### Handler budgets, not global budgets

Different tasks have different information density:
- Code tasks: high density, needs context about functions, imports, types
- Chat: low density, needs conversational context only
- Threat intel: highest density, needs IOCs, TTPs, infrastructure maps

Each handler gets its own budget tuned to the task.

### SQLite persistence

Records every route decision with importance score and TTL.
This means:
- The agent can ask "what was I doing?" and get the handler history
- Expired routes self-clean (no memory leak)
- Session-based routing: first query sets the handler bias

## What I would do differently

1. **Embedding-based classification.** Keyword matching works but misses
   nuance. Running the query through the same Ollama model for intent
   classification would catch semantic intent better.

2. **Dynamic budget adjustment.** If the first 5 queries in a session
   are all code-related, automatically increase the code handler budget
   and decrease others. Adaptive routing.

3. **Multi-agent routing.** Different agents (coder, analyst, operator)
   should get different default budgets. The same query from a coder
   agent vs. an analyst agent should route differently.

## Connection to the ecosystem

| Repo | Role | Connection |
|------|------|-----------|
| `agent-context-route` | Context routing | This repo |
| `agent-context-router` | Defense + routing (HTTP) | Same logic, different protocol + defense |
| `pioneer` | Memory system | Supplies the chunks this router decides on |
| `prompt-injection-guard` | Input defense | Complements the router's budget decisions |
| `oracle-poisoning-advisory` | Threat model | Documents why routing matters for security |

The router doesn't block attacks — it starves them. A malicious injection
needs context to work. If the router gives it 128 tokens instead of 8192,
the attack surface collapses.
