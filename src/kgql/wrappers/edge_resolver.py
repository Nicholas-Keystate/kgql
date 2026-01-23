# -*- encoding: utf-8 -*-
"""
KGQL Edge Resolver - Abstract interface for cross-protocol edge resolution.

This module defines the EdgeResolver abstraction that enables KGQL to traverse
credential graphs across different protocols (KERI/ACDC, S3, Git, etc.) with
uniform semantics.

Key insight: CESR payload types identify message semantics, enabling protocol
detection without custom conventions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EdgeRef:
    """
    Normalized edge reference across protocols.

    Represents a resolved edge from any protocol, providing uniform access
    to target SAIDs, edge types, and metadata.

    Attributes:
        target_said: SAID of the target (from "d" field in KERI messages)
        edge_type: Edge key identifying the relationship (e.g., "acdc", "iss", "delegator")
        payload_type: CESR/KERI message type (e.g., "iss", "icp", "rot") from "t" field
        source_protocol: Protocol that resolved this edge (e.g., "keri", "s3", "git")
        metadata: Protocol-specific metadata (issuer, schema, version, etc.)
        raw_message: Full nested message if needed for further processing
    """
    target_said: str
    edge_type: str
    payload_type: Optional[str] = None
    source_protocol: str = "keri"
    metadata: dict = field(default_factory=dict)
    raw_message: Optional[dict] = None

    def __repr__(self) -> str:
        return (
            f"EdgeRef(target={self.target_said[:16]}..., "
            f"type={self.edge_type}, payload={self.payload_type})"
        )


class EdgeResolver(ABC):
    """
    Abstract edge resolution interface.

    Implement this class for each protocol that can contain KERI credential edges.
    Each resolver knows how to extract edge references from its protocol's format.

    Example implementations:
        - ACDCEdgeResolver: KERI/ACDC credentials with "e" field
        - S3EdgeResolver: S3 objects with x-keri-edge-* metadata
        - GitEdgeResolver: Git commits with KERI-SAID attestations
    """

    @property
    @abstractmethod
    def protocol(self) -> str:
        """
        Protocol identifier for this resolver.

        Returns:
            Protocol name (e.g., "keri", "s3", "git")
        """
        ...

    @abstractmethod
    def get_edge(self, content: Any, edge_name: str) -> Optional[EdgeRef]:
        """
        Extract a named edge from protocol-specific content.

        Args:
            content: Source content (credential dict, S3 metadata, etc.)
            edge_name: Edge key to extract (e.g., "acdc", "iss", "delegator")

        Returns:
            EdgeRef with target SAID and metadata, or None if edge not found
        """
        ...

    @abstractmethod
    def list_edges(self, content: Any) -> list[str]:
        """
        List all available edge names in content.

        Args:
            content: Source content to inspect

        Returns:
            List of edge keys present in the content
        """
        ...

    def detect_payload_type(self, edge_message: dict) -> Optional[str]:
        """
        Detect CESR payload type from an edge message.

        Default implementation checks for "t" field (KERI messages).
        Override for protocol-specific detection.

        Args:
            edge_message: The nested message within an edge

        Returns:
            Payload type string, or None if not detectable
        """
        return edge_message.get("t") if isinstance(edge_message, dict) else None

    def can_resolve(self, content: Any) -> bool:
        """
        Check if this resolver can handle the given content.

        Default implementation returns True. Override for protocols that
        need to inspect content before claiming it.

        Args:
            content: Content to check

        Returns:
            True if this resolver can process the content
        """
        return True
