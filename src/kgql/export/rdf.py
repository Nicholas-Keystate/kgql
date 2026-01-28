# -*- encoding: utf-8 -*-
"""
KGQL RDF/Turtle Exporter.

Generates RDF triples in Turtle format from PropertyGraph.

Uses KERI-specific ontology namespace for semantic web integration.
No rdflib dependency — generates Turtle text directly.

Output can be:
- Loaded into RDF triple stores (Jena, Virtuoso, GraphDB)
- Queried with SPARQL
- Converted to other RDF formats

Example Output:
    @prefix keri: <https://keri.one/ontology#> .
    @prefix acdc: <https://keri.one/acdc#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

    <urn:said:ESAID...> a keri:Credential ;
        keri:issuer <urn:aid:EAID...> ;
        keri:schema <urn:said:ESCHEMA...> ;
        keri:issuedAt "2026-01-28"^^xsd:dateTime .

    <urn:said:ESAID1> keri:acdc <urn:said:ESAID2> .

Usage:
    from kgql.export import PropertyGraph
    from kgql.export.rdf import export_rdf

    turtle = export_rdf(graph)
    print(turtle)  # Valid RDF/Turtle
"""

from typing import Optional

from kgql.export.graph import PropertyGraph, GraphNode, GraphEdge, NodeType


# Ontology namespaces
KERI_NS = "https://keri.one/ontology#"
ACDC_NS = "https://keri.one/acdc#"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"

# URN schemes for KERI identifiers
SAID_URN = "urn:said:"
AID_URN = "urn:aid:"


def export_rdf(
    graph: PropertyGraph,
    format: str = "turtle",
    include_prefixes: bool = True,
) -> str:
    """
    Generate RDF triples in Turtle format from PropertyGraph.

    Creates RDF representation using KERI-specific ontology.

    Args:
        graph: PropertyGraph to export
        format: Output format ("turtle" only for now)
        include_prefixes: Include @prefix declarations (default True)

    Returns:
        String of RDF triples in Turtle format
    """
    if format != "turtle":
        raise ValueError(f"Unsupported RDF format: {format}. Only 'turtle' is supported.")

    lines = []

    if include_prefixes:
        lines.extend(_turtle_prefix_block())
        lines.append("")

    # Generate triples for nodes
    for node in graph.nodes.values():
        node_triples = _node_to_turtle(node)
        lines.extend(node_triples)
        lines.append("")  # Blank line between subjects

    # Generate triples for edges
    if graph.edges:
        lines.append("# Edge relationships")
        for edge in graph.edges:
            edge_triples = _edge_to_turtle(edge)
            lines.extend(edge_triples)

    return "\n".join(lines)


def export_rdf_ntriples(graph: PropertyGraph) -> str:
    """
    Generate RDF in N-Triples format (simpler, line-based).

    N-Triples is easier to parse and stream but more verbose.

    Args:
        graph: PropertyGraph to export

    Returns:
        String of N-Triples
    """
    lines = []

    # Generate triples for nodes
    for node in graph.nodes.values():
        lines.extend(_node_to_ntriples(node))

    # Generate triples for edges
    for edge in graph.edges:
        lines.extend(_edge_to_ntriples(edge))

    return "\n".join(lines)


def _turtle_prefix_block() -> list[str]:
    """
    Generate @prefix declarations for Turtle format.
    """
    return [
        f"@prefix keri: <{KERI_NS}> .",
        f"@prefix acdc: <{ACDC_NS}> .",
        f"@prefix xsd: <{XSD_NS}> .",
        f"@prefix rdf: <{RDF_NS}> .",
        f"@prefix rdfs: <{RDFS_NS}> .",
    ]


def _node_to_turtle(node: GraphNode) -> list[str]:
    """
    Convert GraphNode to Turtle triples.

    Example:
        <urn:said:ESAID...> a keri:Credential ;
            keri:issuer <urn:aid:EAID...> ;
            keri:schema <urn:said:ESCHEMA...> .
    """
    lines = []
    subject = _said_to_uri(node.said)

    # RDF type based on node type
    rdf_type = _node_type_to_rdf_class(node.node_type)
    lines.append(f"{subject} a {rdf_type} ;")

    # Properties
    props = []

    if node.issuer:
        props.append(f'    keri:issuer {_aid_to_uri(node.issuer)}')
    if node.schema:
        props.append(f'    keri:schema {_said_to_uri(node.schema)}')
    if node.label:
        props.append(f'    rdfs:label {_turtle_literal(node.label)}')
    if node.key_state_seq is not None:
        props.append(f'    keri:keyStateSeq {node.key_state_seq}')
    if node.delegation_depth is not None:
        props.append(f'    keri:delegationDepth {node.delegation_depth}')
    if node.issued_at:
        props.append(f'    keri:issuedAt {_turtle_datetime(node.issued_at)}')
    if node.revoked_at:
        props.append(f'    keri:revokedAt {_turtle_datetime(node.revoked_at)}')
    if node.registry:
        props.append(f'    keri:registry {_said_to_uri(node.registry)}')

    # Attributes as custom properties
    if node.attributes:
        for key, value in node.attributes:
            safe_key = _sanitize_predicate(key)
            props.append(f'    acdc:{safe_key} {_turtle_value(value)}')

    # Join properties with semicolons, end with period
    if props:
        for i, prop in enumerate(props):
            if i < len(props) - 1:
                lines.append(f"{prop} ;")
            else:
                lines.append(f"{prop} .")
    else:
        # No properties, just close the type statement
        lines[-1] = lines[-1].replace(" ;", " .")

    return lines


def _edge_to_turtle(edge: GraphEdge) -> list[str]:
    """
    Convert GraphEdge to Turtle triples.

    Example:
        <urn:said:ESAID1> keri:acdc <urn:said:ESAID2> .
        <urn:said:ESAID1> keri:edgeOperator "I2I" .
    """
    lines = []
    subject = _said_to_uri(edge.source_said)
    obj = _said_to_uri(edge.target_said)

    # Edge type as predicate
    predicate = f"keri:{_sanitize_predicate(edge.edge_type)}"
    lines.append(f"{subject} {predicate} {obj} .")

    # Operator as reified property (if not ANY)
    if edge.operator != "ANY":
        lines.append(
            f"{subject} keri:{_sanitize_predicate(edge.edge_type)}Operator "
            f'{_turtle_literal(edge.operator)} .'
        )

    # Weight if present
    if edge.weight is not None:
        lines.append(
            f"{subject} keri:{_sanitize_predicate(edge.edge_type)}Weight "
            f"{edge.weight} ."
        )

    return lines


def _node_to_ntriples(node: GraphNode) -> list[str]:
    """
    Convert GraphNode to N-Triples format.
    """
    lines = []
    subject = _said_to_uri_full(node.said)
    rdf_type = _node_type_to_rdf_class_full(node.node_type)

    lines.append(f'{subject} <{RDF_NS}type> {rdf_type} .')

    if node.issuer:
        lines.append(f'{subject} <{KERI_NS}issuer> {_aid_to_uri_full(node.issuer)} .')
    if node.schema:
        lines.append(f'{subject} <{KERI_NS}schema> {_said_to_uri_full(node.schema)} .')
    if node.label:
        lines.append(f'{subject} <{RDFS_NS}label> {_ntriples_literal(node.label)} .')

    return lines


def _edge_to_ntriples(edge: GraphEdge) -> list[str]:
    """
    Convert GraphEdge to N-Triples format.
    """
    subject = _said_to_uri_full(edge.source_said)
    obj = _said_to_uri_full(edge.target_said)
    predicate = f"<{KERI_NS}{_sanitize_predicate(edge.edge_type)}>"

    return [f"{subject} {predicate} {obj} ."]


def _said_to_uri(said: str) -> str:
    """Convert SAID to Turtle-prefixed URI."""
    return f"<{SAID_URN}{said}>"


def _said_to_uri_full(said: str) -> str:
    """Convert SAID to full URI for N-Triples."""
    return f"<{SAID_URN}{said}>"


def _aid_to_uri(aid: str) -> str:
    """Convert AID to Turtle-prefixed URI."""
    return f"<{AID_URN}{aid}>"


def _aid_to_uri_full(aid: str) -> str:
    """Convert AID to full URI for N-Triples."""
    return f"<{AID_URN}{aid}>"


def _node_type_to_rdf_class(node_type: NodeType) -> str:
    """Map NodeType to RDF class (prefixed form)."""
    class_map = {
        NodeType.CREDENTIAL: "keri:Credential",
        NodeType.IDENTIFIER: "keri:Identifier",
        NodeType.SCHEMA: "keri:Schema",
        NodeType.FRAMEWORK: "keri:GovernanceFramework",
    }
    return class_map.get(node_type, "keri:Node")


def _node_type_to_rdf_class_full(node_type: NodeType) -> str:
    """Map NodeType to full RDF class URI."""
    class_map = {
        NodeType.CREDENTIAL: f"<{KERI_NS}Credential>",
        NodeType.IDENTIFIER: f"<{KERI_NS}Identifier>",
        NodeType.SCHEMA: f"<{KERI_NS}Schema>",
        NodeType.FRAMEWORK: f"<{KERI_NS}GovernanceFramework>",
    }
    return class_map.get(node_type, f"<{KERI_NS}Node>")


def _turtle_literal(value: str) -> str:
    """Format string as Turtle literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _ntriples_literal(value: str) -> str:
    """Format string as N-Triples literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _turtle_datetime(value: str) -> str:
    """Format datetime as typed Turtle literal."""
    return f'"{value}"^^xsd:dateTime'


def _turtle_value(value) -> str:
    """Format arbitrary value as Turtle literal."""
    if isinstance(value, str):
        return _turtle_literal(value)
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        return _turtle_literal(str(value))


def _sanitize_predicate(name: str) -> str:
    """
    Sanitize string for use as RDF predicate local name.

    Removes/replaces characters invalid in Turtle local names.
    """
    # Replace common problematic characters
    result = ""
    for c in name:
        if c.isalnum() or c == "_":
            result += c
        elif c in "-:":
            result += "_"
        # Skip other characters

    # Ensure doesn't start with digit
    if result and result[0].isdigit():
        result = "_" + result

    return result or "unknown"
