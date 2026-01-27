"""
KGQL MCP Server - Model Context Protocol server for KERI credential queries.

This module provides an MCP server that exposes KGQL functionality to
any MCP-compatible client.

Usage:
    # Run as standalone server
    python -m kgql.mcp

    # Or import and use programmatically
    from kgql.mcp import KGQLMCPServer
    server = KGQLMCPServer()
    server.run()
"""

from kgql.mcp.server import KGQLMCPServer, main

__all__ = ["KGQLMCPServer", "main"]
