# -*- encoding: utf-8 -*-
"""
KGQL Mermaid Visualization Exporter.

Generates Mermaid flowchart diagrams from PropertyGraph.

Output can be:
- Pasted into mermaid.live for immediate rendering
- Embedded in Markdown documentation
- Rendered in GitHub/GitLab READMEs
- Used in presentation slides

Example Output:
    flowchart LR
        n0["Credential<br/>EF1x2Kvx..."]
        n1["Credential<br/>EOEwydo..."]
        n0 -->|"acdc @I2I"| n1
        style n0 fill:#e1f5fe

Usage:
    from kgql.export import PropertyGraph
    from kgql.export.visualization import export_mermaid

    diagram = export_mermaid(graph)
    print(diagram)  # Ready for mermaid.live
"""

from typing import Optional

from kgql.export.graph import PropertyGraph, GraphNode, GraphEdge, NodeType


# Color scheme for node types (Material Design colors)
NODE_COLORS = {
    NodeType.CREDENTIAL: "#e1f5fe",  # Light blue
    NodeType.IDENTIFIER: "#e8f5e9",  # Light green
    NodeType.SCHEMA: "#fff3e0",      # Light orange
    NodeType.FRAMEWORK: "#f3e5f5",   # Light purple
}

# Node shapes by type
NODE_SHAPES = {
    NodeType.CREDENTIAL: ("(", ")"),     # Stadium shape
    NodeType.IDENTIFIER: ("([", "])"),   # Rounded rectangle
    NodeType.SCHEMA: ("{{", "}}"),       # Hexagon
    NodeType.FRAMEWORK: ("[[", "]]"),    # Subroutine box
}


def export_mermaid(
    graph: PropertyGraph,
    direction: str = "LR",
    show_operators: bool = True,
    show_saids: bool = False,
    show_labels: bool = True,
    colorize: bool = True,
    max_label_length: int = 20,
) -> str:
    """
    Generate Mermaid flowchart from PropertyGraph.

    Creates a flowchart diagram suitable for rendering with Mermaid.js.

    Args:
        graph: PropertyGraph to visualize
        direction: Flow direction - "LR" (left-right), "TD" (top-down),
                   "RL" (right-left), "BT" (bottom-top)
        show_operators: Include edge operators (I2I/DI2I/NI2I) on edges
        show_saids: Show full SAIDs (verbose) or truncated
        show_labels: Include node labels in diagram
        colorize: Apply colors based on node type
        max_label_length: Maximum label length before truncation

    Returns:
        Mermaid flowchart diagram as string
    """
    lines = [f"flowchart {direction}"]

    # Build SAID → variable mapping
    said_to_var: dict[str, str] = {}
    for idx, said in enumerate(graph.nodes.keys()):
        said_to_var[said] = f"n{idx}"

    # Generate node definitions
    for said, node in graph.nodes.items():
        var = said_to_var[said]
        node_def = _node_to_mermaid(
            node, var, show_saids, show_labels, max_label_length
        )
        lines.append(f"    {node_def}")

    # Add blank line
    lines.append("")

    # Generate edge definitions
    for edge in graph.edges:
        source_var = said_to_var.get(edge.source_said)
        target_var = said_to_var.get(edge.target_said)

        if source_var and target_var:
            edge_def = _edge_to_mermaid(edge, source_var, target_var, show_operators)
            lines.append(f"    {edge_def}")

    # Add styling if colorize is enabled
    if colorize:
        lines.append("")
        for said, node in graph.nodes.items():
            var = said_to_var[said]
            color = NODE_COLORS.get(node.node_type, "#ffffff")
            lines.append(f"    style {var} fill:{color}")

    return "\n".join(lines)


def export_mermaid_subgraph(
    graph: PropertyGraph,
    subgraph_name: str = "Credential Graph",
    direction: str = "LR",
    show_operators: bool = True,
    show_saids: bool = False,
) -> str:
    """
    Generate Mermaid flowchart with subgraph wrapper.

    Useful for embedding in larger diagrams.

    Args:
        graph: PropertyGraph to visualize
        subgraph_name: Name/title for the subgraph
        direction: Flow direction
        show_operators: Include edge operators on edges
        show_saids: Show full SAIDs or truncated

    Returns:
        Mermaid flowchart with subgraph wrapper
    """
    inner = export_mermaid(
        graph,
        direction=direction,
        show_operators=show_operators,
        show_saids=show_saids,
        colorize=False,  # Handle styling at outer level
    )

    # Wrap in subgraph
    inner_lines = inner.split("\n")
    # Remove the "flowchart LR" line
    if inner_lines and inner_lines[0].startswith("flowchart"):
        inner_lines = inner_lines[1:]

    lines = [
        f"flowchart {direction}",
        f"    subgraph {_mermaid_escape_id(subgraph_name)}[{subgraph_name}]",
    ]
    for line in inner_lines:
        if line.strip():
            lines.append(f"    {line}")
    lines.append("    end")

    return "\n".join(lines)


def _node_to_mermaid(
    node: GraphNode,
    var: str,
    show_said: bool,
    show_label: bool,
    max_label_length: int,
) -> str:
    """
    Convert GraphNode to Mermaid node definition.

    Example:
        n0["Credential<br/>EF1x2Kvx..."]
    """
    # Get shape brackets for node type
    left, right = NODE_SHAPES.get(node.node_type, ("[", "]"))

    # Build label parts
    parts = []

    # Type name
    type_name = node.node_type.value.capitalize()
    parts.append(type_name)

    # Custom label if available
    if show_label and node.label:
        label = node.label
        if len(label) > max_label_length:
            label = label[:max_label_length - 3] + "..."
        parts.append(label)
    elif show_said:
        parts.append(node.said)
    else:
        parts.append(_said_short(node.said))

    # Join with line break (Mermaid uses <br/>)
    label = "<br/>".join(parts)

    # Escape special characters in label
    label = _mermaid_escape_label(label)

    return f'{var}{left}"{label}"{right}'


def _edge_to_mermaid(
    edge: GraphEdge,
    source_var: str,
    target_var: str,
    show_operator: bool,
) -> str:
    """
    Convert GraphEdge to Mermaid edge definition.

    Example:
        n0 -->|"acdc @I2I"| n1
    """
    # Build edge label
    label_parts = [edge.edge_type]
    if show_operator and edge.operator != "ANY":
        label_parts.append(f"@{edge.operator}")

    label = " ".join(label_parts)
    label = _mermaid_escape_label(label)

    return f'{source_var} -->|"{label}"| {target_var}'


def _said_short(said: str, length: int = 12) -> str:
    """
    Truncate SAID for display.

    Keeps the first `length` characters and adds ellipsis.
    SAIDs start with 'E' so the first char is always visible.
    """
    if len(said) <= length:
        return said
    return said[:length] + "..."


def _mermaid_escape_label(label: str) -> str:
    """
    Escape special characters for Mermaid labels.

    Mermaid uses double quotes for labels, so we need to escape:
    - Double quotes: " → &quot;
    - Angle brackets (but NOT <br/> which Mermaid uses for line breaks)
    """
    # Temporarily protect <br/> tags
    label = label.replace("<br/>", "\x00BR\x00")
    # Escape special characters
    label = label.replace('"', "&quot;")
    label = label.replace("<", "&lt;")
    label = label.replace(">", "&gt;")
    # Restore <br/> tags
    label = label.replace("\x00BR\x00", "<br/>")
    return label


def _mermaid_escape_id(text: str) -> str:
    """
    Convert text to valid Mermaid ID.

    Removes special characters and replaces spaces with underscores.
    """
    return "".join(c if c.isalnum() else "_" for c in text)


def export_mermaid_sequence(
    graph: PropertyGraph,
    root_said: Optional[str] = None,
) -> str:
    """
    Generate Mermaid sequence diagram for credential chain.

    Shows the temporal flow of credential issuance as a sequence.

    Args:
        graph: PropertyGraph to visualize
        root_said: Starting credential SAID (uses first node if not specified)

    Returns:
        Mermaid sequence diagram as string
    """
    lines = ["sequenceDiagram"]

    # Get participants (issuers/identifiers)
    participants = set()
    for node in graph.nodes.values():
        if node.issuer:
            participants.add(node.issuer)
        if node.node_type == NodeType.IDENTIFIER:
            participants.add(node.said)

    # Declare participants
    for p in sorted(participants):
        short = _said_short(p, 8)
        lines.append(f"    participant {_mermaid_escape_id(p)} as {short}")

    lines.append("")

    # Generate messages for edges
    for edge in graph.edges:
        source_node = graph.get_node(edge.source_said)
        target_node = graph.get_node(edge.target_said)

        if source_node and target_node:
            # Determine participants
            source_p = source_node.issuer or edge.source_said
            target_p = target_node.issuer or edge.target_said

            # Arrow type based on operator
            arrow = "->>" if edge.operator == "I2I" else "-->"

            # Message
            msg = f"{edge.edge_type}"
            if edge.operator != "ANY":
                msg += f" @{edge.operator}"

            lines.append(
                f"    {_mermaid_escape_id(source_p)}{arrow}"
                f"{_mermaid_escape_id(target_p)}: {msg}"
            )

    return "\n".join(lines)
