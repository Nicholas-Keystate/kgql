# -*- encoding: utf-8 -*-
"""
KGQL Governance Schema - Data model for governance framework credentials.

A governance framework is itself an ACDC credential in the graph it governs.
This module defines the Python-side representation that KGQL uses after
resolving and parsing a framework credential.

Key insight from the Four Unifications:
1. Rules ARE Credentials - framework is an ACDC
2. Enforcement IS Verification - KGQL constraint check = cryptographic verify
3. Authority IS Delegation - who can change rules is defined by delegation chain
4. Evolution IS Supersession - new version has 'supersedes' edge to prior

ACDC Schema Structure:
    {
        "v": "ACDC10JSON...",
        "d": "<framework SAID>",
        "i": "<steward AID>",
        "s": "<GovernanceFramework schema SAID>",
        "a": {
            "d": "<attributes SAID>",
            "name": "vLEI Governance Framework",
            "version": "1.0.0",
            "rules": [...],
            "credential_matrix": [...],
            "authorities": {...}
        },
        "e": {
            "supersedes": {           # Edge to prior version (if any)
                "d": "<prior framework SAID>",
                ...
            }
        },
        "r": {                        # Ricardian contract
            "d": "<rules SAID>",
            "human_readable": "...",
            "binding_hash": "..."
        }
    }
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from kgql.parser.ast import EdgeOperator


class RuleEnforcement(Enum):
    """How strictly a rule is enforced during query evaluation."""
    STRICT = "strict"       # Query fails if rule is violated
    ADVISORY = "advisory"   # Warning emitted but query proceeds


@dataclass
class ConstraintRule:
    """
    A single governance rule that constrains edge traversal.

    Rules map to KGQL edge operator requirements. During query execution
    with WITHIN FRAMEWORK, each edge traversal is checked against
    applicable rules.

    Attributes:
        name: Human-readable rule identifier (slug form)
        description: What this rule enforces
        applies_to: Node type or edge type this rule constrains
            e.g., "Credential", "QVI->LE", "iss"
        required_operator: Minimum edge operator strength required
            I2I > DI2I > NI2I (partial order from constraint algebra)
        field_constraints: Optional field-level constraints
            e.g., {"jurisdiction": "$issuer.jurisdiction == $subject.country"}
        max_delegation_depth: Maximum delegation chain length (None = unlimited)
        enforcement: Strict (fail) or advisory (warn)
    """
    name: str
    description: str = ""
    applies_to: str = ""
    required_operator: EdgeOperator = EdgeOperator.ANY
    field_constraints: dict[str, str] = field(default_factory=dict)
    max_delegation_depth: Optional[int] = None
    enforcement: RuleEnforcement = RuleEnforcement.STRICT

    def to_dict(self) -> dict:
        """Serialize to dict (matches ACDC attribute format)."""
        result = {
            "name": self.name,
            "applies_to": self.applies_to,
            "required_operator": self.required_operator.value,
            "enforcement": self.enforcement.value,
        }
        if self.description:
            result["description"] = self.description
        if self.field_constraints:
            result["field_constraints"] = self.field_constraints
        if self.max_delegation_depth is not None:
            result["max_delegation_depth"] = self.max_delegation_depth
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ConstraintRule":
        """Deserialize from ACDC attribute data."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            applies_to=data.get("applies_to", ""),
            required_operator=EdgeOperator(
                data.get("required_operator", "ANY")
            ),
            field_constraints=data.get("field_constraints", {}),
            max_delegation_depth=data.get("max_delegation_depth"),
            enforcement=RuleEnforcement(
                data.get("enforcement", "strict")
            ),
        )


@dataclass
class CredentialMatrixEntry:
    """
    One cell in the credential authorization matrix.

    Maps (action, role) -> required edge operator.
    Example: ("issue", "QVI") -> I2I means QVIs must use I2I edges to issue.

    Attributes:
        action: The operation (e.g., "issue", "revoke", "query")
        role: The node type performing the action (e.g., "QVI", "LE", "Agent")
        required_operator: Minimum operator for this action+role
        allowed: Whether this action is permitted at all
    """
    action: str
    role: str
    required_operator: EdgeOperator = EdgeOperator.ANY
    allowed: bool = True

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "role": self.role,
            "required_operator": self.required_operator.value,
            "allowed": self.allowed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CredentialMatrixEntry":
        return cls(
            action=data.get("action", ""),
            role=data.get("role", ""),
            required_operator=EdgeOperator(
                data.get("required_operator", "ANY")
            ),
            allowed=data.get("allowed", True),
        )


@dataclass
class FrameworkVersion:
    """
    Version metadata for a governance framework.

    Tracks the supersession chain: each version references its predecessor
    via a 'supersedes' edge in the ACDC "e" field.
    """
    said: str                              # This framework's SAID
    version: str                           # Semantic version string
    supersedes_said: Optional[str] = None  # Prior version SAID (from "e" field)
    steward_aid: Optional[str] = None      # AID authorized to issue next version


@dataclass
class GovernanceFramework:
    """
    Parsed governance framework from an ACDC credential.

    This is the Python-side representation used during KGQL query execution.
    Created by FrameworkResolver.resolve() from a raw ACDC credential dict.

    Attributes:
        said: Framework credential SAID (content-addressable, immutable)
        name: Human-readable framework name
        version_info: Version and supersession chain metadata
        steward: AID of the framework steward (issuer of the framework credential)
        rules: Constraint rules that apply during query evaluation
        credential_matrix: Authorization matrix entries
        authorities: Dict mapping role names to authorized AID prefixes
        raw: Original ACDC credential dict (for passthrough to keripy)
    """
    said: str
    name: str = ""
    version_info: Optional[FrameworkVersion] = None
    steward: str = ""
    rules: list[ConstraintRule] = field(default_factory=list)
    credential_matrix: list[CredentialMatrixEntry] = field(default_factory=list)
    authorities: dict[str, list[str]] = field(default_factory=dict)
    raw: Optional[dict] = None

    @property
    def version(self) -> str:
        """Semantic version string."""
        return self.version_info.version if self.version_info else "0.0.0"

    @property
    def supersedes(self) -> Optional[str]:
        """SAID of the prior framework version, if any."""
        return self.version_info.supersedes_said if self.version_info else None

    def get_rules_for(self, applies_to: str) -> list[ConstraintRule]:
        """Get all rules that apply to a given node/edge type."""
        return [r for r in self.rules if r.applies_to == applies_to]

    def get_matrix_entry(
        self, action: str, role: str
    ) -> Optional[CredentialMatrixEntry]:
        """Look up the credential matrix for (action, role)."""
        for entry in self.credential_matrix:
            if entry.action == action and entry.role == role:
                return entry
        return None

    def is_action_allowed(self, action: str, role: str) -> bool:
        """Check if an action is allowed for a role per the matrix."""
        entry = self.get_matrix_entry(action, role)
        if entry is None:
            # No explicit entry = not governed = allowed
            return True
        return entry.allowed

    def required_operator_for(
        self, action: str, role: str
    ) -> EdgeOperator:
        """Get the required edge operator for an action+role pair."""
        entry = self.get_matrix_entry(action, role)
        if entry is None:
            return EdgeOperator.ANY
        return entry.required_operator

    def to_dict(self) -> dict:
        """Serialize to dict format (matches ACDC 'a' field structure)."""
        result: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "rules": [r.to_dict() for r in self.rules],
        }
        if self.credential_matrix:
            result["credential_matrix"] = [
                e.to_dict() for e in self.credential_matrix
            ]
        if self.authorities:
            result["authorities"] = self.authorities
        return result

    @classmethod
    def from_credential(cls, credential: dict) -> "GovernanceFramework":
        """
        Parse a GovernanceFramework from a raw ACDC credential dict.

        Expects standard ACDC structure with governance-specific attributes
        in the 'a' (attributes) field.

        Args:
            credential: Raw ACDC credential dict with 'v', 'd', 'i', 'a', 'e' fields

        Returns:
            GovernanceFramework instance

        Raises:
            ValueError: If credential is missing required fields
        """
        if not isinstance(credential, dict):
            raise ValueError("Credential must be a dict")

        said = credential.get("d")
        if not said:
            raise ValueError("Credential missing 'd' (SAID) field")

        steward = credential.get("i", "")
        attrs = credential.get("a", {})
        if not isinstance(attrs, dict):
            attrs = {}

        # Parse rules
        rules = []
        for rule_data in attrs.get("rules", []):
            if isinstance(rule_data, dict):
                rules.append(ConstraintRule.from_dict(rule_data))

        # Parse credential matrix
        matrix = []
        for entry_data in attrs.get("credential_matrix", []):
            if isinstance(entry_data, dict):
                matrix.append(CredentialMatrixEntry.from_dict(entry_data))

        # Parse authorities
        authorities = attrs.get("authorities", {})
        if not isinstance(authorities, dict):
            authorities = {}

        # Parse supersession from edges
        edges = credential.get("e", {})
        supersedes_said = None
        if isinstance(edges, dict):
            supersedes_edge = edges.get("supersedes", {})
            if isinstance(supersedes_edge, dict):
                supersedes_said = supersedes_edge.get("d")

        version_info = FrameworkVersion(
            said=said,
            version=attrs.get("version", "1.0.0"),
            supersedes_said=supersedes_said,
            steward_aid=steward,
        )

        return cls(
            said=said,
            name=attrs.get("name", ""),
            version_info=version_info,
            steward=steward,
            rules=rules,
            credential_matrix=matrix,
            authorities=authorities,
            raw=credential,
        )
