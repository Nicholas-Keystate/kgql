"""
KGQL Trust Path Analyzer - Computes trust/delegation paths in credential graphs.

Implements KGQL Phase 5.2: Trust Path Analysis. Enables queries like:

    TRAVERSE FROM 'ERootAID...' TO 'ETargetSAID...' VIA [:iss @DI2I]

This module provides:
- TrustPathAnalyzer: BFS-based path finder across credential graph
- VerifiedPath: A verified path between two nodes
- PathStep: Single step (edge) in a path
"""

from kgql.trust_path.analyzer import TrustPathAnalyzer, VerifiedPath, PathStep

__all__ = [
    "TrustPathAnalyzer",
    "VerifiedPath",
    "PathStep",
]
