# -*- encoding: utf-8 -*-
"""
KGQL Edge Registry - Protocol-based edge resolver registry.

This module provides the EdgeResolverRegistry that manages multiple
EdgeResolver implementations, enabling KGQL to traverse edges across
different protocols with uniform semantics.

Usage:
    from kgql.wrappers import EdgeResolverRegistry, ACDCEdgeResolver

    # Create registry with ACDC resolver
    registry = EdgeResolverRegistry()
    registry.register(ACDCEdgeResolver())

    # Resolve an edge
    edge_ref = registry.resolve_edge(credential, "iss")
    if edge_ref:
        print(f"Target: {edge_ref.target_said}")
"""

from typing import Any, Optional

from kgql.wrappers.edge_resolver import EdgeResolver, EdgeRef


class EdgeResolverRegistry:
    """
    Registry of edge resolvers by protocol.

    Manages multiple EdgeResolver implementations and provides unified
    edge resolution across protocols. Resolvers are registered by their
    protocol identifier and can be queried individually or tried in sequence.

    Attributes:
        _resolvers: Dict mapping protocol names to resolver instances
    """

    def __init__(self):
        """Initialize empty registry."""
        self._resolvers: dict[str, EdgeResolver] = {}

    def register(self, resolver: EdgeResolver) -> None:
        """
        Register a resolver for its protocol.

        Args:
            resolver: EdgeResolver instance to register
        """
        self._resolvers[resolver.protocol] = resolver

    def unregister(self, protocol: str) -> Optional[EdgeResolver]:
        """
        Remove and return a resolver by protocol.

        Args:
            protocol: Protocol identifier to remove

        Returns:
            The removed resolver, or None if not found
        """
        return self._resolvers.pop(protocol, None)

    def get(self, protocol: str) -> Optional[EdgeResolver]:
        """
        Get a resolver by protocol name.

        Args:
            protocol: Protocol identifier (e.g., "keri", "s3")

        Returns:
            EdgeResolver for the protocol, or None if not registered
        """
        return self._resolvers.get(protocol)

    def protocols(self) -> list[str]:
        """
        List all registered protocols.

        Returns:
            List of protocol identifiers
        """
        return list(self._resolvers.keys())

    def __len__(self) -> int:
        """Return number of registered resolvers."""
        return len(self._resolvers)

    def __contains__(self, protocol: str) -> bool:
        """Check if a protocol is registered."""
        return protocol in self._resolvers

    def resolve_edge(
        self,
        content: Any,
        edge_name: str,
        protocol_hint: Optional[str] = None
    ) -> Optional[EdgeRef]:
        """
        Resolve an edge from content, optionally with protocol hint.

        If protocol_hint is provided, only that protocol's resolver is used.
        Otherwise, all resolvers are tried until one succeeds.

        Args:
            content: Source content (credential, S3 metadata, etc.)
            edge_name: Edge key to resolve (e.g., "acdc", "iss")
            protocol_hint: If provided, use only this protocol's resolver

        Returns:
            EdgeRef if found, None otherwise
        """
        # Use specific resolver if hint provided
        if protocol_hint:
            resolver = self._resolvers.get(protocol_hint)
            if resolver:
                try:
                    return resolver.get_edge(content, edge_name)
                except (KeyError, TypeError, AttributeError, ValueError):
                    return None
            return None

        # Try each resolver that can handle this content
        for resolver in self._resolvers.values():
            try:
                if resolver.can_resolve(content):
                    edge = resolver.get_edge(content, edge_name)
                    if edge:
                        return edge
            except (KeyError, TypeError, AttributeError, ValueError):
                continue

        return None

    def list_edges(
        self,
        content: Any,
        protocol_hint: Optional[str] = None
    ) -> list[str]:
        """
        List all edges in content.

        Args:
            content: Source content to inspect
            protocol_hint: If provided, use only this protocol's resolver

        Returns:
            List of edge keys found
        """
        if protocol_hint:
            resolver = self._resolvers.get(protocol_hint)
            if resolver:
                try:
                    return resolver.list_edges(content)
                except (KeyError, TypeError, AttributeError, ValueError):
                    return []
            return []

        # Collect edges from first resolver that can handle content
        for resolver in self._resolvers.values():
            try:
                if resolver.can_resolve(content):
                    edges = resolver.list_edges(content)
                    if edges:
                        return edges
            except (KeyError, TypeError, AttributeError, ValueError):
                continue

        return []

    def list_all_edges(self, content: Any) -> dict[str, list[str]]:
        """
        List edges from all resolvers that can parse this content.

        Useful for debugging or when content might be interpretable
        by multiple protocols.

        Args:
            content: Source content to inspect

        Returns:
            Dict mapping protocol names to lists of edge keys
        """
        result: dict[str, list[str]] = {}

        for protocol, resolver in self._resolvers.items():
            try:
                if resolver.can_resolve(content):
                    edges = resolver.list_edges(content)
                    if edges:
                        result[protocol] = edges
            except (KeyError, TypeError, AttributeError, ValueError):
                continue

        return result

    def resolve_all_edges(self, content: Any) -> dict[str, EdgeRef]:
        """
        Resolve all edges in content.

        Args:
            content: Source content to inspect

        Returns:
            Dict mapping edge names to EdgeRef objects
        """
        result: dict[str, EdgeRef] = {}

        # Get list of edges
        edge_names = self.list_edges(content)

        # Resolve each edge
        for edge_name in edge_names:
            edge_ref = self.resolve_edge(content, edge_name)
            if edge_ref:
                result[edge_name] = edge_ref

        return result


def create_default_registry() -> EdgeResolverRegistry:
    """
    Create a registry with standard resolvers.

    Includes:
        - ACDCEdgeResolver (KERI/ACDC credential edges)
        - PatternSpaceEdgeResolver (concept/pattern ontology graph)

    Returns:
        EdgeResolverRegistry with default resolvers registered
    """
    from kgql.wrappers.acdc_edge_resolver import ACDCEdgeResolver
    from kgql.wrappers.pattern_space_resolver import PatternSpaceEdgeResolver

    registry = EdgeResolverRegistry()
    registry.register(ACDCEdgeResolver())
    registry.register(PatternSpaceEdgeResolver())
    return registry
