# -*- encoding: utf-8 -*-
"""
KGQL Export Module - Graph export to external formats.

Provides formatters for exporting KGQL query results to:
- Neo4j Cypher (for graph database import)
- JSON Property Graph (generic format)
- RDF/Turtle (semantic web)
- Mermaid (visualization)

All formatters consume PropertyGraph as the common intermediate representation.

Usage:
    from kgql.export import PropertyGraph, export_neo4j, export_mermaid

    # Build graph from query result
    graph = PropertyGraph.from_query_result(result)

    # Export to Neo4j
    cypher = export_neo4j(graph)

    # Export to Mermaid
    diagram = export_mermaid(graph)
"""

from kgql.export.graph import (
    PropertyGraph,
    GraphNode,
    GraphEdge,
    NodeType,
    EdgeKind,
)

from kgql.export.neo4j import export_neo4j, export_neo4j_merge
from kgql.export.property_graph import (
    export_property_graph,
    export_property_graph_json,
    load_property_graph_json,
)
from kgql.export.rdf import export_rdf, export_rdf_ntriples
from kgql.export.visualization import (
    export_mermaid,
    export_mermaid_subgraph,
    export_mermaid_sequence,
)

# Export format constants
FORMAT_PROPERTY_GRAPH = "property_graph"
FORMAT_NEO4J = "neo4j"
FORMAT_RDF = "rdf"
FORMAT_MERMAID = "mermaid"

__all__ = [
    # Core types
    "PropertyGraph",
    "GraphNode",
    "GraphEdge",
    "NodeType",
    "EdgeKind",
    # Formatters
    "export_neo4j",
    "export_neo4j_merge",
    "export_property_graph",
    "export_property_graph_json",
    "load_property_graph_json",
    "export_rdf",
    "export_rdf_ntriples",
    "export_mermaid",
    "export_mermaid_subgraph",
    "export_mermaid_sequence",
    # Format constants
    "FORMAT_PROPERTY_GRAPH",
    "FORMAT_NEO4J",
    "FORMAT_RDF",
    "FORMAT_MERMAID",
]
