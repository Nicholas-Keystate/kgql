#!/usr/bin/env python3
"""
KGQL MCP Server - KERI Graph Query Language tools for MCP clients.

Provides direct credential graph access via MCP, enabling clients to:
- Resolve credentials by SAID
- Query credentials by issuer, subject, schema
- Verify attestation chains (Turn → Session → Master)
- Execute dynamic KGQL queries

Architecture:
    This server wraps the KGQL API for MCP access. It uses lazy initialization
    to avoid loading KERI infrastructure until the first tool call.

Usage:
    # Run as MCP server (stdio transport)
    python -m kgql.mcp

    # Or from this file directly
    python server.py

    # Configure in Claude Code settings.local.json:
    {
        "mcpServers": {
            "kgql": {
                "command": "python3",
                "args": ["-m", "kgql.mcp"],
                "env": {}
            }
        }
    }
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

# MCP Protocol version
PROTOCOL_VERSION = "2024-11-05"


class KGQLMCPServer:
    """
    MCP Server for KGQL credential queries.

    Uses lazy initialization - KERI infrastructure is only loaded
    on first tool call, not on server startup.
    """

    def __init__(
        self,
        habery_name: Optional[str] = None,
        keri_base: Optional[str] = None,
        session_state_dir: Optional[Path] = None,
    ):
        """
        Initialize the KGQL MCP server.

        Args:
            habery_name: Name for the KERI Habery (default: "kgql")
            keri_base: Base path for KERI data (default: ~/.keri)
            session_state_dir: Path to session state files.
                              Defaults to ~/.claude/keri_session/state
        """
        self._habery_name = habery_name or os.environ.get("KGQL_HABERY_NAME", "kgql")
        self._keri_base = keri_base or os.environ.get(
            "KERI_BASE",
            str(Path.home() / ".keri")
        )
        self._session_state_dir = session_state_dir or (
            Path.home() / ".claude" / "keri_session" / "state"
        )

        # Lazy-loaded instances
        self._infra = None
        self._kgql = None

        # Tool registry
        self._tools = self._build_tool_registry()

    def _get_infrastructure(self):
        """Get or initialize KERI infrastructure."""
        if self._infra is None:
            try:
                from keri.app import habbing
                from keri.vdr import viring

                # Ensure KERI base directory exists
                keri_base = Path(self._keri_base)
                keri_base.mkdir(parents=True, exist_ok=True)

                # Initialize Habery (persistent)
                hby = habbing.Habery(
                    name=self._habery_name,
                    base=str(keri_base),
                    temp=False
                )

                # Initialize Regery
                rgy = viring.Regery(
                    hby=hby,
                    name=self._habery_name,
                    base=str(keri_base),
                    temp=False
                )

                # Create infrastructure container
                class KeriInfra:
                    def __init__(self, hby, rgy):
                        self.hby = hby
                        self.rgy = rgy

                self._infra = KeriInfra(hby, rgy)

            except Exception as e:
                return None, f"Failed to initialize KERI infrastructure: {e}"
        return self._infra, None

    def _get_kgql(self):
        """Get or initialize KGQL instance."""
        if self._kgql is None:
            infra, error = self._get_infrastructure()
            if error:
                return None, error
            try:
                from kgql import KGQL
                self._kgql = KGQL(hby=infra.hby, rgy=infra.rgy, verifier=None)
            except ImportError:
                return None, "KGQL module not available"
            except Exception as e:
                return None, str(e)
        return self._kgql, None

    # Tool implementations

    def _tool_resolve(self, said: str) -> dict:
        """Resolve a credential by SAID."""
        kgql, error = self._get_kgql()
        if error:
            return {"error": error}

        result = kgql.resolve(said)
        if not result:
            return {
                "found": False,
                "said": said,
                "hint": "Credential not in Reger. May not be issued or SAID is incorrect."
            }

        return {
            "found": True,
            "said": result.said,
            "issuer": result.data.get("issuer") if isinstance(result.data, dict) else None,
            "subject": result.data.get("subject") if isinstance(result.data, dict) else None,
            "schema": result.data.get("schema") if isinstance(result.data, dict) else None,
            "data": result.data if isinstance(result.data, dict) else {},
        }

    def _tool_by_issuer(self, aid: str) -> dict:
        """Get all credentials issued by an AID."""
        kgql, error = self._get_kgql()
        if error:
            return {"error": error}

        result = kgql.by_issuer(aid)
        return {
            "issuer": aid,
            "count": len(result),
            "credentials": [{"said": item.said} for item in result]
        }

    def _tool_by_schema(self, schema_said: str) -> dict:
        """Get all credentials using a specific schema."""
        kgql, error = self._get_kgql()
        if error:
            return {"error": error}

        result = kgql.query(
            "MATCH (c:Credential) WHERE c.schema = $schema",
            variables={"schema": schema_said}
        )
        return {
            "schema": schema_said,
            "count": len(result),
            "credentials": [{"said": item.said} for item in result]
        }

    def _tool_verify_chain(self, turn_said: str) -> dict:
        """
        Verify complete attestation chain: Turn → Session → Master.

        This is the critical audit function that proves a turn
        credential chains back to the master AID.
        """
        kgql, error = self._get_kgql()
        if error:
            return {"error": error}

        result = kgql.verify_end_to_end_chain(turn_said)

        if result.metadata.get("valid"):
            chain_data = result.first.data if result.first else {}
            return {
                "valid": True,
                "turn_said": turn_said,
                "chain_length": result.metadata.get("chain_length", 0),
                "kel_anchored": chain_data.get("kel_anchored", False),
                "chain": chain_data.get("chain", []),
            }
        else:
            return {
                "valid": False,
                "turn_said": turn_said,
                "error": result.metadata.get("error", "Unknown verification failure"),
                "chain": result.metadata.get("chain", []),
            }

    def _tool_query(self, query_string: str, variables: Optional[dict] = None) -> dict:
        """
        Execute a raw KGQL query.

        Supports:
        - MATCH (c:Credential) WHERE c.issuer = $aid
        - RESOLVE $said
        - VERIFY $said
        - TRAVERSE FROM $said FOLLOW edge
        """
        kgql, error = self._get_kgql()
        if error:
            return {"error": error}

        try:
            result = kgql.query(query_string, variables or {})
            return {
                "query": query_string,
                "count": len(result),
                "items": [
                    {
                        "said": item.said,
                        "data": item.data if isinstance(item.data, dict) else {},
                    }
                    for item in result
                ],
                "metadata": result.metadata,
            }
        except Exception as e:
            return {
                "error": f"Query failed: {e}",
                "query": query_string,
            }

    def _tool_stats(self) -> dict:
        """Get overall KERI infrastructure statistics."""
        infra, error = self._get_infrastructure()
        if error:
            return {"error": error}

        # Count credentials
        try:
            cred_count = sum(1 for _ in infra.rgy.reger.creds.getItemIter())
        except Exception:
            cred_count = 0

        # Count AIDs
        try:
            aid_count = len(infra.hby.habs) if hasattr(infra.hby, 'habs') else 0
        except Exception:
            aid_count = 0

        # Count sessions from state files
        session_count = 0
        total_turns = 0
        attested_sessions = 0

        if self._session_state_dir.exists():
            for state_file in self._session_state_dir.glob("*.json"):
                if state_file.name.endswith("_recovery.json"):
                    continue
                try:
                    with open(state_file) as f:
                        state = json.load(f)
                    session_count += 1
                    turns = state.get("session", {}).get("turn_count", 0)
                    total_turns += turns
                    if state.get("last_attestation"):
                        attested_sessions += 1
                except Exception:
                    pass

        return {
            "credentials_in_reger": cred_count,
            "aids_in_habery": aid_count,
            "sessions_tracked": session_count,
            "sessions_with_attestation": attested_sessions,
            "total_turns": total_turns,
            "infrastructure_initialized": infra is not None,
        }

    def _tool_session_audit(self, session_id: str) -> dict:
        """
        Audit a specific session's attestation status.

        Returns session info, credentials issued, and chain status.
        """
        state_file = self._session_state_dir / f"{session_id}.json"
        if not state_file.exists():
            return {"error": f"Session not found: {session_id}"}

        try:
            with open(state_file) as f:
                state = json.load(f)
        except Exception as e:
            return {"error": f"Failed to load session state: {e}"}

        session = state.get("session", {})
        delegation = state.get("delegation", {})
        last_attestation = state.get("last_attestation", {})

        result = {
            "session_id": session_id,
            "session_aid": session.get("session_aid"),
            "session_credential_said": session.get("session_credential_said"),
            "turn_count": session.get("turn_count", 0),
            "delegation_status": delegation.get("delegation_status"),
            "kel_verified": delegation.get("kel_verified", False),
        }

        # Get credentials issued by this session
        if session.get("session_aid"):
            kgql, error = self._get_kgql()
            if not error:
                creds = kgql.by_issuer(session["session_aid"])
                result["credentials_issued"] = len(creds)
                result["credential_saids"] = [c.said for c in creds][:10]  # Limit to 10

        # Add last attestation info
        if last_attestation:
            result["last_turn_said"] = last_attestation.get("turn_credential_said")
            result["last_turn_sequence"] = last_attestation.get("turn_sequence")

        return result

    def _build_tool_registry(self) -> list[dict]:
        """Build the MCP tool registry."""
        return [
            {
                "name": "kgql_resolve",
                "description": "Resolve a credential by SAID. Returns credential details including issuer, subject, schema, and attributes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "said": {
                            "type": "string",
                            "description": "The credential SAID to resolve"
                        }
                    },
                    "required": ["said"]
                }
            },
            {
                "name": "kgql_by_issuer",
                "description": "Get all credentials issued by a specific AID. Useful for auditing what a session has attested.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "aid": {
                            "type": "string",
                            "description": "The issuer AID prefix"
                        }
                    },
                    "required": ["aid"]
                }
            },
            {
                "name": "kgql_by_schema",
                "description": "Get all credentials using a specific schema. Useful for finding all turn credentials, session credentials, etc.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "schema_said": {
                            "type": "string",
                            "description": "The schema SAID to filter by"
                        }
                    },
                    "required": ["schema_said"]
                }
            },
            {
                "name": "kgql_verify_chain",
                "description": "Verify complete attestation chain: Turn -> Session -> Master. This is the critical audit function that proves a turn credential chains back to the master AID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "turn_said": {
                            "type": "string",
                            "description": "The turn credential SAID to verify"
                        }
                    },
                    "required": ["turn_said"]
                }
            },
            {
                "name": "kgql_query",
                "description": "Execute a raw KGQL query. Supports MATCH, RESOLVE, VERIFY, and TRAVERSE operations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_string": {
                            "type": "string",
                            "description": "The KGQL query to execute (e.g., 'MATCH (c:Credential) WHERE c.issuer = $aid')"
                        },
                        "variables": {
                            "type": "object",
                            "description": "Variable bindings for the query",
                            "additionalProperties": True
                        }
                    },
                    "required": ["query_string"]
                }
            },
            {
                "name": "kgql_stats",
                "description": "Get overall KERI infrastructure statistics: credential counts, AID counts, session counts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "kgql_session_audit",
                "description": "Audit a specific session's attestation status. Returns session info, credentials issued, and chain status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID to audit"
                        }
                    },
                    "required": ["session_id"]
                }
            }
        ]

    def handle_tool_call(self, name: str, arguments: dict) -> Any:
        """Handle a tool call and return result."""
        handlers: dict[str, Callable] = {
            "kgql_resolve": lambda args: self._tool_resolve(args.get("said", "")),
            "kgql_by_issuer": lambda args: self._tool_by_issuer(args.get("aid", "")),
            "kgql_by_schema": lambda args: self._tool_by_schema(args.get("schema_said", "")),
            "kgql_verify_chain": lambda args: self._tool_verify_chain(args.get("turn_said", "")),
            "kgql_query": lambda args: self._tool_query(
                args.get("query_string", ""),
                args.get("variables")
            ),
            "kgql_stats": lambda args: self._tool_stats(),
            "kgql_session_audit": lambda args: self._tool_session_audit(args.get("session_id", "")),
        }

        handler = handlers.get(name)
        if handler:
            return handler(arguments)
        return {"error": f"Unknown tool: {name}"}

    def handle_request(self, request: dict) -> Optional[dict]:
        """Handle a JSON-RPC request and return response."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "kgql",
                        "version": "1.0.0"
                    }
                }
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self._tools
                }
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            result = self.handle_tool_call(tool_name, arguments)

            # Format as text content for MCP
            content_text = json.dumps(result, indent=2)

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": content_text
                        }
                    ]
                }
            }

        elif method == "notifications/initialized":
            # No response needed for notifications
            return None

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

    def run(self):
        """Run the MCP server (stdio transport)."""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                request = json.loads(line)
            except json.JSONDecodeError:
                continue

            response = self.handle_request(request)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


def main():
    """CLI entry point for the KGQL MCP server."""
    server = KGQLMCPServer()
    server.run()


if __name__ == "__main__":
    main()
