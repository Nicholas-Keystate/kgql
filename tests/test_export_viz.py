# -*- encoding: utf-8 -*-
"""
Tests for KGQL Mermaid visualization exporter.

Tests export_mermaid(), export_mermaid_subgraph(), and related
functions for generating valid Mermaid diagrams.
"""

import pytest

from kgql.export.graph import (
    PropertyGraph,
    GraphNode,
    GraphEdge,
    NodeType,
)
from kgql.export.visualization import (
    export_mermaid,
    export_mermaid_subgraph,
    _said_short,
    _mermaid_escape_label,
)


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    g = PropertyGraph()
    g.add_node(GraphNode(
        said="ESAID1",
        node_type=NodeType.CREDENTIAL,
        issuer="EAID1",
        label="Root Credential",
    ))
    g.add_node(GraphNode(
        said="ESAID2",
        node_type=NodeType.CREDENTIAL,
        issuer="EAID2",
        label="Child Credential",
    ))
    g.add_node(GraphNode(
        said="EAID1",
        node_type=NodeType.IDENTIFIER,
        label="Master AID",
    ))
    g.add_node(GraphNode(
        said="ESCHEMA1",
        node_type=NodeType.SCHEMA,
        label="vLEI Schema",
    ))
    g.add_edge(GraphEdge(
        source_said="ESAID1",
        target_said="ESAID2",
        edge_type="acdc",
        operator="I2I",
    ))
    return g


class TestExportMermaid:
    """Tests for export_mermaid()."""

    def test_export_starts_with_flowchart(self, sample_graph):
        """Test that output starts with flowchart declaration."""
        diagram = export_mermaid(sample_graph)
        assert diagram.startswith("flowchart")

    def test_export_default_direction(self, sample_graph):
        """Test default direction is LR."""
        diagram = export_mermaid(sample_graph)
        assert diagram.startswith("flowchart LR")

    def test_export_custom_direction(self, sample_graph):
        """Test custom direction."""
        diagram = export_mermaid(sample_graph, direction="TD")
        assert diagram.startswith("flowchart TD")

    def test_export_contains_nodes(self, sample_graph):
        """Test that nodes are defined."""
        diagram = export_mermaid(sample_graph)
        assert "n0" in diagram
        assert "n1" in diagram
        assert "n2" in diagram

    def test_export_contains_edges(self, sample_graph):
        """Test that edges are defined with arrow syntax."""
        diagram = export_mermaid(sample_graph)
        assert "-->" in diagram

    def test_export_edge_labels(self, sample_graph):
        """Test that edges have labels with type and operator."""
        diagram = export_mermaid(sample_graph)
        assert "acdc @I2I" in diagram

    def test_export_without_operators(self, sample_graph):
        """Test export without operators in edge labels."""
        diagram = export_mermaid(sample_graph, show_operators=False)
        # Should have type but not operator
        assert "acdc" in diagram
        # @I2I should not appear
        assert "@I2I" not in diagram

    def test_export_with_colors(self, sample_graph):
        """Test that colorize adds style statements."""
        diagram = export_mermaid(sample_graph, colorize=True)
        assert "style n" in diagram
        assert "fill:" in diagram

    def test_export_without_colors(self, sample_graph):
        """Test export without colors."""
        diagram = export_mermaid(sample_graph, colorize=False)
        assert "style" not in diagram

    def test_export_node_shapes(self, sample_graph):
        """Test that different node types have different shapes."""
        diagram = export_mermaid(sample_graph)
        # Credentials use stadium shape: ( )
        # Identifiers use rounded rectangle: ([ ])
        # Schemas use hexagon: {{ }}
        assert '("' in diagram  # Credential
        assert '(["' in diagram  # Identifier
        assert '{{"' in diagram  # Schema


class TestExportMermaidSubgraph:
    """Tests for export_mermaid_subgraph()."""

    def test_subgraph_contains_wrapper(self, sample_graph):
        """Test that subgraph wrapper is present."""
        diagram = export_mermaid_subgraph(sample_graph, subgraph_name="Test")
        assert "subgraph" in diagram
        assert "end" in diagram

    def test_subgraph_name_present(self, sample_graph):
        """Test that subgraph name is used."""
        diagram = export_mermaid_subgraph(sample_graph, subgraph_name="My Graph")
        assert "My Graph" in diagram

    def test_subgraph_direction(self, sample_graph):
        """Test subgraph respects direction."""
        diagram = export_mermaid_subgraph(sample_graph, direction="TD")
        assert "flowchart TD" in diagram


class TestSaidShort:
    """Tests for _said_short() helper."""

    def test_short_said_unchanged(self):
        """Test that short SAIDs are unchanged."""
        assert _said_short("ESAID1") == "ESAID1"

    def test_long_said_truncated(self):
        """Test that long SAIDs are truncated."""
        long_said = "ESAID1234567890ABCDEF"
        result = _said_short(long_said, length=12)
        assert len(result) == 15  # 12 + "..."
        assert result.endswith("...")

    def test_custom_length(self):
        """Test custom truncation length."""
        said = "ESAID123456"
        result = _said_short(said, length=5)
        assert result == "ESAID..."


class TestMermaidEscapeLabel:
    """Tests for _mermaid_escape_label() helper."""

    def test_escape_double_quotes(self):
        """Test escaping double quotes."""
        assert "&quot;" in _mermaid_escape_label('Test "quoted"')

    def test_preserve_br_tags(self):
        """Test that <br/> is preserved."""
        result = _mermaid_escape_label("Line1<br/>Line2")
        assert "<br/>" in result

    def test_escape_angle_brackets(self):
        """Test escaping angle brackets (not <br/>)."""
        result = _mermaid_escape_label("<test>")
        assert "&lt;" in result
        assert "&gt;" in result

    def test_br_not_escaped(self):
        """Test that <br/> is not escaped."""
        result = _mermaid_escape_label("test<br/>more")
        # <br/> should remain as-is
        assert "<br/>" in result
        # No &lt; or &gt; within the br tag
        assert "&lt;br/" not in result


class TestMermaidValidity:
    """Tests for Mermaid syntax validity."""

    def test_valid_node_syntax(self, sample_graph):
        """Test that node definitions use valid syntax."""
        diagram = export_mermaid(sample_graph)
        # Filter for node definitions only (contain [ or ( or { right after variable name)
        lines = [l.strip() for l in diagram.split("\n")
                 if l.strip().startswith("n") and "-->" not in l and "style" not in l]

        for line in lines:
            # Node definitions should be: nX[...] or nX(...)
            assert "[" in line or "(" in line or "{" in line, f"Invalid node: {line}"

    def test_valid_edge_syntax(self, sample_graph):
        """Test that edge definitions use valid syntax."""
        diagram = export_mermaid(sample_graph)
        lines = [l.strip() for l in diagram.split("\n") if "-->" in l]

        for line in lines:
            # Edge should be: nX -->|label| nY
            assert "|" in line, f"Edge missing label: {line}"


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_graph(self):
        """Test exporting empty graph."""
        g = PropertyGraph()
        diagram = export_mermaid(g)
        assert diagram.strip() == "flowchart LR"

    def test_node_without_label(self):
        """Test node without custom label uses SAID."""
        g = PropertyGraph()
        g.add_node(GraphNode(
            said="ESAID_VERY_LONG_IDENTIFIER",
            node_type=NodeType.CREDENTIAL,
        ))
        diagram = export_mermaid(g)
        # Should use truncated SAID
        assert "ESAID_VERY_L..." in diagram

    def test_long_label_truncated(self):
        """Test that long labels are truncated."""
        g = PropertyGraph()
        g.add_node(GraphNode(
            said="ESAID",
            node_type=NodeType.CREDENTIAL,
            label="This is a very long label that should be truncated",
        ))
        diagram = export_mermaid(g, max_label_length=20)
        assert "..." in diagram

    def test_operator_any_hidden(self):
        """Test that ANY operator is not shown."""
        g = PropertyGraph()
        g.add_node(GraphNode(said="ESAID1", node_type=NodeType.CREDENTIAL))
        g.add_node(GraphNode(said="ESAID2", node_type=NodeType.CREDENTIAL))
        g.add_edge(GraphEdge(
            source_said="ESAID1",
            target_said="ESAID2",
            edge_type="iss",
            operator="ANY",
        ))
        diagram = export_mermaid(g)
        # ANY should not appear as @ANY
        assert "@ANY" not in diagram
