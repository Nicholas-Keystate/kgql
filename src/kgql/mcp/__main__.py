#!/usr/bin/env python3
"""
Entry point for running KGQL MCP server as a module.

Usage:
    python -m kgql.mcp
"""

from kgql.mcp.server import main

if __name__ == "__main__":
    main()
