# -*- encoding: utf-8 -*-
"""
KGQL Property Graph JSON Exporter.

Exports PropertyGraph to a generic JSON property graph format
suitable for import into various graph databases and tools.

Output Format:
    {
        "nodes": [
            {"id": "ESAID...", "type": "credential", "properties": {...}},
            ...
        ],
        "edges": [
            {"source": "ESAID1", "target": "ESAID2", "type": "acdc", "properties": {...}},
            ...
        ],
        "metadata": {...}
    }

This format is compatible with:
- NetworkX (via node_link_data/node_link_graph)
- D3.js force layouts
- Gephi (with transformation)
- Custom analytics pipelines
"""

import json
from typing import Optional

from kgql.export.graph import PropertyGraph, GraphNode, GraphEdge


def export_property_graph(graph: PropertyGraph) -> dict:
    """
    Export PropertyGraph as JSON-serializable property graph dict.

    Format follows the common property graph JSON convention with
    nodes, edges, and metadata sections.

    Args:
        graph: PropertyGraph to export

    Returns:
        Dictionary suitable for JSON serialization:
        {
            "nodes": [{"id": ..., "type": ..., "properties": {...}}, ...],
            "edges": [{"source": ..., "target": ..., "type": ..., "properties": {...}}, ...],
            "metadata": {...}
        }
    """
    return {
        "nodes": [_node_to_property_graph(node) for node in graph.nodes.values()],
        "edges": [_edge_to_property_graph(edge) for edge in graph.edges],
        "metadata": graph.metadata,
    }


def export_property_graph_json(
    graph: PropertyGraph,
    indent: Optional[int] = 2,
    sort_keys: bool = True,
) -> str:
    """
    Export PropertyGraph as JSON string.

    Convenience function that wraps export_property_graph() with
    JSON serialization.

    Args:
        graph: PropertyGraph to export
        indent: JSON indentation (default 2, None for compact)
        sort_keys: Sort dictionary keys (default True for determinism)

    Returns:
        JSON string representation
    """
    data = export_property_graph(graph)
    return json.dumps(data, indent=indent, sort_keys=sort_keys)


def _node_to_property_graph(node: GraphNode) -> dict:
    """
    Convert GraphNode to property graph node dict.

    Format:
        {
            "id": "<said>",
            "type": "<node_type>",
            "properties": {
                "issuer": "...",
                "schema": "...",
                ...
            }
        }
    """
    properties = {}

    if node.issuer:
        properties["issuer"] = node.issuer
    if node.schema:
        properties["schema"] = node.schema
    if node.attributes:
        properties["attributes"] = dict(node.attributes)
    if node.label:
        properties["label"] = node.label
    if node.key_state_seq is not None:
        properties["key_state_seq"] = node.key_state_seq
    if node.delegation_depth is not None:
        properties["delegation_depth"] = node.delegation_depth
    if node.issued_at:
        properties["issued_at"] = node.issued_at
    if node.revoked_at:
        properties["revoked_at"] = node.revoked_at
    if node.registry:
        properties["registry"] = node.registry

    return {
        "id": node.said,
        "type": node.node_type.value,
        "properties": properties,
    }


def _edge_to_property_graph(edge: GraphEdge) -> dict:
    """
    Convert GraphEdge to property graph edge dict.

    Format:
        {
            "source": "<source_said>",
            "target": "<target_said>",
            "type": "<edge_type>",
            "properties": {
                "operator": "I2I",
                ...
            }
        }
    """
    properties = {
        "operator": edge.operator,
    }

    if edge.weight is not None:
        properties["weight"] = edge.weight
    if edge.metadata:
        properties["metadata"] = dict(edge.metadata)

    return {
        "source": edge.source_said,
        "target": edge.target_said,
        "type": edge.edge_type,
        "properties": properties,
    }


def load_property_graph_json(json_str: str) -> PropertyGraph:
    """
    Load PropertyGraph from JSON string.

    Inverse of export_property_graph_json(). Useful for round-trip
    testing and loading previously exported graphs.

    Args:
        json_str: JSON string in property graph format

    Returns:
        PropertyGraph instance
    """
    from kgql.export.graph import NodeType

    data = json.loads(json_str)
    graph = PropertyGraph()

    # Load metadata
    if "metadata" in data:
        graph.metadata = data["metadata"]

    # Load nodes
    for node_dict in data.get("nodes", []):
        props = node_dict.get("properties", {})

        # Convert attributes back to tuple
        attrs = props.get("attributes", {})
        attrs_tuple = tuple(attrs.items()) if isinstance(attrs, dict) else ()

        node = GraphNode(
            said=node_dict["id"],
            node_type=NodeType(node_dict["type"]),
            issuer=props.get("issuer", ""),
            schema=props.get("schema", ""),
            attributes=attrs_tuple,
            label=props.get("label", ""),
            key_state_seq=props.get("key_state_seq"),
            delegation_depth=props.get("delegation_depth"),
            issued_at=props.get("issued_at"),
            revoked_at=props.get("revoked_at"),
            registry=props.get("registry"),
        )
        graph.add_node(node)

    # Load edges
    for edge_dict in data.get("edges", []):
        props = edge_dict.get("properties", {})

        # Convert metadata back to tuple
        meta = props.get("metadata", {})
        meta_tuple = tuple(meta.items()) if isinstance(meta, dict) else ()

        edge = GraphEdge(
            source_said=edge_dict["source"],
            target_said=edge_dict["target"],
            edge_type=edge_dict["type"],
            operator=props.get("operator", "ANY"),
            weight=props.get("weight"),
            metadata=meta_tuple,
        )
        graph.add_edge(edge)

    return graph
