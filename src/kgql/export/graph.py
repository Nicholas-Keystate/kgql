# -*- encoding: utf-8 -*-
"""
KGQL PropertyGraph - Common Intermediate Representation for Graph Export.

All formatters (Neo4j, RDF, Mermaid, JSON Property Graph) consume this IR
rather than QueryResult directly. This avoids duplicating edge extraction
logic in every formatter.

Flow:
    QueryResult ──→ PropertyGraph ──→ Neo4j Cypher
    VerifiedPath ─┘                ├─→ JSON Property Graph
                                   ├─→ RDF/Turtle
                                   └─→ Mermaid

Key principle: "Resolution IS Verification" — extracted edges from ACDC
credentials are already verified by virtue of the credentials existing.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from kgql.api.kgql import QueryResult, QueryResultItem
    from kgql.trust_path.analyzer import VerifiedPath
    from kgql.wrappers.acdc_edge_resolver import ACDCEdgeResolver


class NodeType(str, Enum):
    """Types of nodes in the property graph."""
    CREDENTIAL = "credential"
    IDENTIFIER = "identifier"    # AID node
    SCHEMA = "schema"
    FRAMEWORK = "framework"


class EdgeKind(str, Enum):
    """
    Known edge kinds for ACDC credential relationships.

    Maps to edge keys in the 'e' field of ACDC credentials.
    """
    ACDC = "acdc"               # Chained credential reference
    ISSUANCE = "iss"            # Issuance event
    DELEGATION = "delegator"    # Delegator (master AID)
    PREVIOUS = "previous"       # Previous credential (monotonic chain)
    SESSION = "session"         # Session credential
    PARENT = "parent"           # Parent credential in chain
    ANCHOR = "anc"              # Anchor event
    REGISTRY = "vcp"            # Registry inception
    WATCHER = "watcher"         # Watcher attestation


@dataclass(frozen=True)
class GraphNode:
    """
    A node in the property graph.

    Represents a credential, AID, schema, or governance framework.
    Frozen for hashability and immutable graph semantics.

    Attributes:
        said: Self-Addressing Identifier (primary key)
        node_type: Type classification (credential, identifier, etc.)
        issuer: AID of issuer (for credentials)
        schema: Schema SAID (for credentials)
        attributes: Credential attributes from 'a' field
        label: Human-readable label for visualization
        key_state_seq: KEL sequence number (KEL metadata)
        delegation_depth: Delegation chain depth (KEL metadata)
        issued_at: Issuance timestamp (TEL metadata)
        revoked_at: Revocation timestamp (TEL metadata)
        registry: Registry SAID (TEL metadata)
    """
    said: str
    node_type: NodeType
    issuer: str = ""
    schema: str = ""
    attributes: tuple = field(default_factory=tuple)  # Frozen-compatible
    label: str = ""
    # KEL metadata
    key_state_seq: Optional[int] = None
    delegation_depth: Optional[int] = None
    # TEL metadata
    issued_at: Optional[str] = None
    revoked_at: Optional[str] = None
    registry: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "said": self.said,
            "type": self.node_type.value,
        }
        if self.issuer:
            result["issuer"] = self.issuer
        if self.schema:
            result["schema"] = self.schema
        if self.attributes:
            result["attributes"] = dict(self.attributes)
        if self.label:
            result["label"] = self.label
        if self.key_state_seq is not None:
            result["key_state_seq"] = self.key_state_seq
        if self.delegation_depth is not None:
            result["delegation_depth"] = self.delegation_depth
        if self.issued_at:
            result["issued_at"] = self.issued_at
        if self.revoked_at:
            result["revoked_at"] = self.revoked_at
        if self.registry:
            result["registry"] = self.registry
        return result


@dataclass(frozen=True)
class GraphEdge:
    """
    An edge in the property graph.

    Represents a relationship between two nodes (credentials, AIDs, etc.).

    Attributes:
        source_said: SAID of source node
        target_said: SAID of target node
        edge_type: Edge key from ACDC 'e' field (e.g., "acdc", "delegator")
        operator: Constraint operator (I2I, DI2I, NI2I, ANY)
        weight: Optional numeric weight for analytics
        metadata: Additional edge properties as frozen tuple of pairs
    """
    source_said: str
    target_said: str
    edge_type: str
    operator: str = "ANY"  # I2I, DI2I, NI2I, ANY
    weight: Optional[float] = None
    metadata: tuple = field(default_factory=tuple)  # Frozen-compatible

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "source": self.source_said,
            "target": self.target_said,
            "type": self.edge_type,
            "operator": self.operator,
        }
        if self.weight is not None:
            result["weight"] = self.weight
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass
class PropertyGraph:
    """
    Common intermediate representation for graph export.

    All formatters consume this IR rather than raw QueryResult or
    VerifiedPath objects. This centralizes edge extraction logic
    and provides a uniform graph structure.

    Attributes:
        nodes: Dict mapping SAID → GraphNode
        edges: List of GraphEdge relationships
        metadata: Framework info, query metadata, etc.
    """
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        """
        Add a node to the graph.

        If a node with the same SAID exists, it is replaced.

        Args:
            node: GraphNode to add
        """
        self.nodes[node.said] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """
        Add an edge to the graph.

        Duplicate edges are allowed (multi-graph semantics).

        Args:
            edge: GraphEdge to add
        """
        self.edges.append(edge)

    def node_count(self) -> int:
        """Return number of nodes in the graph."""
        return len(self.nodes)

    def edge_count(self) -> int:
        """Return number of edges in the graph."""
        return len(self.edges)

    def get_node(self, said: str) -> Optional[GraphNode]:
        """Get a node by SAID, or None if not found."""
        return self.nodes.get(said)

    def has_node(self, said: str) -> bool:
        """Check if a node exists by SAID."""
        return said in self.nodes

    def get_edges_from(self, source_said: str) -> list[GraphEdge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source_said == source_said]

    def get_edges_to(self, target_said: str) -> list[GraphEdge]:
        """Get all edges pointing to a node."""
        return [e for e in self.edges if e.target_said == target_said]

    @classmethod
    def from_query_result(
        cls,
        result: "QueryResult",
        edge_resolver: Optional["ACDCEdgeResolver"] = None,
    ) -> "PropertyGraph":
        """
        Build PropertyGraph from KGQL QueryResult.

        Extracts nodes from result items and edges from ACDC 'e' fields.
        Creates implicit nodes for issuers and schemas not in the result set.

        Args:
            result: QueryResult from KGQL query execution
            edge_resolver: Optional ACDCEdgeResolver for edge extraction.
                If not provided, edges are extracted from raw 'e' field.

        Returns:
            PropertyGraph with nodes and edges
        """
        graph = cls()

        # Copy query metadata
        if result.metadata:
            graph.metadata["query"] = result.metadata

        # Process each result item
        for item in result.items:
            # Create node from result item
            node = cls._item_to_node(item)
            graph.add_node(node)

            # Extract edges from credential data
            cred_data = item.data
            if isinstance(cred_data, dict):
                edges = cls._extract_edges(item.said, cred_data, edge_resolver)
                for edge in edges:
                    graph.add_edge(edge)

                    # Create implicit target node if not already in graph
                    if not graph.has_node(edge.target_said):
                        implicit_node = GraphNode(
                            said=edge.target_said,
                            node_type=NodeType.CREDENTIAL,  # Default, may be wrong
                            label=f"Referenced by {edge.edge_type}",
                        )
                        graph.add_node(implicit_node)

                # Create implicit issuer node
                issuer = cred_data.get("i") or cred_data.get("issuer")
                if issuer and not graph.has_node(issuer):
                    graph.add_node(GraphNode(
                        said=issuer,
                        node_type=NodeType.IDENTIFIER,
                        label="Issuer AID",
                    ))

                # Create implicit schema node
                schema = cred_data.get("s") or cred_data.get("schema")
                if schema and not graph.has_node(schema):
                    graph.add_node(GraphNode(
                        said=schema,
                        node_type=NodeType.SCHEMA,
                        label="Schema",
                    ))

        return graph

    @classmethod
    def from_verified_path(cls, path: "VerifiedPath") -> "PropertyGraph":
        """
        Build PropertyGraph from TrustPathAnalyzer VerifiedPath.

        Each PathStep becomes an edge; unique SAIDs become nodes.

        Args:
            path: VerifiedPath from trust path analysis

        Returns:
            PropertyGraph representing the trust path
        """
        graph = cls()
        graph.metadata["path"] = {
            "root": path.root_said,
            "target": path.target_said,
            "depth": path.depth,
        }

        # Track SAIDs we've seen for node creation
        seen_saids: set[str] = set()

        for step in path.steps:
            # Add source node if not seen
            if step.source_said not in seen_saids:
                graph.add_node(GraphNode(
                    said=step.source_said,
                    node_type=NodeType.CREDENTIAL,
                ))
                seen_saids.add(step.source_said)

            # Add target node if not seen
            if step.target_said not in seen_saids:
                graph.add_node(GraphNode(
                    said=step.target_said,
                    node_type=NodeType.CREDENTIAL,
                ))
                seen_saids.add(step.target_said)

            # Add edge
            graph.add_edge(GraphEdge(
                source_said=step.source_said,
                target_said=step.target_said,
                edge_type=step.edge_type,
                operator=step.operator.value if hasattr(step.operator, 'value') else str(step.operator),
            ))

        return graph

    @classmethod
    def from_credentials(
        cls,
        credentials: list[dict],
        edge_resolver: Optional["ACDCEdgeResolver"] = None,
    ) -> "PropertyGraph":
        """
        Build PropertyGraph from raw credential dicts.

        For direct use without KGQL query execution.

        Args:
            credentials: List of ACDC credential dicts
            edge_resolver: Optional ACDCEdgeResolver for edge extraction

        Returns:
            PropertyGraph with nodes and edges
        """
        graph = cls()

        for cred in credentials:
            said = cred.get("d")
            if not said:
                continue

            # Create node
            node = GraphNode(
                said=said,
                node_type=NodeType.CREDENTIAL,
                issuer=cred.get("i", ""),
                schema=cred.get("s", ""),
                attributes=tuple((cred.get("a") or {}).items()),
            )
            graph.add_node(node)

            # Extract edges
            edges = cls._extract_edges(said, cred, edge_resolver)
            for edge in edges:
                graph.add_edge(edge)

                # Create implicit target node
                if not graph.has_node(edge.target_said):
                    graph.add_node(GraphNode(
                        said=edge.target_said,
                        node_type=NodeType.CREDENTIAL,
                    ))

        return graph

    @staticmethod
    def _item_to_node(item: "QueryResultItem") -> GraphNode:
        """Convert QueryResultItem to GraphNode."""
        data = item.data if isinstance(item.data, dict) else {}

        # Determine node type from data structure
        node_type = NodeType.CREDENTIAL  # Default
        version = data.get("v", "")
        if isinstance(version, str):
            if version.startswith("ACDC"):
                node_type = NodeType.CREDENTIAL
            elif "Schema" in str(data.get("$id", "")):
                node_type = NodeType.SCHEMA

        # Extract attributes (from 'a' field or raw data)
        attrs = data.get("a", {})
        if not isinstance(attrs, dict):
            attrs = {}

        return GraphNode(
            said=item.said,
            node_type=node_type,
            issuer=data.get("i", ""),
            schema=data.get("s", ""),
            attributes=tuple(attrs.items()),
            # KEL metadata from keystate if available
            key_state_seq=getattr(item.keystate, 'sn', None) if item.keystate else None,
        )

    @staticmethod
    def _extract_edges(
        source_said: str,
        cred_data: dict,
        edge_resolver: Optional["ACDCEdgeResolver"] = None,
    ) -> list[GraphEdge]:
        """
        Extract edges from ACDC credential data.

        Uses ACDCEdgeResolver if provided, otherwise parses 'e' field directly.
        """
        edges: list[GraphEdge] = []
        edge_field = cred_data.get("e", {})

        if not isinstance(edge_field, dict):
            return edges

        if edge_resolver:
            # Use resolver for proper edge extraction
            edge_keys = edge_resolver.list_edges(cred_data)
            for key in edge_keys:
                edge_ref = edge_resolver.get_edge(cred_data, key)
                if edge_ref and edge_ref.target_said:
                    metadata = edge_ref.metadata or {}
                    edges.append(GraphEdge(
                        source_said=source_said,
                        target_said=edge_ref.target_said,
                        edge_type=edge_ref.edge_type,
                        operator=metadata.get("operator", "ANY"),
                        metadata=tuple(metadata.items()),
                    ))
        else:
            # Direct extraction from 'e' field
            for key, nested in edge_field.items():
                if not isinstance(nested, dict):
                    continue
                target_said = nested.get("d")
                if not target_said:
                    continue

                # Extract operator if present (from 'o' field)
                operator = nested.get("o", "ANY")

                edges.append(GraphEdge(
                    source_said=source_said,
                    target_said=target_said,
                    edge_type=key,
                    operator=operator,
                ))

        return edges

    def to_dict(self) -> dict:
        """Convert graph to dictionary for JSON serialization."""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": self.metadata,
            "stats": {
                "node_count": self.node_count(),
                "edge_count": self.edge_count(),
            },
        }
