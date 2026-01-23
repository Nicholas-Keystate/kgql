# -*- encoding: utf-8 -*-
"""
KGQL ACDC Edge Resolver - Edge resolution for KERI/ACDC credentials.

This resolver handles the standard ACDC credential edge structure as defined
in keripy. ACDC edges are stored in the "e" field as nested messages keyed
by their relationship type.

ACDC Edge Structure (from keripy):
    credential = {
        "v": "ACDC10JSON...",
        "d": "ESAID...",           # Credential SAID
        "i": "EISSUER...",         # Issuer AID
        "s": "ESCHEMA...",         # Schema SAID
        "a": {...},                # Attributes (subject)
        "e": {                     # EDGES - nested messages by type
            "acdc": {              # Referenced credential
                "v": "ACDC10JSON...",
                "d": "ETARGET...", # Target SAID in "d" field
                ...
            },
            "iss": {               # Issuance event
                "v": "KERI10JSON...",
                "t": "iss",        # Message type in "t" field
                "d": "ESAID...",
                ...
            },
        },
        "r": {...}                 # Rules
    }

References:
    - keripy/src/keri/vc/proving.py (credential() function)
    - keripy/tests/vc/test_protocoling.py (IPEX exchange tests)
"""

from typing import Any, Optional

from kgql.wrappers.edge_resolver import EdgeResolver, EdgeRef


# Known KERI message types (from keripy)
KERI_MESSAGE_TYPES = {
    "icp",  # Inception
    "rot",  # Rotation
    "ixn",  # Interaction
    "dip",  # Delegated inception
    "drt",  # Delegated rotation
    "rct",  # Receipt
    "qry",  # Query
    "rpy",  # Reply
    "exn",  # Exchange
    "vcp",  # Registry inception
    "vrt",  # Registry rotation
    "iss",  # Credential issuance
    "rev",  # Credential revocation
    "bis",  # Backed issuance
    "brv",  # Backed revocation
}


class ACDCEdgeResolver(EdgeResolver):
    """
    Edge resolver for ACDC credentials.

    Extracts edges from the "e" field of ACDC credentials. Each edge key
    maps to a nested message containing a SAID in its "d" field.

    Common edge types:
        - "acdc": Chained credential reference
        - "iss": Issuance event
        - "anc": Anchor event
        - "vcp": Registry inception
        - "ixn": Interaction event
    """

    @property
    def protocol(self) -> str:
        """Return protocol identifier."""
        return "keri"

    def get_edge(self, credential: Any, edge_name: str) -> Optional[EdgeRef]:
        """
        Extract an edge by name from an ACDC credential.

        Args:
            credential: ACDC credential dict
            edge_name: Edge key (e.g., "acdc", "iss", "vcp", "delegator")

        Returns:
            EdgeRef with target SAID, or None if edge not found
        """
        if not isinstance(credential, dict):
            return None

        edges = credential.get("e", {})

        # Handle empty or non-dict edges
        if not edges or not isinstance(edges, dict):
            return None

        edge_message = edges.get(edge_name)
        if not edge_message or not isinstance(edge_message, dict):
            return None

        # Target SAID is in "d" field of nested message
        target_said = edge_message.get("d")
        if not target_said:
            return None

        # Detect payload type from message
        payload_type = self.detect_payload_type(edge_message)

        # Extract useful metadata
        metadata = {}
        if "i" in edge_message:
            metadata["issuer"] = edge_message["i"]
        if "s" in edge_message:
            # Could be schema SAID or sequence number depending on message type
            metadata["s"] = edge_message["s"]
        if "v" in edge_message:
            metadata["version"] = edge_message["v"]
        if "ri" in edge_message:
            metadata["registry"] = edge_message["ri"]

        return EdgeRef(
            target_said=target_said,
            edge_type=edge_name,
            payload_type=payload_type,
            source_protocol="keri",
            metadata=metadata,
            raw_message=edge_message,
        )

    def list_edges(self, credential: Any) -> list[str]:
        """
        List all edge keys in a credential.

        Args:
            credential: ACDC credential dict

        Returns:
            List of edge keys (e.g., ["acdc", "iss"])
        """
        if not isinstance(credential, dict):
            return []

        edges = credential.get("e", {})
        if isinstance(edges, dict):
            return list(edges.keys())
        return []

    def detect_payload_type(self, edge_message: dict) -> Optional[str]:
        """
        Detect CESR/KERI payload type from edge message.

        KERI messages have a "t" field with the message type.
        ACDC credentials have a "v" field starting with "ACDC".

        Args:
            edge_message: The nested message within an edge

        Returns:
            Message type string, or None if not detectable
        """
        if not isinstance(edge_message, dict):
            return None

        # Check for KERI message type field
        msg_type = edge_message.get("t")
        if msg_type and msg_type in KERI_MESSAGE_TYPES:
            return msg_type

        # Check for ACDC version string
        version = edge_message.get("v", "")
        if isinstance(version, str) and version.startswith("ACDC"):
            return "acdc"

        # Check for KERI version string
        if isinstance(version, str) and version.startswith("KERI"):
            # Try to infer type from structure
            if "t" in edge_message:
                return edge_message["t"]

        return None

    def can_resolve(self, content: Any) -> bool:
        """
        Check if content looks like an ACDC credential.

        Args:
            content: Content to check

        Returns:
            True if content has ACDC structure
        """
        if not isinstance(content, dict):
            return False

        # ACDC credentials have version string starting with "ACDC"
        version = content.get("v", "")
        if isinstance(version, str) and version.startswith("ACDC"):
            return True

        # Also accept if it has the key ACDC fields
        return all(k in content for k in ("d", "i", "s"))
