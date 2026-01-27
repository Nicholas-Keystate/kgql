# -*- encoding: utf-8 -*-
"""Tests for PatternSpaceEdgeResolver."""

import json
import tempfile
from pathlib import Path

import pytest

from kgql.wrappers import (
    PatternSpaceEdgeResolver,
    EdgeResolverRegistry,
    create_default_registry,
)


@pytest.fixture
def edges_file(tmp_path):
    """Create a temporary edges.json file."""
    edges_data = {
        "version": "1.0.0",
        "edges": [
            {
                "source": "habery",
                "source_type": "concept",
                "target": "singleton-prevention",
                "target_type": "concept",
                "edge_type": "references",
                "weight": 1.0,
            },
            {
                "source": "keri-runtime-singleton",
                "source_type": "pattern",
                "target": "habery",
                "target_type": "concept",
                "edge_type": "references",
                "weight": 1.0,
            },
            {
                "source": "keri-runtime-singleton",
                "source_type": "pattern",
                "target": "hio-doer-lifecycle",
                "target_type": "pattern",
                "edge_type": "composable_with",
                "weight": 0.8,
            },
            {
                "source": "keri-runtime-singleton",
                "source_type": "pattern",
                "target": "import-time-init",
                "target_type": "pattern",
                "edge_type": "conflicts_with",
                "weight": 1.0,
            },
        ],
    }
    path = tmp_path / "edges.json"
    path.write_text(json.dumps(edges_data))
    return path


@pytest.fixture
def resolver(edges_file):
    """Resolver loaded from test edges file (no registries)."""
    return PatternSpaceEdgeResolver(
        edges_path=edges_file,
        load_registries=False,
    )


class TestProtocol:
    """Protocol identification."""

    def test_protocol_name(self, resolver):
        assert resolver.protocol == "pattern-space"


class TestCanResolve:
    """Content detection."""

    def test_accepts_dict_with_slug(self, resolver):
        assert resolver.can_resolve({"slug": "habery"})

    def test_rejects_dict_without_slug(self, resolver):
        assert not resolver.can_resolve({"name": "habery"})

    def test_rejects_non_dict(self, resolver):
        assert not resolver.can_resolve("habery")
        assert not resolver.can_resolve(None)
        assert not resolver.can_resolve(42)


class TestListEdges:
    """Listing edges from a node."""

    def test_list_edges_concept(self, resolver):
        edges = resolver.list_edges({"slug": "habery"})
        assert edges == ["references:singleton-prevention"]

    def test_list_edges_pattern(self, resolver):
        edges = resolver.list_edges({"slug": "keri-runtime-singleton"})
        assert set(edges) == {
            "references:habery",
            "composable_with:hio-doer-lifecycle",
            "conflicts_with:import-time-init",
        }

    def test_list_edges_unknown_slug(self, resolver):
        edges = resolver.list_edges({"slug": "nonexistent"})
        assert edges == []

    def test_list_edges_invalid_content(self, resolver):
        assert resolver.list_edges("not a dict") == []
        assert resolver.list_edges({}) == []


class TestGetEdge:
    """Resolving specific edges."""

    def test_get_edge_by_type_and_target(self, resolver):
        edge = resolver.get_edge(
            {"slug": "keri-runtime-singleton"},
            "references:habery",
        )
        assert edge is not None
        assert edge.target_said == "habery"
        assert edge.edge_type == "references"
        assert edge.source_protocol == "pattern-space"
        assert edge.metadata["source"] == "keri-runtime-singleton"
        assert edge.metadata["target_type"] == "concept"

    def test_get_edge_by_type_only(self, resolver):
        edge = resolver.get_edge(
            {"slug": "keri-runtime-singleton"},
            "references",
        )
        assert edge is not None
        assert edge.target_said == "habery"

    def test_get_edge_nonexistent(self, resolver):
        edge = resolver.get_edge(
            {"slug": "keri-runtime-singleton"},
            "extends:something",
        )
        assert edge is None

    def test_get_edge_unknown_slug(self, resolver):
        edge = resolver.get_edge({"slug": "nope"}, "references")
        assert edge is None


class TestGetNeighbors:
    """Convenience neighbor queries."""

    def test_all_neighbors(self, resolver):
        refs = resolver.get_neighbors("keri-runtime-singleton")
        assert len(refs) == 3

    def test_filtered_neighbors(self, resolver):
        refs = resolver.get_neighbors("keri-runtime-singleton", "references")
        assert len(refs) == 1
        assert refs[0].target_said == "habery"

    def test_no_neighbors(self, resolver):
        refs = resolver.get_neighbors("nonexistent")
        assert refs == []


class TestGetStats:
    """Graph statistics."""

    def test_stats(self, resolver):
        stats = resolver.get_stats()
        assert stats["total_nodes"] == 2  # habery, keri-runtime-singleton
        assert stats["total_edges"] == 4
        assert stats["edge_types"]["references"] == 2
        assert stats["edge_types"]["composable_with"] == 1
        assert stats["edge_types"]["conflicts_with"] == 1


class TestRegistryIntegration:
    """Integration with EdgeResolverRegistry."""

    def test_register_in_registry(self, resolver):
        registry = EdgeResolverRegistry()
        registry.register(resolver)
        assert "pattern-space" in registry

    def test_resolve_through_registry(self, resolver):
        registry = EdgeResolverRegistry()
        registry.register(resolver)
        edge = registry.resolve_edge(
            {"slug": "keri-runtime-singleton"},
            "references:habery",
            protocol_hint="pattern-space",
        )
        assert edge is not None
        assert edge.target_said == "habery"

    def test_default_registry_includes_pattern_space(self):
        registry = create_default_registry()
        assert "pattern-space" in registry
        assert "keri" in registry


class TestEmptyResolver:
    """Resolver with no edges."""

    def test_empty_resolver(self):
        resolver = PatternSpaceEdgeResolver(
            edges_path=None,
            load_registries=False,
        )
        assert resolver.list_edges({"slug": "anything"}) == []
        assert resolver.get_edge({"slug": "anything"}, "references") is None
        stats = resolver.get_stats()
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0
