# -*- encoding: utf-8 -*-
"""
KGQL Key State Resolver - Resolves AID key states for temporal queries.

When a query includes `AT KEYSTATE(aid='...', seq=N)`, the resolver
captures the key state at that point in the KEL. This snapshot is then
used to verify credentials against the historical key state rather than
the current one.

Key insight: The KEL is an append-only log, so key state at seq=N is
immutable once established. This means snapshots can be cached by (AID, seq).
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class KeyStateSnapshot:
    """
    Captured key state at a specific point in the KEL.

    This is the temporal anchor for AT KEYSTATE queries. All verification
    during the query uses this snapshot instead of the current key state.

    Attributes:
        aid: The AID whose key state was captured
        seq: Sequence number in the KEL
        keys: Public keys at this key state (signing keys)
        ndigs: Next key digests (pre-rotation commitment)
        tholder: Signing threshold
        delpre: Delegator prefix (if delegated AID)
        anchors: Anchored seals at this event
        raw: Raw kever/key state data for passthrough
    """
    aid: str
    seq: int
    keys: list[str] = field(default_factory=list)
    ndigs: list[str] = field(default_factory=list)
    tholder: Optional[str] = None
    delpre: Optional[str] = None
    anchors: list[dict] = field(default_factory=list)
    raw: Optional[Any] = None

    @property
    def is_delegated(self) -> bool:
        """Whether this AID is delegated at this key state."""
        return self.delpre is not None and self.delpre != ""

    @property
    def cache_key(self) -> tuple[str, int]:
        """Cache key for this snapshot (immutable once established)."""
        return (self.aid, self.seq)

    def to_dict(self) -> dict:
        """Serialize to dict for query results."""
        result = {
            "aid": self.aid,
            "seq": self.seq,
            "keys": self.keys,
            "tholder": self.tholder,
        }
        if self.delpre:
            result["delpre"] = self.delpre
        if self.ndigs:
            result["ndigs"] = self.ndigs
        return result

    @classmethod
    def from_kever(cls, kever: Any, seq: Optional[int] = None) -> "KeyStateSnapshot":
        """
        Create a snapshot from a keripy Kever object.

        Args:
            kever: keripy Kever instance
            seq: Sequence number (defaults to kever.sn)

        Returns:
            KeyStateSnapshot capturing the key state
        """
        return cls(
            aid=kever.prefixer.qb64 if hasattr(kever, 'prefixer') else str(kever),
            seq=seq if seq is not None else getattr(kever, 'sn', 0),
            keys=[k.qb64 for k in kever.verfers] if hasattr(kever, 'verfers') else [],
            ndigs=[d.qb64 for d in kever.ndigers] if hasattr(kever, 'ndigers') else [],
            tholder=str(kever.tholder) if hasattr(kever, 'tholder') else None,
            delpre=kever.delpre if hasattr(kever, 'delpre') else None,
            raw=kever,
        )


class KeyStateResolver:
    """
    Resolves AID key states at specific sequence numbers.

    Wraps keripy's Kever/KEL access with caching and temporal support.
    Since key state at seq=N is immutable (KEL is append-only), snapshots
    are cached by (AID, seq) and never go stale.

    Usage:
        resolver = KeyStateResolver(hby=habery)
        snapshot = resolver.resolve("EAID...", seq=3)
        if snapshot:
            print(f"Keys at seq 3: {snapshot.keys}")
    """

    def __init__(self, kever_getter: Optional[Callable] = None):
        """
        Initialize with an optional kever getter function.

        Args:
            kever_getter: Callable(aid, seq) -> kever or None.
                Typically wraps hby.kevers.get() with KEL walking.
        """
        self._get_kever = kever_getter
        self._cache: dict[tuple[str, int], KeyStateSnapshot] = {}
        self._current: dict[str, KeyStateSnapshot] = {}  # latest known per AID

    def resolve(
        self, aid: str, seq: Optional[int] = None
    ) -> Optional[KeyStateSnapshot]:
        """
        Resolve key state for an AID at an optional sequence number.

        Args:
            aid: The AID to resolve
            seq: Optional sequence number. If None, returns current state.

        Returns:
            KeyStateSnapshot or None if not found
        """
        # Check cache for specific seq
        if seq is not None:
            cache_key = (aid, seq)
            if cache_key in self._cache:
                return self._cache[cache_key]
        else:
            # seq=None means current state — check current cache
            if aid in self._current:
                return self._current[aid]

        if self._get_kever is None:
            return None

        kever = self._get_kever(aid, seq)
        if kever is None:
            return None

        actual_seq = seq if seq is not None else getattr(kever, 'sn', 0)
        snapshot = KeyStateSnapshot.from_kever(kever, seq=actual_seq)

        # Cache by (aid, seq) - immutable because KEL is append-only
        self._cache[(aid, actual_seq)] = snapshot
        # Update current-state tracker
        existing = self._current.get(aid)
        if existing is None or actual_seq >= existing.seq:
            self._current[aid] = snapshot
        return snapshot

    def resolve_current(self, aid: str) -> Optional[KeyStateSnapshot]:
        """
        Resolve the current (latest) key state for an AID.

        Args:
            aid: The AID to resolve

        Returns:
            KeyStateSnapshot for the current key state
        """
        return self.resolve(aid, seq=None)

    def register(self, snapshot: KeyStateSnapshot) -> None:
        """
        Manually register a key state snapshot (for testing).

        Also updates the current-state cache if this is the highest seq
        seen for this AID.

        Args:
            snapshot: Snapshot to cache
        """
        self._cache[snapshot.cache_key] = snapshot
        # Track latest known state per AID
        existing = self._current.get(snapshot.aid)
        if existing is None or snapshot.seq >= existing.seq:
            self._current[snapshot.aid] = snapshot

    def is_cached(self, aid: str, seq: int) -> bool:
        """Check if a specific key state is cached."""
        return (aid, seq) in self._cache

    def clear_cache(self) -> None:
        """Clear the snapshot cache."""
        self._cache.clear()
        self._current.clear()
