# -*- encoding: utf-8 -*-
"""
Tests for KGQL RDF/Turtle exporter.

Tests export_rdf() and export_rdf_ntriples() for generating
valid RDF triples.
"""

import pytest

from kgql.export.graph import (
    PropertyGraph,
    GraphNode,
    GraphEdge,
    NodeType,
)
from kgql.export.rdf import (
    export_rdf,
    export_rdf_ntriples,
    KERI_NS,
    SAID_URN,
    AID_URN,
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
    ))
    return g


class TestExportRdf:
    """Tests for export_rdf()."""

    def test_export_contains_prefixes(self, sample_graph):
        """Test that output contains prefix declarations."""
        turtle = export_rdf(sample_graph)
        assert "@prefix keri:" in turtle
        assert "@prefix acdc:" in turtle
        assert "@prefix xsd:" in turtle
        assert "@prefix rdf:" in turtle
        assert "@prefix rdfs:" in turtle

    def test_export_without_prefixes(self, sample_graph):
        """Test export without prefix block."""
        turtle = export_rdf(sample_graph, include_prefixes=False)
        assert "@prefix" not in turtle

    def test_export_contains_types(self, sample_graph):
        """Test that nodes have rdf:type declarations."""
        turtle = export_rdf(sample_graph)
        assert "a keri:Credential" in turtle
        assert "a keri:Identifier" in turtle

    def test_export_uses_urn_said(self, sample_graph):
        """Test that SAIDs use urn:said: scheme."""
        turtle = export_rdf(sample_graph)
        assert "<urn:said:ESAID1>" in turtle

    def test_export_uses_urn_aid(self, sample_graph):
        """Test that AIDs use urn:aid: scheme."""
        turtle = export_rdf(sample_graph)
        assert "<urn:aid:EAID1>" in turtle

    def test_export_issuer_property(self, sample_graph):
        """Test that issuer property is included."""
        turtle = export_rdf(sample_graph)
        assert "keri:issuer" in turtle

    def test_export_schema_property(self, sample_graph):
        """Test that schema property is included."""
        turtle = export_rdf(sample_graph)
        assert "keri:schema" in turtle

    def test_export_label(self, sample_graph):
        """Test that rdfs:label is used."""
        turtle = export_rdf(sample_graph)
        assert 'rdfs:label "Test Credential"' in turtle

    def test_export_datetime(self, sample_graph):
        """Test that datetime values are typed."""
        turtle = export_rdf(sample_graph)
        assert "^^xsd:dateTime" in turtle
        assert '"2026-01-28T00:00:00Z"' in turtle


class TestExportRdfEdges:
    """Tests for edge export in RDF."""

    def test_export_edge_predicate(self, sample_graph):
        """Test that edges become predicates."""
        turtle = export_rdf(sample_graph)
        assert "keri:acdc" in turtle

    def test_export_edge_operator(self, sample_graph):
        """Test that edge operators are exported."""
        turtle = export_rdf(sample_graph)
        assert "keri:acdcOperator" in turtle
        assert '"I2I"' in turtle


class TestExportRdfNtriples:
    """Tests for export_rdf_ntriples()."""

    def test_export_ntriples_format(self, sample_graph):
        """Test N-Triples format (full URIs, no prefixes)."""
        ntriples = export_rdf_ntriples(sample_graph)
        # N-Triples uses full URIs
        assert f"<{KERI_NS}" in ntriples
        # No prefix declarations
        assert "@prefix" not in ntriples

    def test_export_ntriples_one_per_line(self, sample_graph):
        """Test that each triple is on its own line."""
        ntriples = export_rdf_ntriples(sample_graph)
        lines = [l for l in ntriples.split("\n") if l.strip()]
        # Each line should end with .
        for line in lines:
            assert line.strip().endswith("."), f"Line doesn't end with period: {line}"

    def test_export_ntriples_type(self, sample_graph):
        """Test rdf:type in N-Triples."""
        ntriples = export_rdf_ntriples(sample_graph)
        assert "rdf-syntax-ns#type>" in ntriples


class TestRdfValidity:
    """Tests for RDF syntax validity."""

    def test_turtle_subjects_have_predicates(self, sample_graph):
        """Test that subjects have at least one predicate."""
        turtle = export_rdf(sample_graph)
        # Each subject block should have 'a' (type)
        assert turtle.count(" a ") >= 3  # At least 3 nodes with types

    def test_turtle_statements_end_properly(self, sample_graph):
        """Test that statements end with ; or ."""
        turtle = export_rdf(sample_graph)
        lines = [l.strip() for l in turtle.split("\n")
                 if l.strip() and not l.strip().startswith("@") and not l.strip().startswith("#")]

        for line in lines:
            if line:
                assert line.endswith(";") or line.endswith("."), f"Invalid ending: {line}"


class TestRdfNamespaces:
    """Tests for RDF namespace constants."""

    def test_keri_namespace(self):
        """Test KERI namespace is well-formed."""
        assert KERI_NS.startswith("https://")
        assert KERI_NS.endswith("#")

    def test_said_urn(self):
        """Test SAID URN scheme."""
        assert SAID_URN == "urn:said:"

    def test_aid_urn(self):
        """Test AID URN scheme."""
        assert AID_URN == "urn:aid:"


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_graph(self):
        """Test exporting empty graph."""
        g = PropertyGraph()
        turtle = export_rdf(g)
        # Should only have prefixes
        assert "@prefix" in turtle
        # No subjects
        assert "<urn:said:" not in turtle

    def test_unsupported_format(self):
        """Test that unsupported format raises error."""
        g = PropertyGraph()
        with pytest.raises(ValueError, match="Unsupported RDF format"):
            export_rdf(g, format="n3")

    def test_node_with_special_chars_in_label(self):
        """Test node with special characters in label."""
        g = PropertyGraph()
        g.add_node(GraphNode(
            said="ESAID",
            node_type=NodeType.CREDENTIAL,
            label='Test "quoted" label',
        ))
        turtle = export_rdf(g)
        # Quotes should be escaped
        assert '\\"' in turtle

    def test_sanitize_predicate(self):
        """Test that edge types are sanitized for RDF predicates."""
        g = PropertyGraph()
        g.add_node(GraphNode(said="ESAID1", node_type=NodeType.CREDENTIAL))
        g.add_node(GraphNode(said="ESAID2", node_type=NodeType.CREDENTIAL))
        g.add_edge(GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="my-edge:type",  # Contains invalid chars
        ))
        turtle = export_rdf(g)
        # Should be sanitized
        assert "keri:my_edge_type" in turtle
