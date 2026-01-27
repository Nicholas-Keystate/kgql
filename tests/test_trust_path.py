# -*- encoding: utf-8 -*-
"""
Tests for KGQL Trust Path Analyzer - Phase 5.2

Tests BFS/DFS path discovery, filtering, Mermaid rendering, and
integration with EdgeRef.
"""

import pytest

from kgql.parser.ast import EdgeOperator
from kgql.wrappers.edge_resolver import EdgeRef
from kgql.trust_path.analyzer import TrustPathAnalyzer, VerifiedPath, PathStep


# ── Test Graph Fixture ───────────────────────────────────────────────
#
# Graph structure:
#   ROOT --iss(I2I)--> A --iss(DI2I)--> B --iss(NI2I)--> TARGET
#   ROOT --delegation(DI2I)--> C --delegation(DI2I)--> TARGET
#   A --acdc(ANY)--> D  (dead end)
#

def _build_graph():
    """Build a test graph as adjacency list."""
    graph = {
        "ROOT": [
            ("A", "iss", EdgeOperator.I2I, None),
            ("C", "delegation", EdgeOperator.DI2I, None),
        ],
        "A": [
            ("B", "iss", EdgeOperator.DI2I, None),
            ("D", "acdc", EdgeOperator.ANY, None),
        ],
        "B": [
            ("TARGET", "iss", EdgeOperator.NI2I, None),
        ],
        "C": [
            ("TARGET", "delegation", EdgeOperator.DI2I, None),
        ],
        "D": [],
        "TARGET": [],
    }
    return graph


def _neighbor_fn(said):
    graph = _build_graph()
    return graph.get(said, [])


# ── PathStep Tests ───────────────────────────────────────────────────


class TestPathStep:
    """PathStep data model."""

    def test_basic_step(self):
        step = PathStep(
            source_said="ROOT",
            target_said="A",
            edge_type="iss",
            operator=EdgeOperator.I2I,
        )
        assert step.source_said == "ROOT"
        assert step.target_said == "A"
        assert step.edge_type == "iss"
        assert step.operator == EdgeOperator.I2I

    def test_to_dict(self):
        step = PathStep("ROOT", "A", "iss", EdgeOperator.I2I)
        d = step.to_dict()
        assert d["source"] == "ROOT"
        assert d["target"] == "A"
        assert d["operator"] == "I2I"

    def test_with_edge_ref(self):
        eref = EdgeRef(target_said="A", edge_type="iss")
        step = PathStep("ROOT", "A", "iss", EdgeOperator.I2I, edge_ref=eref)
        assert step.edge_ref is eref


# ── VerifiedPath Tests ───────────────────────────────────────────────


class TestVerifiedPath:
    """VerifiedPath data model."""

    def test_empty_path(self):
        path = VerifiedPath(root_said="ROOT", target_said="ROOT")
        assert path.depth == 0
        assert path.saids == []
        assert path.operators == []

    def test_single_step(self):
        path = VerifiedPath(
            steps=[PathStep("ROOT", "A", "iss", EdgeOperator.I2I)],
            root_said="ROOT",
            target_said="A",
        )
        assert path.depth == 1
        assert path.saids == ["ROOT", "A"]
        assert path.operators == [EdgeOperator.I2I]
        assert path.edge_types == ["iss"]

    def test_multi_step(self):
        path = VerifiedPath(
            steps=[
                PathStep("ROOT", "A", "iss", EdgeOperator.I2I),
                PathStep("A", "B", "iss", EdgeOperator.DI2I),
            ],
            root_said="ROOT",
            target_said="B",
        )
        assert path.depth == 2
        assert path.saids == ["ROOT", "A", "B"]

    def test_to_dict(self):
        path = VerifiedPath(
            steps=[PathStep("ROOT", "A", "iss", EdgeOperator.I2I)],
            root_said="ROOT",
            target_said="A",
        )
        d = path.to_dict()
        assert d["root"] == "ROOT"
        assert d["target"] == "A"
        assert d["depth"] == 1
        assert len(d["steps"]) == 1

    def test_to_mermaid(self):
        path = VerifiedPath(
            steps=[
                PathStep("ROOT_SAID_12345", "A_SAID_123456", "iss", EdgeOperator.I2I),
                PathStep("A_SAID_123456", "B_SAID_123456", "iss", EdgeOperator.DI2I),
            ],
            root_said="ROOT_SAID_12345",
            target_said="B_SAID_123456",
        )
        mermaid = path.to_mermaid()
        assert "graph LR" in mermaid
        assert "iss @I2I" in mermaid
        assert "iss @DI2I" in mermaid


# ── TrustPathAnalyzer Tests ──────────────────────────────────────────


class TestTrustPathAnalyzerShortestPath:
    """BFS shortest path discovery."""

    def test_shortest_path_direct(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        path = analyzer.shortest_path("ROOT", "A")
        assert path is not None
        assert path.depth == 1
        assert path.steps[0].edge_type == "iss"

    def test_shortest_path_two_hops(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        path = analyzer.shortest_path("ROOT", "TARGET")
        assert path is not None
        assert path.depth == 2  # ROOT->C->TARGET is shorter than ROOT->A->B->TARGET

    def test_shortest_path_chooses_shorter(self):
        """ROOT->C->TARGET (2 hops) beats ROOT->A->B->TARGET (3 hops)."""
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        path = analyzer.shortest_path("ROOT", "TARGET")
        assert path.depth == 2
        assert path.steps[0].target_said == "C"

    def test_shortest_path_self(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        path = analyzer.shortest_path("ROOT", "ROOT")
        assert path is not None
        assert path.depth == 0

    def test_shortest_path_not_found(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        path = analyzer.shortest_path("D", "ROOT")  # D is a dead end, no reverse edges
        assert path is None

    def test_shortest_path_max_depth(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        # ROOT->A->B->TARGET is 3 hops, limit to 2
        # ROOT->C->TARGET is 2 hops, should still work
        path = analyzer.shortest_path("ROOT", "TARGET", max_depth=2)
        assert path is not None
        assert path.depth == 2

    def test_shortest_path_max_depth_too_short(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        path = analyzer.shortest_path("ROOT", "TARGET", max_depth=1)
        assert path is None

    def test_shortest_path_no_neighbor_fn(self):
        analyzer = TrustPathAnalyzer()
        assert analyzer.shortest_path("ROOT", "TARGET") is None


class TestTrustPathAnalyzerFindPaths:
    """DFS all-paths discovery."""

    def test_find_all_paths(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths("ROOT", "TARGET")
        assert len(paths) == 2  # Two paths to TARGET

    def test_find_paths_sorted_by_depth(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths("ROOT", "TARGET")
        assert paths[0].depth <= paths[1].depth

    def test_find_paths_depth_limit(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths("ROOT", "TARGET", max_depth=2)
        # Only ROOT->C->TARGET (2 hops) fits
        assert len(paths) == 1
        assert paths[0].depth == 2

    def test_find_paths_no_result(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths("D", "ROOT")
        assert paths == []

    def test_find_paths_no_neighbor_fn(self):
        analyzer = TrustPathAnalyzer()
        assert analyzer.find_paths("ROOT", "TARGET") == []


class TestTrustPathAnalyzerFilters:
    """Edge type and operator filtering."""

    def test_filter_by_edge_type(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths(
            "ROOT", "TARGET", edge_type_filter="delegation"
        )
        assert len(paths) == 1
        for step in paths[0].steps:
            assert step.edge_type == "delegation"

    def test_filter_by_edge_type_no_match(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths(
            "ROOT", "TARGET", edge_type_filter="nonexistent"
        )
        assert paths == []

    def test_filter_by_operator_i2i(self):
        """Only I2I edges → no path to TARGET (requires weaker edges)."""
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths(
            "ROOT", "TARGET", operator_filter=EdgeOperator.I2I
        )
        # ROOT->A (I2I) but A->B needs DI2I which doesn't satisfy I2I
        # ROOT->C (DI2I) doesn't satisfy I2I
        assert paths == []

    def test_filter_by_operator_di2i(self):
        """DI2I filter → only ROOT->C->TARGET (both DI2I)."""
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths(
            "ROOT", "TARGET", operator_filter=EdgeOperator.DI2I
        )
        # ROOT->A is I2I (satisfies DI2I), A->B is DI2I (satisfies),
        # but B->TARGET is NI2I (doesn't satisfy DI2I)
        # ROOT->C is DI2I (satisfies), C->TARGET is DI2I (satisfies)
        assert len(paths) == 1
        assert paths[0].steps[0].target_said == "C"

    def test_filter_by_operator_any(self):
        """ANY filter → all edges pass."""
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        paths = analyzer.find_paths(
            "ROOT", "TARGET", operator_filter=EdgeOperator.ANY
        )
        assert len(paths) == 2

    def test_shortest_path_with_filter(self):
        analyzer = TrustPathAnalyzer(neighbor_fn=_neighbor_fn)
        path = analyzer.shortest_path(
            "ROOT", "TARGET", edge_type_filter="delegation"
        )
        assert path is not None
        assert path.depth == 2
        assert all(s.edge_type == "delegation" for s in path.steps)


# ── Cycle Protection Tests ───────────────────────────────────────────


class TestCycleProtection:
    """Handles cycles without infinite loops."""

    def test_cycle_in_graph(self):
        def cyclic_neighbors(said):
            return {
                "A": [("B", "iss", EdgeOperator.I2I, None)],
                "B": [("A", "iss", EdgeOperator.I2I, None),
                       ("C", "iss", EdgeOperator.I2I, None)],
                "C": [],
            }.get(said, [])

        analyzer = TrustPathAnalyzer(neighbor_fn=cyclic_neighbors)
        path = analyzer.shortest_path("A", "C")
        assert path is not None
        assert path.depth == 2  # A->B->C

    def test_self_loop(self):
        def self_loop_neighbors(said):
            return {
                "A": [("A", "self", EdgeOperator.ANY, None),
                       ("B", "iss", EdgeOperator.I2I, None)],
                "B": [],
            }.get(said, [])

        analyzer = TrustPathAnalyzer(neighbor_fn=self_loop_neighbors)
        path = analyzer.shortest_path("A", "B")
        assert path is not None
        assert path.depth == 1
