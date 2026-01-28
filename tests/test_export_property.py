# -*- encoding: utf-8 -*-
"""
Tests for KGQL JSON Property Graph exporter.

Tests export_property_graph(), export_property_graph_json(),
and round-trip loading with load_property_graph_json().
"""

import json
import pytest

from kgql.export.graph import (
    PropertyGraph,
    GraphNode,
    GraphEdge,
    NodeType,
)
from kgql.export.property_graph import (
    export_property_graph,
    export_property_graph_json,
    load_property_graph_json,
)


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    g = PropertyGraph()
    g.add_node(GraphNode(
        said="ESAID1",
        node_type=NodeType.CREDENTIAL,
        issuer="EAID1",
        schema="ESCHEMA1",
        label="Test Credential",
        issued_at="2026-01-28T00:00:00Z",
    ))
    g.add_node(GraphNode(
        said="ESAID2",
        node_type=NodeType.CREDENTIAL,
        issuer="EAID2",
        schema="ESCHEMA1",
    ))
    g.add_node(GraphNode(
        said="EAID1",
        node_type=NodeType.IDENTIFIER,
        label="Master AID",
    ))
    g.add_edge(GraphEdge(
        source_said="ESAID1",
        target_said="ESAID2",
        edge_type="acdc",
        operator="I2I",
        weight=0.95,
    ))
    g.metadata = {"query": "MATCH (c:Credential)"}
    return g


class TestExportPropertyGraph:
    """Tests for export_property_graph()."""

    def test_export_basic(self, sample_graph):
        """Test basic export to dict."""
        result = export_property_graph(sample_graph)
        assert isinstance(result, dict)
        assert "nodes" in result
        assert "edges" in result
        assert "metadata" in result

    def test_export_nodes(self, sample_graph):
        """Test that nodes are exported correctly."""
        result = export_property_graph(sample_graph)
        nodes = result["nodes"]
        assert len(nodes) == 3

        # Find credential node
        cred_nodes = [n for n in nodes if n["type"] == "credential"]
        assert len(cred_nodes) == 2

        # Check node structure
        node = cred_nodes[0]
        assert "id" in node
        assert "type" in node
        assert "properties" in node

    def test_export_edges(self, sample_graph):
        """Test that edges are exported correctly."""
        result = export_property_graph(sample_graph)
        edges = result["edges"]
        assert len(edges) == 1

        edge = edges[0]
        assert edge["source"] == "ESAID1"
        assert edge["target"] == "ESAID2"
        assert edge["type"] == "acdc"
        assert edge["properties"]["operator"] == "I2I"
        assert edge["properties"]["weight"] == 0.95

    def test_export_metadata_preserved(self, sample_graph):
        """Test that metadata is preserved."""
        result = export_property_graph(sample_graph)
        assert result["metadata"] == {"query": "MATCH (c:Credential)"}


class TestExportPropertyGraphJson:
    """Tests for export_property_graph_json()."""

    def test_export_json_string(self, sample_graph):
        """Test export to JSON string."""
        json_str = export_property_graph_json(sample_graph)
        assert isinstance(json_str, str)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "nodes" in parsed

    def test_export_json_indentation(self, sample_graph):
        """Test JSON indentation options."""
        # With indent
        json_indented = export_property_graph_json(sample_graph, indent=2)
        assert "\n" in json_indented

        # Compact (no indent)
        json_compact = export_property_graph_json(sample_graph, indent=None)
        # Compact may still have newlines but fewer
        assert len(json_compact) < len(json_indented)

    def test_export_json_deterministic(self, sample_graph):
        """Test that output is deterministic with sort_keys."""
        json1 = export_property_graph_json(sample_graph, sort_keys=True)
        json2 = export_property_graph_json(sample_graph, sort_keys=True)
        assert json1 == json2


class TestLoadPropertyGraphJson:
    """Tests for load_property_graph_json()."""

    def test_round_trip(self, sample_graph):
        """Test that export -> load preserves graph structure."""
        json_str = export_property_graph_json(sample_graph)
        loaded = load_property_graph_json(json_str)

        assert loaded.node_count() == sample_graph.node_count()
        assert loaded.edge_count() == sample_graph.edge_count()

    def test_round_trip_node_properties(self, sample_graph):
        """Test that node properties survive round-trip."""
        json_str = export_property_graph_json(sample_graph)
        loaded = load_property_graph_json(json_str)

        original_node = sample_graph.get_node("ESAID1")
        loaded_node = loaded.get_node("ESAID1")

        assert loaded_node.said == original_node.said
        assert loaded_node.node_type == original_node.node_type
        assert loaded_node.issuer == original_node.issuer
        assert loaded_node.schema == original_node.schema
        assert loaded_node.label == original_node.label
        assert loaded_node.issued_at == original_node.issued_at

    def test_round_trip_edge_properties(self, sample_graph):
        """Test that edge properties survive round-trip."""
        json_str = export_property_graph_json(sample_graph)
        loaded = load_property_graph_json(json_str)

        original_edge = sample_graph.edges[0]
        loaded_edge = loaded.edges[0]

        assert loaded_edge.source_said == original_edge.source_said
        assert loaded_edge.target_said == original_edge.target_said
        assert loaded_edge.edge_type == original_edge.edge_type
        assert loaded_edge.operator == original_edge.operator
        assert loaded_edge.weight == original_edge.weight

    def test_round_trip_metadata(self, sample_graph):
        """Test that metadata survives round-trip."""
        json_str = export_property_graph_json(sample_graph)
        loaded = load_property_graph_json(json_str)

        assert loaded.metadata == sample_graph.metadata


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_graph(self):
        """Test exporting empty graph."""
        g = PropertyGraph()
        result = export_property_graph(g)
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_node_with_attributes(self):
        """Test node with attributes as tuple."""
        g = PropertyGraph()
        g.add_node(GraphNode(
            said="ESAID",
            node_type=NodeType.CREDENTIAL,
            attributes=(("lei", "549300EXAMPLE"), ("name", "Test Org")),
        ))

        result = export_property_graph(g)
        node = result["nodes"][0]
        attrs = node["properties"]["attributes"]
        assert attrs["lei"] == "549300EXAMPLE"
        assert attrs["name"] == "Test Org"
