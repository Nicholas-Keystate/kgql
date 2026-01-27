# -*- encoding: utf-8 -*-
"""
KGQL Trust Path Analyzer - BFS-based trust path discovery.

Computes and exposes trust/delegation paths between any two nodes in
the credential graph. Uses the EdgeResolverRegistry for traversal,
so paths can span multiple protocols.

Key insight: "Resolution IS Verification" — each step in the path is
verified by the act of resolution. If a SAID resolves, it's authentic.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kgql.parser.ast import EdgeOperator
from kgql.wrappers.edge_resolver import EdgeRef


@dataclass
class PathStep:
    """
    A single step in a trust path.

    Represents one edge traversal from source to target.

    Attributes:
        source_said: SAID of the source node
        target_said: SAID of the target node
        edge_type: Type of edge traversed (e.g., "iss", "acdc", "delegation")
        operator: Edge operator constraint (I2I, DI2I, etc.)
        edge_ref: The resolved EdgeRef for this step
    """
    source_said: str
    target_said: str
    edge_type: str
    operator: EdgeOperator = EdgeOperator.ANY
    edge_ref: Optional[EdgeRef] = None

    def to_dict(self) -> dict:
        return {
            "source": self.source_said,
            "target": self.target_said,
            "edge_type": self.edge_type,
            "operator": self.operator.value,
        }


@dataclass
class VerifiedPath:
    """
    A verified trust path between two nodes.

    Each step in the path has been resolved (and thus verified).
    The path represents a chain of credential relationships.

    Attributes:
        steps: Ordered list of PathStep from root to target
        root_said: Starting node SAID
        target_said: Ending node SAID
    """
    steps: list[PathStep] = field(default_factory=list)
    root_said: str = ""
    target_said: str = ""

    @property
    def depth(self) -> int:
        """Number of edges in the path."""
        return len(self.steps)

    @property
    def operators(self) -> list[EdgeOperator]:
        """Operators used along the path."""
        return [s.operator for s in self.steps]

    @property
    def edge_types(self) -> list[str]:
        """Edge types traversed along the path."""
        return [s.edge_type for s in self.steps]

    @property
    def saids(self) -> list[str]:
        """All SAIDs in the path, from root to target."""
        if not self.steps:
            return []
        result = [self.steps[0].source_said]
        for step in self.steps:
            result.append(step.target_said)
        return result

    def to_dict(self) -> dict:
        return {
            "root": self.root_said,
            "target": self.target_said,
            "depth": self.depth,
            "steps": [s.to_dict() for s in self.steps],
            "operators": [op.value for op in self.operators],
        }

    def to_mermaid(self) -> str:
        """Render path as a Mermaid flowchart diagram."""
        lines = ["graph LR"]
        for i, step in enumerate(self.steps):
            src = step.source_said[:12]
            tgt = step.target_said[:12]
            label = f"{step.edge_type} @{step.operator.value}"
            lines.append(f"    {src}[{src}...] -->|{label}| {tgt}[{tgt}...]")
        return "\n".join(lines)


class TrustPathAnalyzer:
    """
    Finds trust/delegation paths in credential graphs.

    Uses BFS for shortest-path and depth-limited search for all paths.
    Traversal uses a neighbor function that returns (target_said, edge_type,
    operator, edge_ref) for each outgoing edge from a node.

    Usage:
        analyzer = TrustPathAnalyzer(neighbor_fn=my_neighbor_fn)
        paths = analyzer.find_paths("ERootSAID", "ETargetSAID", max_depth=6)
        shortest = analyzer.shortest_path("ERootSAID", "ETargetSAID")
    """

    def __init__(
        self,
        neighbor_fn: Optional[Callable[[str], list[tuple[str, str, EdgeOperator, Optional[EdgeRef]]]]] = None,
    ):
        """
        Initialize with a neighbor function.

        Args:
            neighbor_fn: Callable(said) -> list of (target_said, edge_type, operator, edge_ref).
                Returns all outgoing edges from a node.
        """
        self._neighbor_fn = neighbor_fn

    def find_paths(
        self,
        root_said: str,
        target_said: str,
        max_depth: int = 6,
        edge_type_filter: Optional[str] = None,
        operator_filter: Optional[EdgeOperator] = None,
    ) -> list[VerifiedPath]:
        """
        Find all paths from root to target within max_depth.

        Uses depth-limited DFS to enumerate all paths.

        Args:
            root_said: Starting node SAID
            target_said: Target node SAID
            max_depth: Maximum path depth (default: 6)
            edge_type_filter: Only traverse edges of this type
            operator_filter: Only traverse edges with this operator or stronger

        Returns:
            List of VerifiedPath objects, shortest first
        """
        if self._neighbor_fn is None:
            return []

        paths: list[VerifiedPath] = []
        # DFS with path tracking
        stack: list[tuple[str, list[PathStep], set[str]]] = [
            (root_said, [], {root_said})
        ]

        while stack:
            current, path, visited = stack.pop()

            if current == target_said:
                paths.append(VerifiedPath(
                    steps=list(path),
                    root_said=root_said,
                    target_said=target_said,
                ))
                continue

            if len(path) >= max_depth:
                continue

            neighbors = self._neighbor_fn(current)
            for tgt, etype, op, eref in neighbors:
                if tgt in visited:
                    continue
                if edge_type_filter and etype != edge_type_filter:
                    continue
                if operator_filter:
                    from kgql.governance.checker import operator_satisfies
                    if not operator_satisfies(op, operator_filter):
                        continue

                step = PathStep(
                    source_said=current,
                    target_said=tgt,
                    edge_type=etype,
                    operator=op,
                    edge_ref=eref,
                )
                new_visited = visited | {tgt}
                stack.append((tgt, path + [step], new_visited))

        # Sort by depth (shortest first)
        paths.sort(key=lambda p: p.depth)
        return paths

    def shortest_path(
        self,
        root_said: str,
        target_said: str,
        max_depth: int = 6,
        edge_type_filter: Optional[str] = None,
        operator_filter: Optional[EdgeOperator] = None,
    ) -> Optional[VerifiedPath]:
        """
        Find the shortest path from root to target.

        Uses BFS for optimal shortest path.

        Args:
            root_said: Starting node SAID
            target_said: Target node SAID
            max_depth: Maximum path depth
            edge_type_filter: Only traverse edges of this type
            operator_filter: Only traverse edges with this operator or stronger

        Returns:
            Shortest VerifiedPath, or None if no path exists
        """
        if self._neighbor_fn is None:
            return None

        if root_said == target_said:
            return VerifiedPath(
                steps=[], root_said=root_said, target_said=target_said,
            )

        # BFS
        queue: deque[tuple[str, list[PathStep], set[str]]] = deque()
        queue.append((root_said, [], {root_said}))

        while queue:
            current, path, visited = queue.popleft()

            if len(path) >= max_depth:
                continue

            neighbors = self._neighbor_fn(current)
            for tgt, etype, op, eref in neighbors:
                if tgt in visited:
                    continue
                if edge_type_filter and etype != edge_type_filter:
                    continue
                if operator_filter:
                    from kgql.governance.checker import operator_satisfies
                    if not operator_satisfies(op, operator_filter):
                        continue

                step = PathStep(
                    source_said=current,
                    target_said=tgt,
                    edge_type=etype,
                    operator=op,
                    edge_ref=eref,
                )
                new_path = path + [step]

                if tgt == target_said:
                    return VerifiedPath(
                        steps=new_path,
                        root_said=root_said,
                        target_said=target_said,
                    )

                new_visited = visited | {tgt}
                queue.append((tgt, new_path, new_visited))

        return None
