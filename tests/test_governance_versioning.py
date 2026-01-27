# -*- encoding: utf-8 -*-
"""
Tests for KGQL Governance Framework Versioning - Phase 4.4

Tests the supersession chain traversal, active version resolution,
and historical query support.
"""

import pytest

from kgql.parser.ast import EdgeOperator
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
    FrameworkVersion,
)
from kgql.governance.resolver import FrameworkResolver, VersionChain


# ── VersionChain Tests ───────────────────────────────────────────────


class TestVersionChain:
    """VersionChain data structure."""

    def test_empty_chain(self):
        chain = VersionChain()
        assert chain.active is None
        assert chain.active_said is None
        assert chain.root is None
        assert chain.depth == 0
        assert chain.saids() == []

    def test_single_version(self):
        fw = GovernanceFramework(said="EV1", name="FW v1")
        chain = VersionChain(versions=[fw])
        assert chain.active is fw
        assert chain.active_said == "EV1"
        assert chain.root is fw
        assert chain.depth == 1

    def test_multiple_versions_order(self):
        v1 = GovernanceFramework(said="EV1", name="v1")
        v2 = GovernanceFramework(said="EV2", name="v2")
        v3 = GovernanceFramework(said="EV3", name="v3")
        chain = VersionChain(versions=[v3, v2, v1])  # newest first
        assert chain.active is v3
        assert chain.root is v1
        assert chain.depth == 3
        assert chain.saids() == ["EV3", "EV2", "EV1"]

    def test_contains(self):
        v1 = GovernanceFramework(said="EV1", name="v1")
        v2 = GovernanceFramework(said="EV2", name="v2")
        chain = VersionChain(versions=[v2, v1])
        assert chain.contains("EV1")
        assert chain.contains("EV2")
        assert not chain.contains("EV3")

    def test_get_version(self):
        v1 = GovernanceFramework(said="EV1", name="v1")
        v2 = GovernanceFramework(said="EV2", name="v2")
        chain = VersionChain(versions=[v2, v1])
        assert chain.get_version("EV1") is v1
        assert chain.get_version("EV2") is v2
        assert chain.get_version("EV3") is None


# ── Supersession Registration Tests ─────────────────────────────────


class TestSupersessionRegistration:
    """Auto-registration of supersession edges."""

    def test_register_records_supersession(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(
            said="EV1", name="v1",
            version_info=FrameworkVersion(said="EV1", version="1.0.0"),
        )
        v2 = GovernanceFramework(
            said="EV2", name="v2",
            version_info=FrameworkVersion(
                said="EV2", version="2.0.0", supersedes_said="EV1",
            ),
        )
        resolver.register(v1)
        resolver.register(v2)
        # v1 is superseded by v2
        assert resolver._superseded_by.get("EV1") == "EV2"

    def test_register_no_supersession(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(
            said="EV1", name="v1",
            version_info=FrameworkVersion(said="EV1", version="1.0.0"),
        )
        resolver.register(v1)
        assert "EV1" not in resolver._superseded_by

    def test_clear_cache_clears_supersession(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(said="EV1", name="v1")
        v2 = GovernanceFramework(
            said="EV2", name="v2",
            version_info=FrameworkVersion(
                said="EV2", version="2.0.0", supersedes_said="EV1",
            ),
        )
        resolver.register(v1)
        resolver.register(v2)
        resolver.clear_cache()
        assert len(resolver._superseded_by) == 0
        assert not resolver.is_cached("EV1")


# ── Chain Traversal Tests ────────────────────────────────────────────


class TestResolveChain:
    """Supersession chain traversal."""

    @pytest.fixture
    def three_version_resolver(self):
        """Three-version lineage: v1 <- v2 <- v3."""
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(
            said="EV1", name="FW v1",
            version_info=FrameworkVersion(said="EV1", version="1.0.0"),
            rules=[
                ConstraintRule(name="r1", applies_to="iss",
                               required_operator=EdgeOperator.NI2I),
            ],
        )
        v2 = GovernanceFramework(
            said="EV2", name="FW v2",
            version_info=FrameworkVersion(
                said="EV2", version="2.0.0", supersedes_said="EV1",
            ),
            rules=[
                ConstraintRule(name="r1", applies_to="iss",
                               required_operator=EdgeOperator.DI2I),
            ],
        )
        v3 = GovernanceFramework(
            said="EV3", name="FW v3",
            version_info=FrameworkVersion(
                said="EV3", version="3.0.0", supersedes_said="EV2",
            ),
            rules=[
                ConstraintRule(name="r1", applies_to="iss",
                               required_operator=EdgeOperator.I2I),
            ],
        )
        resolver.register(v1)
        resolver.register(v2)
        resolver.register(v3)
        return resolver

    def test_chain_from_latest(self, three_version_resolver):
        chain = three_version_resolver.resolve_chain("EV3")
        assert chain.depth == 3
        assert chain.saids() == ["EV3", "EV2", "EV1"]
        assert chain.active_said == "EV3"

    def test_chain_from_middle(self, three_version_resolver):
        chain = three_version_resolver.resolve_chain("EV2")
        assert chain.depth == 3
        assert chain.saids() == ["EV3", "EV2", "EV1"]

    def test_chain_from_oldest(self, three_version_resolver):
        chain = three_version_resolver.resolve_chain("EV1")
        assert chain.depth == 3
        assert chain.saids() == ["EV3", "EV2", "EV1"]

    def test_chain_unknown_said(self, three_version_resolver):
        chain = three_version_resolver.resolve_chain("EUnknown")
        assert chain.depth == 0

    def test_chain_single_version(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(said="EV1", name="Solo")
        resolver.register(v1)
        chain = resolver.resolve_chain("EV1")
        assert chain.depth == 1
        assert chain.active_said == "EV1"

    def test_chain_rules_evolve(self, three_version_resolver):
        """Verify rules strengthen across versions."""
        chain = three_version_resolver.resolve_chain("EV1")
        v1 = chain.get_version("EV1")
        v3 = chain.get_version("EV3")
        # v1 requires NI2I, v3 requires I2I (stricter)
        assert v1.rules[0].required_operator == EdgeOperator.NI2I
        assert v3.rules[0].required_operator == EdgeOperator.I2I


# ── Active Version Resolution Tests ─────────────────────────────────


class TestResolveActive:
    """Resolve the active (newest) version from any point in chain."""

    def test_active_from_oldest(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(said="EV1", name="v1")
        v2 = GovernanceFramework(
            said="EV2", name="v2",
            version_info=FrameworkVersion(
                said="EV2", version="2.0.0", supersedes_said="EV1",
            ),
        )
        resolver.register(v1)
        resolver.register(v2)
        active = resolver.resolve_active("EV1")
        assert active is not None
        assert active.said == "EV2"

    def test_active_from_latest(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(said="EV1", name="v1")
        v2 = GovernanceFramework(
            said="EV2", name="v2",
            version_info=FrameworkVersion(
                said="EV2", version="2.0.0", supersedes_said="EV1",
            ),
        )
        resolver.register(v1)
        resolver.register(v2)
        active = resolver.resolve_active("EV2")
        assert active.said == "EV2"

    def test_active_unknown(self):
        resolver = FrameworkResolver()
        assert resolver.resolve_active("EUnknown") is None

    def test_active_single_version(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(said="EV1", name="Solo")
        resolver.register(v1)
        active = resolver.resolve_active("EV1")
        assert active.said == "EV1"


# ── Historical Pinning Tests ────────────────────────────────────────


class TestHistoricalPinning:
    """WITHIN FRAMEWORK can pin to a specific version."""

    def test_resolve_specific_version(self):
        """Resolving a specific SAID returns that version, not active."""
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(
            said="EV1", name="v1",
            version_info=FrameworkVersion(said="EV1", version="1.0.0"),
            rules=[
                ConstraintRule(name="r1", applies_to="iss",
                               required_operator=EdgeOperator.NI2I),
            ],
        )
        v2 = GovernanceFramework(
            said="EV2", name="v2",
            version_info=FrameworkVersion(
                said="EV2", version="2.0.0", supersedes_said="EV1",
            ),
            rules=[
                ConstraintRule(name="r1", applies_to="iss",
                               required_operator=EdgeOperator.I2I),
            ],
        )
        resolver.register(v1)
        resolver.register(v2)

        # resolve() returns the exact version requested (pinned)
        pinned = resolver.resolve("EV1")
        assert pinned.said == "EV1"
        assert pinned.rules[0].required_operator == EdgeOperator.NI2I

        # resolve_active() returns the newest
        active = resolver.resolve_active("EV1")
        assert active.said == "EV2"
        assert active.rules[0].required_operator == EdgeOperator.I2I

    def test_register_supersession_explicit(self):
        """Explicit supersession registration works."""
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(said="EV1", name="v1")
        v2 = GovernanceFramework(said="EV2", name="v2")
        resolver.register(v1)
        resolver.register(v2)
        resolver.register_supersession("EV2", "EV1")

        active = resolver.resolve_active("EV1")
        assert active.said == "EV2"


# ── Cycle Protection Tests ──────────────────────────────────────────


class TestCycleProtection:
    """Chain traversal handles cycles without infinite loops."""

    def test_self_referencing_supersedes(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(
            said="EV1", name="v1",
            version_info=FrameworkVersion(
                said="EV1", version="1.0.0", supersedes_said="EV1",
            ),
        )
        resolver.register(v1)
        chain = resolver.resolve_chain("EV1")
        assert chain.depth == 1  # No infinite loop

    def test_mutual_supersession(self):
        resolver = FrameworkResolver()
        v1 = GovernanceFramework(
            said="EV1", name="v1",
            version_info=FrameworkVersion(
                said="EV1", version="1.0.0", supersedes_said="EV2",
            ),
        )
        v2 = GovernanceFramework(
            said="EV2", name="v2",
            version_info=FrameworkVersion(
                said="EV2", version="2.0.0", supersedes_said="EV1",
            ),
        )
        resolver.register(v1)
        resolver.register(v2)
        chain = resolver.resolve_chain("EV1")
        # Should not infinite loop; both versions present
        assert chain.depth == 2
