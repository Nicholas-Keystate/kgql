"""
KGQL - KERI Graph Query Language

A declarative query language and thin wrapper over existing keripy infrastructure.
Enables ambient key state querying without duplicating existing functionality.

Core Principles:
- "Resolution IS Verification" - If a SAID resolves, the credential exists
- "Don't Duplicate, Integrate" - Thin wrappers over keripy, not reimplementation

Components:
- KGQL: Main query interface
- kgql.mcp: MCP server for Claude Code integration

Usage:
    from kgql import KGQL

    # Initialize with keripy instances
    kgql = KGQL(hby=hby, rgy=rgy, verifier=verifier)

    # Execute queries
    result = kgql.query("RESOLVE $said", variables={"said": "ESAID..."})

    # Or use MCP server for Claude Code
    # python -m kgql.mcp
"""

from kgql.api.kgql import KGQL
from kgql.parser.ast import (
    KGQLQuery,
    MatchOperation,
    ResolveOperation,
    TraverseOperation,
    VerifyOperation,
    EdgeOperator,
)

__all__ = [
    "KGQL",
    "KGQLQuery",
    "MatchOperation",
    "ResolveOperation",
    "TraverseOperation",
    "VerifyOperation",
    "EdgeOperator",
]

__version__ = "0.1.0"
