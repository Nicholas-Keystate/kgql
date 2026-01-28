# -*- encoding: utf-8 -*-
"""
Tests for KGQL PropertyGraph intermediate representation.

Tests PropertyGraph construction, node/edge management, and
factory methods for building graphs from various sources.
"""

import pytest

from kgql.export.graph import (
    PropertyGraph,
    GraphNode,
    GraphEdge,
    NodeType,
    EdgeKind,
)


@pytest.fixture
def sample_graph():
    """Create a 3-node credential chain with edges for testing."""
    g = PropertyGraph()
    g.add_node(GraphNode(
        said="ESAID1",
        node_type=NodeType.CREDENTIAL,
        issuer="EAID1",
        schema="ESCHEMA1",
        label="Root Credential",
    ))
    g.add_node(GraphNode(
        said="ESAID2",
        node_type=NodeType.CREDENTIAL,
        issuer="EAID2",
        schema="ESCHEMA1",
    ))
    g.add_node(GraphNode(
        said="ESAID3",
        node_type=NodeType.CREDENTIAL,
        issuer="EAID1",
        schema="ESCHEMA2",
    ))
    g.add_edge(GraphEdge(
        source_said="ESAID1",
        target_said="ESAID2",
        edge_type="acdc",
        operator="I2I",
    ))
    g.add_edge(GraphEdge(
        source_said="ESAID2",
        target_said="ESAID3",
        edge_type="delegator",
        operator="DI2I",
    ))
    return g


class TestGraphNode:
    """Tests for GraphNode dataclass."""

    def test_create_node_minimal(self):
        """Test creating a node with minimal fields."""
        node = GraphNode(said="ESAID", node_type=NodeType.CREDENTIAL)
        assert node.said == "ESAID"
        assert node.node_type == NodeType.CREDENTIAL
        assert node.issuer == ""
        assert node.schema == ""

    def test_create_node_full(self):
        """Test creating a node with all fields."""
        node = GraphNode(
            said="ESAID",
            node_type=NodeType.CREDENTIAL,
            issuer="EAID",
            schema="ESCHEMA",
            attributes=(("lei", "549300EXAMPLE"),),
            label="Test Credential",
            key_state_seq=5,
            delegation_depth=2,
            issued_at="2026-01-28T00:00:00Z",
            revoked_at=None,
            registry="EREGISTRY",
        )
        assert node.issued_at == "2026-01-28T00:00:00Z"
        assert node.key_state_seq == 5
        assert dict(node.attributes)["lei"] == "549300EXAMPLE"

    def test_node_is_frozen(self):
        """Test that GraphNode is immutable."""
        node = GraphNode(said="ESAID", node_type=NodeType.CREDENTIAL)
        with pytest.raises(AttributeError):
            node.said = "CHANGED"

    def test_node_to_dict(self):
        """Test node serialization to dict."""
        node = GraphNode(
            said="ESAID",
            node_type=NodeType.CREDENTIAL,
            issuer="EAID",
        )
        d = node.to_dict()
        assert d["said"] == "ESAID"
        assert d["type"] == "credential"
        assert d["issuer"] == "EAID"


class TestGraphEdge:
    """Tests for GraphEdge dataclass."""

    def test_create_edge_minimal(self):
        """Test creating an edge with minimal fields."""
        edge = GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="acdc",
        )
        assert edge.source_said == "ESAID1"
        assert edge.target_said == "ESAID2"
        assert edge.edge_type == "acdc"
        assert edge.operator == "ANY"

    def test_create_edge_full(self):
        """Test creating an edge with all fields."""
        edge = GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="acdc",
            operator="I2I",
            weight=0.95,
            metadata=(("verified", True),),
        )
        assert edge.operator == "I2I"
        assert edge.weight == 0.95
        assert dict(edge.metadata)["verified"] is True

    def test_edge_is_frozen(self):
        """Test that GraphEdge is immutable."""
        edge = GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="acdc",
        )
        with pytest.raises(AttributeError):
            edge.edge_type = "CHANGED"

    def test_edge_to_dict(self):
        """Test edge serialization to dict."""
        edge = GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="acdc",
            operator="I2I",
        )
        d = edge.to_dict()
        assert d["source"] == "ESAID1"
        assert d["target"] == "ESAID2"
        assert d["type"] == "acdc"
        assert d["operator"] == "I2I"


class TestPropertyGraph:
    """Tests for PropertyGraph class."""

    def test_empty_graph(self):
        """Test creating an empty graph."""
        g = PropertyGraph()
        assert g.node_count() == 0
        assert g.edge_count() == 0

    def test_add_node(self):
        """Test adding nodes."""
        g = PropertyGraph()
        node = GraphNode(said="ESAID", node_type=NodeType.CREDENTIAL)
        g.add_node(node)
        assert g.node_count() == 1
        assert g.has_node("ESAID")
        assert g.get_node("ESAID") == node

    def test_add_duplicate_node_replaces(self):
        """Test that adding a node with same SAID replaces existing."""
        g = PropertyGraph()
        node1 = GraphNode(said="ESAID", node_type=NodeType.CREDENTIAL, label="v1")
        node2 = GraphNode(said="ESAID", node_type=NodeType.CREDENTIAL, label="v2")
        g.add_node(node1)
        g.add_node(node2)
        assert g.node_count() == 1
        assert g.get_node("ESAID").label == "v2"

    def test_add_edge(self):
        """Test adding edges."""
        g = PropertyGraph()
        edge = GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="acdc",
        )
        g.add_edge(edge)
        assert g.edge_count() == 1

    def test_add_duplicate_edges_allowed(self):
        """Test that duplicate edges are allowed (multi-graph)."""
        g = PropertyGraph()
        edge = GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="acdc",
        )
        g.add_edge(edge)
        g.add_edge(edge)
        assert g.edge_count() == 2

    def test_get_edges_from(self, sample_graph):
        """Test getting edges originating from a node."""
        edges = sample_graph.get_edges_from("ESAID1")
        assert len(edges) == 1
        assert edges[0].target_said == "ESAID2"

    def test_get_edges_to(self, sample_graph):
        """Test getting edges pointing to a node."""
        edges = sample_graph.get_edges_to("ESAID3")
        assert len(edges) == 1
        assert edges[0].source_said == "ESAID2"

    def test_to_dict(self, sample_graph):
        """Test full graph serialization."""
        d = sample_graph.to_dict()
        assert len(d["nodes"]) == 3
        assert len(d["edges"]) == 2
        assert d["stats"]["node_count"] == 3
        assert d["stats"]["edge_count"] == 2


class TestPropertyGraphFromCredentials:
    """Tests for PropertyGraph.from_credentials() factory method."""

    def test_from_credentials_basic(self):
        """Test building graph from credential dicts."""
        credentials = [
            {
                "d": "ESAID1",
                "i": "EAID1",
                "s": "ESCHEMA1",
                "a": {"lei": "549300EXAMPLE"},
            },
            {
                "d": "ESAID2",
                "i": "EAID2",
                "s": "ESCHEMA1",
                "a": {},
            },
        ]
        graph = PropertyGraph.from_credentials(credentials)
        assert graph.node_count() == 2
        assert graph.has_node("ESAID1")
        assert graph.has_node("ESAID2")

    def test_from_credentials_with_edges(self):
        """Test building graph from credentials with edge sections."""
        credentials = [
            {
                "d": "ESAID1",
                "i": "EAID1",
                "s": "ESCHEMA1",
                "a": {},
                "e": {
                    "acdc": {
                        "d": "ESAID2",
                    },
                },
            },
        ]
        graph = PropertyGraph.from_credentials(credentials)
        # Should have 2 nodes: ESAID1 and implicit ESAID2 from edge
        assert graph.node_count() == 2
        assert graph.edge_count() == 1
        assert graph.has_node("ESAID2")


class TestNodeType:
    """Tests for NodeType enum."""

    def test_node_types_are_strings(self):
        """Test that NodeType values are strings."""
        assert NodeType.CREDENTIAL.value == "credential"
        assert NodeType.IDENTIFIER.value == "identifier"
        assert NodeType.SCHEMA.value == "schema"
        assert NodeType.FRAMEWORK.value == "framework"


class TestEdgeKind:
    """Tests for EdgeKind enum."""

    def test_edge_kinds_are_strings(self):
        """Test that EdgeKind values are strings."""
        assert EdgeKind.ACDC.value == "acdc"
        assert EdgeKind.ISSUANCE.value == "iss"
        assert EdgeKind.DELEGATION.value == "delegator"
