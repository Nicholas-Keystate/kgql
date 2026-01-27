# -*- encoding: utf-8 -*-
"""
KGQL PatternSpace Edge Resolver.

Resolves edges from a concept/pattern graph, enabling KGQL traversal
over the ontological structure (concepts, patterns, compositions).

Content format: a dict with at minimum a "slug" key identifying the
node, and optionally "type" ("concept" or "pattern").

Example:
    resolver = PatternSpaceEdgeResolver(edges_path="~/.claude/pattern_space/edges.json")
    edges = resolver.list_edges({"slug": "keri-runtime-singleton"})
    ref = resolver.get_edge({"slug": "keri-runtime-singleton"}, "references:habery")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from kgql.wrappers.edge_resolver import EdgeRef, EdgeResolver

logger = logging.getLogger(__name__)

VALID_EDGE_TYPES = frozenset({
    "references",
    "extends",
    "conflicts_with",
    "composable_with",
    "anti_pattern_of",
    "implements",
})


@dataclass
class GraphEdge:
    """An edge in the pattern space graph."""

    source: str
    source_type: str
    target: str
    target_type: str
    edge_type: str
    weight: float = 1.0


class PatternSpaceEdgeResolver(EdgeResolver):
    """Resolve edges from concept/pattern ontology graph.

    Loads edges from a JSON file and from optional concept/pattern
    registries. Exposes them via the standard EdgeResolver interface
    so KGQL queries can traverse concept-pattern relationships.

    Content passed to get_edge/list_edges must be a dict with:
      - "slug": node identifier (required)
      - "type": "concept" or "pattern" (optional, for filtering)

    Edge names are formatted as "{edge_type}:{target_slug}".
    """

    def __init__(
        self,
        edges_path: str | Path | None = None,
        load_registries: bool = True,
    ) -> None:
        self._edges_path = Path(edges_path) if edges_path else None
        self._load_registries = load_registries
        self._adjacency: dict[str, list[GraphEdge]] = {}
        self._loaded = False

    @property
    def protocol(self) -> str:
        return "pattern-space"

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self._edges_path and self._edges_path.exists():
            self._load_edges_file()
        if self._load_registries:
            self._build_from_registries()

    def _load_edges_file(self) -> None:
        try:
            data = json.loads(self._edges_path.read_text())
            for edge_data in data.get("edges", []):
                self._add_edge(GraphEdge(**edge_data))
        except Exception as e:
            logger.error("Failed to load pattern space edges: %s", e)

    def _build_from_registries(self) -> None:
        try:
            from agents.concept_directory import get_concept_directory
            from agents.pattern_registry import get_pattern_registry

            for concept in get_concept_directory().list_all():
                for related_slug in concept.related:
                    self._add_edge(GraphEdge(
                        source=concept.slug,
                        source_type="concept",
                        target=related_slug,
                        target_type="concept",
                        edge_type="references",
                    ))

            for pattern in get_pattern_registry().list_all():
                for concept_slug in pattern.concept_refs:
                    self._add_edge(GraphEdge(
                        source=pattern.slug,
                        source_type="pattern",
                        target=concept_slug,
                        target_type="concept",
                        edge_type="references",
                    ))
                for composable_slug in pattern.composable_with:
                    self._add_edge(GraphEdge(
                        source=pattern.slug,
                        source_type="pattern",
                        target=composable_slug,
                        target_type="pattern",
                        edge_type="composable_with",
                    ))
                for conflict_slug in pattern.conflicts_with:
                    self._add_edge(GraphEdge(
                        source=pattern.slug,
                        source_type="pattern",
                        target=conflict_slug,
                        target_type="pattern",
                        edge_type="conflicts_with",
                    ))
        except ImportError:
            logger.debug("Concept/pattern registries not available")

    def _add_edge(self, edge: GraphEdge) -> None:
        key = f"{edge.source}->{edge.target}:{edge.edge_type}"
        for existing in self._adjacency.get(edge.source, []):
            if f"{existing.source}->{existing.target}:{existing.edge_type}" == key:
                return
        self._adjacency.setdefault(edge.source, []).append(edge)

    def can_resolve(self, content: Any) -> bool:
        return isinstance(content, dict) and "slug" in content

    def get_edge(self, content: Any, edge_name: str) -> Optional[EdgeRef]:
        """Get a specific edge by name.

        Edge names use the format "{edge_type}:{target_slug}".
        If no colon, edge_name is treated as edge_type and the first
        matching edge is returned.
        """
        self._ensure_loaded()
        if not isinstance(content, dict) or "slug" not in content:
            return None

        slug = content["slug"]
        edges = self._adjacency.get(slug, [])

        if ":" in edge_name:
            edge_type, target = edge_name.split(":", 1)
            for e in edges:
                if e.edge_type == edge_type and e.target == target:
                    return self._to_edge_ref(e)
        else:
            for e in edges:
                if e.edge_type == edge_name:
                    return self._to_edge_ref(e)

        return None

    def list_edges(self, content: Any) -> list[str]:
        """List all edge names from a node.

        Returns edges as "{edge_type}:{target_slug}".
        """
        self._ensure_loaded()
        if not isinstance(content, dict) or "slug" not in content:
            return []

        slug = content["slug"]
        return [
            f"{e.edge_type}:{e.target}"
            for e in self._adjacency.get(slug, [])
        ]

    def get_neighbors(
        self,
        slug: str,
        edge_type: str | None = None,
    ) -> list[EdgeRef]:
        """Get all outgoing edges from a node.

        Convenience method beyond the base EdgeResolver interface.
        """
        self._ensure_loaded()
        edges = self._adjacency.get(slug, [])
        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]
        return [self._to_edge_ref(e) for e in edges]

    def get_stats(self) -> dict:
        """Get graph statistics."""
        self._ensure_loaded()
        edge_types: dict[str, int] = {}
        total_edges = 0
        for edges in self._adjacency.values():
            for e in edges:
                edge_types[e.edge_type] = edge_types.get(e.edge_type, 0) + 1
                total_edges += 1
        return {
            "total_nodes": len(self._adjacency),
            "total_edges": total_edges,
            "edge_types": edge_types,
        }

    @staticmethod
    def _to_edge_ref(edge: GraphEdge) -> EdgeRef:
        return EdgeRef(
            target_said=edge.target,
            edge_type=edge.edge_type,
            payload_type=None,
            source_protocol="pattern-space",
            metadata={
                "source": edge.source,
                "source_type": edge.source_type,
                "target_type": edge.target_type,
                "weight": edge.weight,
            },
        )
