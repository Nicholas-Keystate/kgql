# -*- encoding: utf-8 -*-
"""
KGQL Framework Resolver - Resolves framework SAIDs to GovernanceFramework objects.

In KGQL queries, `WITHIN FRAMEWORK 'EFrameworkSAID...'` references a governance
framework credential by SAID. This module resolves that SAID to a parsed
GovernanceFramework that the ConstraintChecker can evaluate.

Resolution follows the same principle as credential resolution:
"Resolution IS Verification" - if the SAID resolves, integrity is guaranteed.
"""

from typing import Optional

from kgql.governance.schema import GovernanceFramework


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
        return framework

    def register(self, framework: GovernanceFramework) -> None:
        """
        Manually register a GovernanceFramework (e.g., for testing or
        for frameworks loaded from local config).

        Args:
            framework: Parsed GovernanceFramework to cache
        """
        self._cache[framework.said] = framework

    def is_cached(self, framework_said: str) -> bool:
        """Check if a framework is in the cache."""
        return framework_said in self._cache

    def clear_cache(self) -> None:
        """Clear the framework cache."""
        self._cache.clear()
