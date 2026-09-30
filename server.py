#!/usr/bin/env python3
"""
Agent Context Route — MCP stdio JSON-RPC server
================================================
Decides WHAT context the agent needs and HOW MUCH token budget to allocate.
Zero dependencies, Python 3.10+ stdlib only.
Protocol: MCP (Model Context Protocol) via stdio.
Philosophy: "Importance over recency."

Repository: github.com/ARES-SYS/agent-context-route
"""

import sys
import json
import sqlite3
import hashlib
import time
import os
from pathlib import Path

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════

DB_PATH = os.path.expanduser(os.environ.get("CTX_ROUTE_DB", "~/.agent_context_route.db"))

# Default token budgets per handler type
TOKEN_BUDGETS = {
    "code":         {"max_tokens": 4096, "ttl": 3600},
    "chat":         {"max_tokens": 2048, "ttl": 1800},
    "threat_intel": {"max_tokens": 8192, "ttl": 7200},
    "operations":   {"max_tokens": 2048, "ttl": 3600},
    "research":     {"max_tokens": 8192, "ttl": 14400},
    "default":      {"max_tokens": 2048, "ttl": 1800},
}

# ═══════════════════════════════════════════════════════
# SQLite persistence
# ═══════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS context_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            handler TEXT NOT NULL,
            query_hash TEXT NOT NULL,
            token_budget INTEGER NOT NULL,
            importance_score REAL DEFAULT 0.5,
            ttl INTEGER NOT NULL,
            created_at REAL NOT NULL,
            accessed_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocked_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL,
            blocked_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def record_route(session_id, handler, query_hash, token_budget, importance=0.5, ttl=1800):
    conn = get_db()
    now = time.time()
    conn.execute(
        "INSERT INTO context_routes (session_id, handler, query_hash, token_budget, importance_score, ttl, created_at, accessed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, handler, query_hash, token_budget, importance, ttl, now, now)
    )
    conn.commit()
    conn.close()


def get_route_history(session_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT handler, query_hash, token_budget, importance_score, ttl, created_at FROM context_routes WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    conn.close()
    return [{"handler": r[0], "query_hash": r[1], "token_budget": r[2], "importance": r[3], "ttl": r[4], "created_at": r[5]} for r in rows]


def clean_expired():
    conn = get_db()
    now = time.time()
    conn.execute("DELETE FROM context_routes WHERE created_at + ttl < ?", (now,))
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════
# CLASSIFICATION
# ═══════════════════════════════════════════════════════

INTENT_PATTERNS = {
    "code":         ["code", "script", "function", "python", "bash", "command", "fix", "compile", "git", "docker", "import ", "def ", "class "],
    "threat_intel": ["attack", "malware", "c2", "beacon", "ioc", "threat", "exploit", "vuln", "adversary", "apt", "ransomware"],
    "operations":   ["deploy", "server", "backup", "config", "service", "restart", "monitor", "log", "disk", "cpu", "memory"],
    "research":     ["research", "paper", "arxiv", "study", "analysis", "survey", "literature", "review"],
}


def classify_intent(query: str) -> tuple:
    """Classify the intent of a query. Returns (handler, confidence, importance)."""
    query_lower = query.lower()
    scores = {}
    for handler, keywords in INTENT_PATTERNS.items():
        hits = sum(1 for kw in keywords if kw in query_lower)
        if hits > 0:
            scores[handler] = hits / len(keywords)

    if not scores:
        return "chat", 0.3, 0.3

    best = max(scores, key=scores.get)
    confidence = min(scores[best] * 2, 1.0)
    importance = min(scores[best] * 1.5, 1.0)

    return best, round(confidence, 2), round(importance, 2)


# ═══════════════════════════════════════════════════════
# ROUTING
# ═══════════════════════════════════════════════════════

def route(query: str, session_id: str = "default") -> dict:
    """Main routing function. Classifies intent, assigns token budget, records."""
    clean_expired()

    handler, confidence, importance = classify_intent(query)
    budget = TOKEN_BUDGETS.get(handler, TOKEN_BUDGETS["default"])
    query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

    record_route(session_id, handler, query_hash, budget["max_tokens"], importance, budget["ttl"])

    history = get_route_history(session_id, 5)

    return {
        "handler": handler,
        "confidence": confidence,
        "importance": importance,
        "token_budget": budget["max_tokens"],
        "ttl": budget["ttl"],
        "query_hash": query_hash,
        "session_id": session_id,
        "recent_routes": history,
    }


# ═══════════════════════════════════════════════════════
# MCP PROTOCOL (stdio JSON-RPC)
# ═══════════════════════════════════════════════════════

def handle_request(request: dict) -> dict:
    """Handle a JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "0.1.0",
                "serverInfo": {
                    "name": "agent-context-route",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {}
                }
            }
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [{
                    "name": "route_context",
                    "description": "Classify a query and determine optimal context routing with token budget",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The user query to classify"},
                            "session_id": {"type": "string", "description": "Session identifier for context tracking"}
                        },
                        "required": ["query"]
                    }
                }]
            }
        }

    if method == "tools/call":
        tool_name = request.get("params", {}).get("name")
        arguments = request.get("params", {}).get("arguments", {})

        if tool_name == "route_context":
            query = arguments.get("query", "")
            session_id = arguments.get("session_id", "default")
            result = route(query, session_id)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}


def main():
    """MCP stdio loop."""
    print("[CTX-ROUTE] Agent Context Route MCP server ready", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            sys.stdout.write(json.dumps(error) + "\n")
            sys.stdout.flush()
        except Exception as e:
            error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(error) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
