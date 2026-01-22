# KGQL MCP Server

Model Context Protocol (MCP) server for KERI Graph Query Language.

Enables Claude Code and other MCP clients to query the KERI credential graph directly.

## Installation

### Claude Code Configuration

Add to `.claude/settings.local.json`:

```json
{
  "mcpServers": {
    "kgql": {
      "command": "python3",
      "args": ["-m", "kgql.mcp"],
      "env": {
        "KGQL_HABERY_NAME": "kgql",
        "KERI_BASE": "~/.keri"
      }
    }
  }
}
```

Environment variables (all optional):
- `KGQL_HABERY_NAME`: Name for the KERI Habery (default: "kgql")
- `KERI_BASE`: Base path for KERI data (default: ~/.keri)

### Running Standalone

```bash
# As module
python -m kgql.mcp

# Direct invocation
python kgql/mcp/server.py
```

## Tools

### `kgql_resolve`

Resolve a credential by SAID.

```
Input: { "said": "ESAID..." }
Output: { "found": true, "said": "...", "issuer": "...", "subject": "...", "schema": "...", "data": {...} }
```

### `kgql_by_issuer`

Get all credentials issued by an AID.

```
Input: { "aid": "EAID..." }
Output: { "issuer": "...", "count": 5, "credentials": [{"said": "..."}] }
```

### `kgql_by_schema`

Get all credentials using a specific schema.

```
Input: { "schema_said": "ESAID..." }
Output: { "schema": "...", "count": 3, "credentials": [{"said": "..."}] }
```

### `kgql_verify_chain`

Verify complete attestation chain: Turn → Session → Master.

This is the critical audit function that proves a turn credential chains back to the master AID.

```
Input: { "turn_said": "ESAID..." }
Output: {
  "valid": true,
  "turn_said": "...",
  "chain_length": 3,
  "kel_anchored": true,
  "chain": [
    {"type": "turn", "said": "..."},
    {"type": "session", "said": "..."},
    {"type": "master_delegation", "said": "...", "master_pre": "...", "kel_verified": true}
  ]
}
```

### `kgql_query`

Execute a raw KGQL query.

```
Input: {
  "query_string": "MATCH (c:Credential) WHERE c.issuer = $aid",
  "variables": {"aid": "EAID..."}
}
Output: { "query": "...", "count": 2, "items": [...], "metadata": {...} }
```

Supported operations:
- `MATCH (c:Credential) WHERE c.issuer = $aid`
- `RESOLVE $said`
- `VERIFY $said`
- `TRAVERSE FROM $said FOLLOW edge`

### `kgql_stats`

Get overall KERI infrastructure statistics.

```
Input: {}
Output: {
  "credentials_in_reger": 42,
  "aids_in_habery": 3,
  "sessions_tracked": 5,
  "sessions_with_attestation": 4,
  "total_turns": 127,
  "infrastructure_initialized": true
}
```

### `kgql_session_audit`

Audit a specific session's attestation status.

```
Input: { "session_id": "session-123" }
Output: {
  "session_id": "session-123",
  "session_aid": "EAID...",
  "session_credential_said": "ESAID...",
  "turn_count": 15,
  "delegation_status": "active",
  "kel_verified": true,
  "credentials_issued": 45,
  "credential_saids": ["ESAID1...", "ESAID2..."]
}
```

## Integration with Smart Context Server

This server complements the `smart-context` MCP server:

| Server | Purpose |
|--------|---------|
| **smart-context** | Content size awareness, RLM recommendations |
| **kgql** | Credential verification, chain auditing |

**Together:** Full attestation-aware context management.

## Architecture

```
┌─────────────────────────────────────────────┐
│             Claude Code                     │
└─────────────────┬───────────────────────────┘
                  │ MCP (stdio)
                  ▼
┌─────────────────────────────────────────────┐
│          KGQLMCPServer                      │
│  - Lazy KERI infrastructure initialization  │
│  - Tool dispatch to KGQL API                │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│              KGQL                           │
│  - Parser, Planner, Executor                │
│  - Wraps keripy Habery/Regery               │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│            keripy                           │
│  - Habery (AIDs, KELs)                      │
│  - Regery (credentials, TELs)              │
└─────────────────────────────────────────────┘
```

## Development

### Testing

```bash
# Test server initialization
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python -m kgql.mcp

# List tools
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python -m kgql.mcp

# Get stats
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"kgql_stats","arguments":{}}}' | python -m kgql.mcp
```

### Programmatic Usage

```python
from kgql.mcp import KGQLMCPServer

server = KGQLMCPServer()

# Handle a tool call directly
result = server.handle_tool_call("kgql_stats", {})
print(result)
```

## Core Principle

**"Resolution IS Verification"**

If you can resolve a SAID through KGQL, the credential exists and its integrity is guaranteed by the cryptographic binding. The graph is the audit trail.
