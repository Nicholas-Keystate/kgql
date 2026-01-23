"""
KGQL Wrappers - Thin wrappers over existing keripy infrastructure.

These wrappers provide a consistent interface without duplicating any logic.
All actual work is delegated to existing keripy classes.

Edge Resolution:
    EdgeRef - Normalized edge reference across protocols
    EdgeResolver - Abstract interface for edge resolution
    ACDCEdgeResolver - KERI/ACDC credential edge resolver (with watcher support)
    EdgeResolverRegistry - Protocol-based resolver registry
    KNOWN_EDGE_TYPES - Dictionary of known edge types for reference

Watcher Support:
    ACDCEdgeResolver.get_watcher_edge() - Get watcher attestation edge
    ACDCEdgeResolver.get_watcher_aid() - Get watcher AID from edge
    ACDCEdgeResolver.has_watcher_attestation() - Check for watcher edge
    ACDCEdgeResolver.is_watcher_signed() - Check for embedded signature
"""

from kgql.wrappers.reger_wrapper import RegerWrapper
from kgql.wrappers.verifier_wrapper import VerifierWrapper
from kgql.wrappers.edge_resolver import EdgeRef, EdgeResolver
from kgql.wrappers.acdc_edge_resolver import ACDCEdgeResolver, KNOWN_EDGE_TYPES
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
    # Edge type reference
    "KNOWN_EDGE_TYPES",
]
