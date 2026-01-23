"""
KGQL Wrappers - Thin wrappers over existing keripy infrastructure.

These wrappers provide a consistent interface without duplicating any logic.
All actual work is delegated to existing keripy classes.

Edge Resolution:
    EdgeRef - Normalized edge reference across protocols
    EdgeResolver - Abstract interface for edge resolution
    ACDCEdgeResolver - KERI/ACDC credential edge resolver
    EdgeResolverRegistry - Protocol-based resolver registry
"""

from kgql.wrappers.reger_wrapper import RegerWrapper
from kgql.wrappers.verifier_wrapper import VerifierWrapper
from kgql.wrappers.edge_resolver import EdgeRef, EdgeResolver
from kgql.wrappers.acdc_edge_resolver import ACDCEdgeResolver
from kgql.wrappers.edge_registry import EdgeResolverRegistry, create_default_registry

__all__ = [
    # Existing wrappers
    "RegerWrapper",
    "VerifierWrapper",
    # Edge resolution
    "EdgeRef",
    "EdgeResolver",
    "ACDCEdgeResolver",
    "EdgeResolverRegistry",
    "create_default_registry",
]
