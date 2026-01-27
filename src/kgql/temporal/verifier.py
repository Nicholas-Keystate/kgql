# -*- encoding: utf-8 -*-
"""
KGQL Temporal Verifier - Verifies credentials against historical key states.

When executing an AT KEYSTATE query, credentials must be verified against
the key state at the specified sequence number, not the current key state.

This is critical for temporal queries: "Was this credential valid when
the issuer's key state was at seq=3?"
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from kgql.temporal.resolver import KeyStateResolver, KeyStateSnapshot


@dataclass
class TemporalCheckResult:
    """
    Result of a temporal verification check.

    Attributes:
        valid: Whether the credential was valid at the key state
        snapshot: The key state used for verification
        credential_said: SAID of the credential checked
        message: Human-readable explanation
    """
    valid: bool
    snapshot: Optional[KeyStateSnapshot] = None
    credential_said: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        result = {
            "valid": self.valid,
            "credential_said": self.credential_said,
            "message": self.message,
        }
        if self.snapshot:
            result["keystate"] = self.snapshot.to_dict()
        return result


class TemporalVerifier:
    """
    Verifies credentials against historical key states.

    Wraps the key state resolver with credential verification logic.
    During AT KEYSTATE queries, all verification uses the snapshot
    rather than current key state.

    Usage:
        resolver = KeyStateResolver(kever_getter=...)
        verifier = TemporalVerifier(resolver)

        result = verifier.verify_at_keystate(
            credential_said="ESaid...",
            issuer_aid="EAID...",
            seq=3,
            verify_fn=my_verify_function,
        )
    """

    def __init__(self, keystate_resolver: KeyStateResolver):
        """
        Initialize with a key state resolver.

        Args:
            keystate_resolver: Resolver for fetching key state snapshots
        """
        self._resolver = keystate_resolver

    @property
    def resolver(self) -> KeyStateResolver:
        return self._resolver

    def verify_at_keystate(
        self,
        credential_said: str,
        issuer_aid: str,
        seq: Optional[int] = None,
        verify_fn: Optional[Any] = None,
    ) -> TemporalCheckResult:
        """
        Verify a credential against a specific key state.

        Args:
            credential_said: SAID of the credential to verify
            issuer_aid: AID of the credential issuer
            seq: Sequence number for historical state (None = current)
            verify_fn: Optional callable(said, keys) -> bool for actual
                signature verification. If None, only checks key state exists.

        Returns:
            TemporalCheckResult with verification outcome
        """
        # Resolve the key state
        snapshot = self._resolver.resolve(issuer_aid, seq=seq)
        if snapshot is None:
            return TemporalCheckResult(
                valid=False,
                credential_said=credential_said,
                message=(
                    f"Key state not found for {issuer_aid}"
                    + (f" at seq={seq}" if seq is not None else "")
                ),
            )

        # If no verify function, just confirm key state exists
        if verify_fn is None:
            return TemporalCheckResult(
                valid=True,
                snapshot=snapshot,
                credential_said=credential_said,
                message=(
                    f"Key state resolved for {issuer_aid} at seq={snapshot.seq}"
                ),
            )

        # Verify using the historical keys
        try:
            is_valid = verify_fn(credential_said, snapshot.keys)
        except Exception as e:
            return TemporalCheckResult(
                valid=False,
                snapshot=snapshot,
                credential_said=credential_said,
                message=f"Verification error: {e}",
            )

        return TemporalCheckResult(
            valid=is_valid,
            snapshot=snapshot,
            credential_said=credential_said,
            message=(
                f"Credential {'valid' if is_valid else 'invalid'} "
                f"at {issuer_aid} seq={snapshot.seq}"
            ),
        )

    def check_edge_at_keystate(
        self,
        edge_said: str,
        issuer_aid: str,
        subject_aid: str,
        seq: Optional[int] = None,
    ) -> TemporalCheckResult:
        """
        Check if an edge was valid at a specific key state.

        Verifies both issuer and subject key states existed at the
        specified sequence number.

        Args:
            edge_said: SAID of the edge credential
            issuer_aid: Issuer AID
            subject_aid: Subject AID
            seq: Sequence number for temporal scoping

        Returns:
            TemporalCheckResult
        """
        # Check issuer key state
        issuer_snapshot = self._resolver.resolve(issuer_aid, seq=seq)
        if issuer_snapshot is None:
            return TemporalCheckResult(
                valid=False,
                credential_said=edge_said,
                message=f"Issuer key state not found for {issuer_aid} at seq={seq}",
            )

        # Check subject key state (at current, since subject seq may differ)
        subject_snapshot = self._resolver.resolve(subject_aid)
        if subject_snapshot is None:
            return TemporalCheckResult(
                valid=False,
                credential_said=edge_said,
                message=f"Subject key state not found for {subject_aid}",
            )

        return TemporalCheckResult(
            valid=True,
            snapshot=issuer_snapshot,
            credential_said=edge_said,
            message=(
                f"Edge valid at issuer seq={issuer_snapshot.seq}, "
                f"subject seq={subject_snapshot.seq}"
            ),
        )
