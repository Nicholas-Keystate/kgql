# -*- encoding: utf-8 -*-
"""
KGQL Framework Resolver - Resolves framework SAIDs to GovernanceFramework objects.

In KGQL queries, `WITHIN FRAMEWORK 'EFrameworkSAID...'` references a governance
framework credential by SAID. This module resolves that SAID to a parsed
GovernanceFramework that the ConstraintChecker can evaluate.

Resolution follows the same principle as credential resolution:
"Resolution IS Verification" - if the SAID resolves, integrity is guaranteed.

Supersession Chain (Phase 4.4):
Each framework version is an ACDC with a 'supersedes' edge to its predecessor.
The chain is walked backwards from any version to find the full history.
The "active" version is the latest one not superseded by any other.
"""

from dataclasses import dataclass, field
from typing import Optional

from kgql.governance.schema import GovernanceFramework


@dataclass
class VersionChain:
    """
    A resolved supersession chain for a governance framework lineage.

    The chain is ordered from newest (index 0) to oldest (last index).
    Each entry is a GovernanceFramework that supersedes the next.

    Attributes:
        versions: Ordered list from newest to oldest
        active_said: SAID of the current active version (head of chain)
    """
    versions: list[GovernanceFramework] = field(default_factory=list)

    @property
    def active(self) -> Optional[GovernanceFramework]:
        """The current active (newest) version."""
        return self.versions[0] if self.versions else None

    @property
    def active_said(self) -> Optional[str]:
        """SAID of the active version."""
        return self.versions[0].said if self.versions else None

    @property
    def root(self) -> Optional[GovernanceFramework]:
        """The original (oldest) version in the chain."""
        return self.versions[-1] if self.versions else None

    @property
    def depth(self) -> int:
        """Number of versions in the chain."""
        return len(self.versions)

    def contains(self, said: str) -> bool:
        """Check if a SAID is anywhere in the chain."""
        return any(v.said == said for v in self.versions)

    def get_version(self, said: str) -> Optional[GovernanceFramework]:
        """Get a specific version by SAID."""
        for v in self.versions:
            if v.said == said:
                return v
        return None

    def saids(self) -> list[str]:
        """All SAIDs in the chain, newest first."""
        return [v.said for v in self.versions]


class FrameworkResolver:
    """
    Resolves governance framework SAIDs to GovernanceFramework objects.

    Uses a RegerWrapper (or any callable returning credential dicts) to
    fetch the raw credential, then parses it into a GovernanceFramework.

    Supports an in-memory cache keyed by SAID. Since SAIDs are
    content-addressable, cached entries never go stale (immutable content).

    Usage:
        resolver = FrameworkResolver(reger_wrapper)
        framework = resolver.resolve("EFrameworkSAID...")
        if framework:
            rules = framework.get_rules_for("QVI->LE")
    """

    def __init__(self, credential_resolver=None):
        """
        Initialize with an optional credential resolver.

        Args:
            credential_resolver: Callable that takes a SAID string and returns
                a credential dict, or None if not found. Typically a
                RegerWrapper.resolve() method or similar.
        """
        self._resolve_fn = credential_resolver
        self._cache: dict[str, GovernanceFramework] = {}
        self._superseded_by: dict[str, str] = {}  # old_said -> new_said

    def resolve(self, framework_said: str) -> Optional[GovernanceFramework]:
        """
        Resolve a framework SAID to a GovernanceFramework.

        Checks cache first (SAID = immutable, so cache never stales).
        Falls back to credential_resolver if provided.

        Args:
            framework_said: SAID of the governance framework credential

        Returns:
            GovernanceFramework if found and parseable, None otherwise
        """
        # Cache hit (SAIDs are content-addressed, so this is always valid)
        if framework_said in self._cache:
            return self._cache[framework_said]

        # Try to resolve via credential store
        if self._resolve_fn is None:
            return None

        cred_result = self._resolve_fn(framework_said)
        if cred_result is None:
            return None

        # Extract raw dict from result
        raw = cred_result
        if hasattr(cred_result, "data"):
            raw = cred_result.data
        if hasattr(cred_result, "raw"):
            raw = cred_result.raw
        if not isinstance(raw, dict):
            return None

        try:
            framework = GovernanceFramework.from_credential(raw)
        except (ValueError, KeyError, TypeError):
            return None

        self._cache[framework_said] = framework
        if framework.supersedes:
            self._superseded_by[framework.supersedes] = framework.said
        return framework

    def register(self, framework: GovernanceFramework) -> None:
        """
        Manually register a GovernanceFramework (e.g., for testing or
        for frameworks loaded from local config).

        Also records supersession edge if the framework has one.

        Args:
            framework: Parsed GovernanceFramework to cache
        """
        self._cache[framework.said] = framework
        if framework.supersedes:
            self._superseded_by[framework.supersedes] = framework.said

    def is_cached(self, framework_said: str) -> bool:
        """Check if a framework is in the cache."""
        return framework_said in self._cache

    def clear_cache(self) -> None:
        """Clear the framework cache."""
        self._cache.clear()
        self._superseded_by.clear()

    def register_supersession(
        self, new_said: str, old_said: str
    ) -> None:
        """
        Record that new_said supersedes old_said.

        This builds the forward index so we can find the active version
        from any version in the chain.

        Args:
            new_said: SAID of the newer framework
            old_said: SAID of the older framework being superseded
        """
        self._superseded_by[old_said] = new_said

    def resolve_chain(self, framework_said: str) -> VersionChain:
        """
        Resolve the full supersession chain containing a framework.

        Walks backward via supersedes edges to find ancestors, then
        walks forward via the superseded_by index to find descendants.
        Returns the chain ordered newest-first.

        Args:
            framework_said: Any SAID in the lineage

        Returns:
            VersionChain with all resolved versions, newest first
        """
        # Resolve the starting framework
        start = self.resolve(framework_said)
        if start is None:
            return VersionChain()

        # Walk backward through supersedes edges to find ancestors
        ancestors: list[GovernanceFramework] = []
        current = start
        seen = {start.said}
        while current.supersedes:
            prior = self.resolve(current.supersedes)
            if prior is None or prior.said in seen:
                break
            ancestors.append(prior)
            seen.add(prior.said)
            current = prior

        # Walk forward through superseded_by index to find descendants
        descendants: list[GovernanceFramework] = []
        current = start
        while current.said in self._superseded_by:
            next_said = self._superseded_by[current.said]
            if next_said in seen:
                break
            newer = self.resolve(next_said)
            if newer is None:
                break
            descendants.append(newer)
            seen.add(newer.said)
            current = newer

        # Build chain: descendants (newest first) + start + ancestors (oldest last)
        chain = list(reversed(descendants)) + [start] + ancestors
        return VersionChain(versions=chain)

    def resolve_active(self, framework_said: str) -> Optional[GovernanceFramework]:
        """
        Resolve the currently active version in a framework's lineage.

        From any version in the chain, finds the newest (non-superseded)
        version. This is what WITHIN FRAMEWORK should use by default.

        Args:
            framework_said: Any SAID in the lineage

        Returns:
            The active (newest) GovernanceFramework, or None
        """
        chain = self.resolve_chain(framework_said)
        return chain.active
