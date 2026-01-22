"""
RegerWrapper - Thin wrapper for Reger credential queries.

This wrapper provides a consistent interface for credential queries
WITHOUT duplicating any existing Reger functionality.

All methods delegate directly to existing Reger methods:
    - by_issuer() -> reger.issus.getIter()
    - by_subject() -> reger.subjs.getIter()
    - by_schema() -> reger.schms.getIter()
    - resolve() -> reger.creds.get() + deserialization
    - traverse_sources() -> reger.sources()
"""

from dataclasses import dataclass
from typing import Any, Iterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from keri.vdr.viring import Reger
    from keri.db.basing import Baser


@dataclass
class CredentialResult:
    """
    Wrapper for credential query results.

    Provides a consistent interface for KGQL query results
    without adding new data structures.
    """
    said: str
    issuer: Optional[str] = None
    subject: Optional[str] = None
    schema: Optional[str] = None
    raw: Optional[Any] = None  # The actual Creder or raw credential

    @classmethod
    def from_creder(cls, creder: Any) -> "CredentialResult":
        """Create from a keripy Creder instance."""
        return cls(
            said=creder.said,
            issuer=creder.issuer,
            subject=creder.attrib.get("i") if creder.attrib else None,
            schema=creder.schema,
            raw=creder,
        )


class RegerWrapper:
    """
    Thin wrapper for Reger queries.

    This wrapper does NOT duplicate Reger functionality - it provides
    a consistent interface that delegates all work to existing methods.

    Usage:
        wrapper = RegerWrapper(reger)
        creds = wrapper.by_issuer("EAID...")
        cred = wrapper.resolve("ESAID...")
    """

    def __init__(self, reger: "Reger"):
        """
        Initialize with a keripy Reger instance.

        Args:
            reger: The keripy Reger instance to wrap
        """
        self._reger = reger

    @property
    def reger(self) -> "Reger":
        """Direct access to underlying Reger for advanced queries."""
        return self._reger

    def by_issuer(self, aid: str) -> Iterator[str]:
        """
        Get credential SAIDs by issuer.

        Wraps reger.issus.getIter().

        Args:
            aid: The issuer AID to search for

        Yields:
            Credential SAIDs issued by the AID
        """
        for saider in self._reger.issus.getIter(keys=aid):
            yield saider.qb64 if hasattr(saider, 'qb64') else str(saider)

    def by_subject(self, aid: str) -> Iterator[str]:
        """
        Get credential SAIDs by subject.

        Wraps reger.subjs.getIter().

        Args:
            aid: The subject AID to search for

        Yields:
            Credential SAIDs with the AID as subject
        """
        for saider in self._reger.subjs.getIter(keys=aid):
            yield saider.qb64 if hasattr(saider, 'qb64') else str(saider)

    def by_schema(self, schema_said: str) -> Iterator[str]:
        """
        Get credential SAIDs by schema.

        Wraps reger.schms.getIter().

        Args:
            schema_said: The schema SAID to search for

        Yields:
            Credential SAIDs with the specified schema
        """
        for saider in self._reger.schms.getIter(keys=schema_said):
            yield saider.qb64 if hasattr(saider, 'qb64') else str(saider)

    def resolve(self, said: str) -> Optional[CredentialResult]:
        """
        Resolve a credential by SAID.

        Wraps reger.creds.get() and returns credential data.

        Args:
            said: The credential SAID to resolve

        Returns:
            CredentialResult or None if not found
        """
        try:
            # Get credential from Reger
            # Returns SerderACDC directly when stored via creds.put()
            raw = self._reger.creds.get(keys=said)
            if raw is None:
                return None

            # Handle different return types from creds.get()
            from keri.core.serdering import SerderACDC
            if isinstance(raw, SerderACDC):
                # Already a SerderACDC, use directly
                creder = raw
            elif isinstance(raw, bytes):
                # Raw bytes, deserialize
                creder = SerderACDC(raw=raw)
            elif hasattr(raw, 'raw'):
                # Has raw attribute, deserialize from that
                creder = SerderACDC(raw=raw.raw)
            else:
                # Unknown type, try to use as-is
                creder = raw

            return CredentialResult.from_creder(creder)

        except Exception as e:
            # Log exception for debugging (silent failures are bad)
            import logging
            logging.getLogger(__name__).debug(f"Failed to resolve {said[:16]}...: {e}")
            return None

    def traverse_sources(self, db: "Baser", said: str) -> Iterator[tuple[Any, bytes]]:
        """
        Traverse credential chain using sources().

        Wraps reger.sources() for recursive chain traversal.

        Args:
            db: The keripy database instance
            said: The starting credential SAID

        Yields:
            Tuples of (Creder, proof_bytes) for each source in the chain
        """
        # First resolve the starting credential
        cred_result = self.resolve(said)
        if not cred_result or not cred_result.raw:
            return

        # Use existing sources() method
        for creder, proof in self._reger.sources(db, cred_result.raw):
            yield (creder, proof)

    def clone_cred(self, said: str) -> Optional[Any]:
        """
        Clone a credential by SAID.

        Wraps reger.cloneCred() if available, otherwise uses creds.get().

        Args:
            said: The credential SAID to clone

        Returns:
            The cloned credential or None
        """
        if hasattr(self._reger, 'cloneCred'):
            return self._reger.cloneCred(said)

        # Fallback to resolve
        result = self.resolve(said)
        return result.raw if result else None

    def count_by_issuer(self, aid: str) -> int:
        """
        Count credentials by issuer.

        Args:
            aid: The issuer AID

        Returns:
            Count of credentials issued by the AID
        """
        return sum(1 for _ in self.by_issuer(aid))

    def count_by_subject(self, aid: str) -> int:
        """
        Count credentials by subject.

        Args:
            aid: The subject AID

        Returns:
            Count of credentials with the AID as subject
        """
        return sum(1 for _ in self.by_subject(aid))

    def count_by_schema(self, schema_said: str) -> int:
        """
        Count credentials by schema.

        Args:
            schema_said: The schema SAID

        Returns:
            Count of credentials with the specified schema
        """
        return sum(1 for _ in self.by_schema(schema_said))
