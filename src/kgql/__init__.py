"""
KGQL - KERI Graph Query Language

A declarative query language and thin wrapper over existing keripy infrastructure.
Enables ambient key state querying without duplicating existing functionality.

Core Principles:
- "Resolution IS Verification" - If a SAID resolves, the credential exists
- "Don't Duplicate, Integrate" - Thin wrappers over keripy, not reimplementation

Components:
- KGQL: Main query interface
- kgql.export: Graph export to Neo4j, RDF, Mermaid, property graph
- kgql.mcp: MCP server for LLM tool integration

Usage:
    from kgql import KGQL

    # Initialize with keripy instances
    kgql = KGQL(hby=hby, rgy=rgy, verifier=verifier)

    # Execute queries
    result = kgql.query("RESOLVE $said", variables={"said": "ESAID..."})

    # Export to external formats
    cypher = kgql.export(result, "neo4j")
    mermaid = kgql.export(result, "mermaid")

    # Or run MCP server
    # python -m kgql.mcp
"""

from kgql.api.kgql import KGQL, QueryResult, QueryResultItem
from kgql.parser.ast import (
    KGQLQuery,
    MatchOperation,
    ResolveOperation,
    TraverseOperation,
    VerifyOperation,
    EdgeOperator,
)

# Export module - import lazily to avoid circular dependencies
# Use: from kgql.export import PropertyGraph, export_neo4j, etc.

__all__ = [
    # Main API
    "KGQL",
    "QueryResult",
    "QueryResultItem",
    # AST types
    "KGQLQuery",
    "MatchOperation",
    "ResolveOperation",
    "TraverseOperation",
    "VerifyOperation",
    "EdgeOperator",
]

__version__ = "0.1.0"
