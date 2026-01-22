"""
VerifierWrapper - Thin wrapper for Verifier verification operations.

This wrapper provides a consistent interface for credential verification
WITHOUT duplicating any existing Verifier functionality.

All methods delegate directly to existing Verifier methods:
    - verify_chain() -> verifier.verifyChain()
    - check_delegation() -> walks kever.delpre chain
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from keri.vdr.verifying import Verifier
    from keri.core.eventing import Kever


class VerificationStatus(Enum):
    """Status of a verification operation."""
    VERIFIED = "verified"
    REVOKED = "revoked"
    NOT_FOUND = "not_found"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_CHAIN = "invalid_chain"
    PENDING = "pending"


@dataclass
class VerificationResult:
    """
    Result of a credential verification.

    Wraps the keripy VcStateRecord with additional context.
    """
    status: VerificationStatus
    said: str
    issuer: Optional[str] = None
    sequence: Optional[int] = None
    keystate_said: Optional[str] = None
    raw_result: Optional[Any] = None  # The actual VcStateRecord

    @property
    def is_valid(self) -> bool:
        """Check if the credential is valid (verified and not revoked)."""
        return self.status == VerificationStatus.VERIFIED


@dataclass
class DelegationCheckResult:
    """Result of checking if an AID is in a delegation chain."""
    is_delegated: bool
    delegation_path: list[str]  # AIDs in the path from root to target
    delegator: Optional[str] = None


class VerifierWrapper:
    """
    Thin wrapper for Verifier operations.

    This wrapper does NOT duplicate Verifier functionality - it provides
    a consistent interface that delegates all work to existing methods.

    Usage:
        wrapper = VerifierWrapper(verifier, hby)
        result = wrapper.verify_chain("ESAID...")
        is_delegated = wrapper.check_delegation("EAID...", "ERoot...")
    """

    def __init__(self, verifier: "Verifier", hby: Any = None):
        """
        Initialize with keripy Verifier and Habery instances.

        Args:
            verifier: The keripy Verifier instance
            hby: The keripy Habery instance (for key state lookups)
        """
        self._verifier = verifier
        self._hby = hby

    @property
    def verifier(self) -> "Verifier":
        """Direct access to underlying Verifier for advanced operations."""
        return self._verifier

    def verify_chain(
        self,
        said: str,
        issuer: Optional[str] = None,
        operator: Optional[str] = None
    ) -> VerificationResult:
        """
        Verify a credential chain.

        Wraps verifier.verifyChain().

        Args:
            said: The credential SAID to verify
            issuer: Optional issuer AID for additional validation
            operator: Optional edge operator constraint (I2I, DI2I, NI2I)

        Returns:
            VerificationResult with status and details
        """
        try:
            # Call existing verifyChain method
            result = self._verifier.verifyChain(
                nodeSaid=said,
                op=operator,
                issuer=issuer
            )

            if result is None:
                return VerificationResult(
                    status=VerificationStatus.NOT_FOUND,
                    said=said,
                )

            # Check if revoked
            if hasattr(result, 'revoked') and result.revoked:
                return VerificationResult(
                    status=VerificationStatus.REVOKED,
                    said=said,
                    issuer=getattr(result, 'issuer', None),
                    sequence=getattr(result, 'sn', None),
                    raw_result=result,
                )

            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                said=said,
                issuer=getattr(result, 'issuer', None),
                sequence=getattr(result, 'sn', None),
                keystate_said=getattr(result, 'ksaid', None),
                raw_result=result,
            )

        except Exception as e:
            # Determine specific error type
            error_msg = str(e).lower()
            if "signature" in error_msg:
                status = VerificationStatus.INVALID_SIGNATURE
            elif "chain" in error_msg or "delegation" in error_msg:
                status = VerificationStatus.INVALID_CHAIN
            else:
                status = VerificationStatus.NOT_FOUND

            return VerificationResult(
                status=status,
                said=said,
            )

    def check_delegation(
        self,
        child_aid: str,
        parent_aid: str
    ) -> DelegationCheckResult:
        """
        Check if child_aid is in the delegation chain from parent_aid.

        Walks the kever.delpre chain to find delegation path.

        Args:
            child_aid: The potential delegate AID
            parent_aid: The potential delegator AID

        Returns:
            DelegationCheckResult with path if delegated
        """
        if not self._hby:
            return DelegationCheckResult(
                is_delegated=False,
                delegation_path=[],
            )

        path = []
        current = child_aid

        while current and current != parent_aid:
            path.append(current)

            # Get the kever for current AID
            kever = self._hby.kevers.get(current)
            if not kever or not kever.delpre:
                # No delegator - not in chain
                return DelegationCheckResult(
                    is_delegated=False,
                    delegation_path=[],
                )

            current = kever.delpre

        if current == parent_aid:
            path.append(parent_aid)
            return DelegationCheckResult(
                is_delegated=True,
                delegation_path=list(reversed(path)),
                delegator=parent_aid,
            )

        return DelegationCheckResult(
            is_delegated=False,
            delegation_path=[],
        )

    def get_key_state(self, aid: str, seq: Optional[int] = None) -> Optional[Any]:
        """
        Get key state for an AID.

        Args:
            aid: The AID to get key state for
            seq: Optional sequence number for historical state

        Returns:
            The Kever key state or None
        """
        if not self._hby:
            return None

        kever = self._hby.kevers.get(aid)
        if not kever:
            return None

        # If specific sequence requested, check if it matches
        if seq is not None and kever.sn != seq:
            # Would need to walk KEL for historical state
            # This is a limitation - full historical lookup not implemented
            return None

        return kever

    def verify_i2i(self, edge_said: str, parent_said: str) -> bool:
        """
        Verify I2I constraint: edge issuer == parent subject.

        Args:
            edge_said: The edge credential SAID
            parent_said: The parent credential SAID

        Returns:
            True if I2I constraint is satisfied
        """
        result = self.verify_chain(edge_said, operator="I2I")
        return result.is_valid

    def verify_di2i(
        self,
        edge_said: str,
        parent_said: str,
        root_aid: str
    ) -> bool:
        """
        Verify DI2I constraint: edge issuer in delegation chain from parent subject.

        Args:
            edge_said: The edge credential SAID
            parent_said: The parent credential SAID
            root_aid: The root AID for delegation chain

        Returns:
            True if DI2I constraint is satisfied
        """
        result = self.verify_chain(edge_said, operator="DI2I")
        if not result.is_valid:
            return False

        # Check delegation chain
        if result.issuer:
            delegation = self.check_delegation(result.issuer, root_aid)
            return delegation.is_delegated

        return False
