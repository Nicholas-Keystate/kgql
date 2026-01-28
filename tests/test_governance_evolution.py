# -*- encoding: utf-8 -*-
"""
Tests for KGQL Governance Evolution - Modes A and B.

Mode A: Steward supersession (centralized authority)
Mode B: Emergent deliberation (collective authorization)
"""

import pytest
from kgql.parser.ast import EdgeOperator
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    CredentialMatrixEntry,
    FrameworkVersion,
    RuleEnforcement,
)
from kgql.governance.resolver import FrameworkResolver
from kgql.governance.evolution import GovernanceEvolution, EvolutionResult
from kgql.governance.patterns import operator_floor, role_action_matrix


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STEWARD_AID = "Esteward_aid_000000000000000000000000"
OTHER_AID = "Eother_aid_00000000000000000000000000"


@pytest.fixture
def base_framework():
    """A v1.0.0 governance framework for testing evolution."""
    rules = [
        *operator_floor(["content_rotation"], minimum=EdgeOperator.DI2I),
    ]
    matrix = role_action_matrix(
        roles=["controller"],
        actions=["rotate"],
        default_operator=EdgeOperator.DI2I,
    )
    return GovernanceFramework(
        said="Ebase_framework_said_0000000000000000000",
        name="Test Framework",
        version_info=FrameworkVersion(
            said="Ebase_framework_said_0000000000000000000",
            version="1.0.0",
            supersedes_said=None,
            steward_aid=STEWARD_AID,
        ),
        steward=STEWARD_AID,
        rules=rules,
        credential_matrix=matrix,
        authorities={"controller": [STEWARD_AID]},
    )


@pytest.fixture
def resolver(base_framework):
    """FrameworkResolver with the base framework registered."""
    r = FrameworkResolver()
    r.register(base_framework)
    return r


@pytest.fixture
def evolution(resolver):
    """GovernanceEvolution instance."""
    return GovernanceEvolution(resolver)


# ---------------------------------------------------------------------------
# Mode A: Steward Supersession
# ---------------------------------------------------------------------------

class TestModeASupersession:

    def test_supersede_success(self, evolution, base_framework):
        """Test basic steward supersession."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
            new_version="2.0.0",
            reason="Policy update",
        )

        assert result.success
        assert result.mode == "A"
        assert result.prior_said == base_framework.said
        assert result.new_framework is not None
        assert result.new_framework.version == "2.0.0"

    def test_supersede_inherits_name(self, evolution, base_framework):
        """Test that name is inherited when not specified."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        assert result.new_framework.name == "Test Framework"

    def test_supersede_updates_name(self, evolution, base_framework):
        """Test that name can be changed."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
            new_name="Renamed Framework",
        )

        assert result.new_framework.name == "Renamed Framework"

    def test_supersede_auto_bumps_version(self, evolution, base_framework):
        """Test automatic version bumping."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        assert result.new_framework.version == "1.1.0"

    def test_supersede_inherits_rules(self, evolution, base_framework):
        """Test that rules are inherited when not specified."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        assert len(result.new_framework.rules) == len(base_framework.rules)

    def test_supersede_updates_rules(self, evolution, base_framework):
        """Test that rules can be replaced."""
        new_rules = [
            ConstraintRule(
                name="new-rule",
                applies_to="iss",
                required_operator=EdgeOperator.I2I,
            ),
        ]

        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
            new_rules=new_rules,
        )

        assert len(result.new_framework.rules) == 1
        assert result.new_framework.rules[0].name == "new-rule"

    def test_supersede_wrong_steward_fails(self, evolution, base_framework):
        """Test that non-steward cannot supersede."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=OTHER_AID,
        )

        assert not result.success
        assert "not authorized" in result.reason

    def test_supersede_unknown_framework_fails(self, evolution):
        """Test supersession of non-existent framework."""
        result = evolution.supersede(
            current_said="Eunknown_000000000000000000000000000",
            steward_aid=STEWARD_AID,
        )

        assert not result.success
        assert "not found" in result.reason

    def test_supersede_registers_in_resolver(self, evolution, resolver, base_framework):
        """Test that new framework is registered in the resolver."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        resolved = resolver.resolve(result.new_framework.said)
        assert resolved is not None
        assert resolved.said == result.new_framework.said

    def test_supersede_registers_chain(self, evolution, resolver, base_framework):
        """Test that supersession chain is tracked."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        # The new framework should be the active version
        active = resolver.resolve_active(base_framework.said)
        assert active is not None
        assert active.said == result.new_framework.said

    def test_supersede_chain_three_versions(self, evolution, resolver, base_framework):
        """Test three-version supersession chain."""
        r1 = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
            new_version="2.0.0",
        )

        r2 = evolution.supersede(
            current_said=r1.new_framework.said,
            steward_aid=STEWARD_AID,
            new_version="3.0.0",
        )

        assert r2.success
        assert r2.prior_said == r1.new_framework.said

        # Resolve chain from original
        chain = resolver.resolve_chain(base_framework.said)
        assert chain.depth >= 2

    def test_supersede_preserves_raw_credential(self, evolution, base_framework):
        """Test that raw ACDC credential is preserved."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        raw = result.new_framework.raw
        assert raw is not None
        assert raw["e"]["supersedes"]["d"] == base_framework.said
        assert raw["i"] == STEWARD_AID

    def test_supersede_version_info_chain(self, evolution, base_framework):
        """Test that version_info tracks the supersession correctly."""
        result = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        vi = result.new_framework.version_info
        assert vi.supersedes_said == base_framework.said
        assert vi.steward_aid == STEWARD_AID

    def test_supersede_no_steward_on_framework_allows_any(self, resolver):
        """Test that framework with empty steward allows anyone."""
        fw = GovernanceFramework(
            said="Enosteward_000000000000000000000000000",
            name="Open Framework",
            steward="",  # No steward restriction
        )
        resolver.register(fw)
        evo = GovernanceEvolution(resolver)

        result = evo.supersede(
            current_said=fw.said,
            steward_aid=OTHER_AID,
        )

        assert result.success


# ---------------------------------------------------------------------------
# Mode B: Emergent Deliberation
# ---------------------------------------------------------------------------

class TestModeBDeliberation:

    def test_evolve_from_ratification(self, evolution, base_framework):
        """Test Mode B evolution from ratification."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={
                "proposer_aid": OTHER_AID,
                "proposed_version": "2.0.0",
                "proposed_name": "Community Framework",
            },
        )

        assert result.success
        assert result.mode == "B"
        assert result.new_framework.name == "Community Framework"
        assert result.new_framework.version == "2.0.0"
        assert result.new_framework.steward == OTHER_AID

    def test_mode_b_inherits_rules(self, evolution, base_framework):
        """Test that Mode B inherits rules when not proposed."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={
                "proposer_aid": OTHER_AID,
            },
        )

        assert len(result.new_framework.rules) == len(base_framework.rules)

    def test_mode_b_updates_rules(self, evolution, base_framework):
        """Test that Mode B applies proposed rules."""
        new_rule = ConstraintRule(
            name="community-rule",
            applies_to="iss",
            required_operator=EdgeOperator.I2I,
        )

        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={
                "proposer_aid": OTHER_AID,
                "proposed_rules": [new_rule.to_dict()],
            },
        )

        assert len(result.new_framework.rules) == 1
        assert result.new_framework.rules[0].name == "community-rule"

    def test_mode_b_updates_matrix(self, evolution, base_framework):
        """Test that Mode B applies proposed credential matrix."""
        new_entry = CredentialMatrixEntry(
            action="query",
            role="reader",
            required_operator=EdgeOperator.NI2I,
            allowed=True,
        )

        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={
                "proposer_aid": OTHER_AID,
                "proposed_matrix": [new_entry.to_dict()],
            },
        )

        assert len(result.new_framework.credential_matrix) == 1
        assert result.new_framework.credential_matrix[0].action == "query"

    def test_mode_b_missing_proposer_fails(self, evolution, base_framework):
        """Test that Mode B requires proposer_aid."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={},  # Missing proposer_aid
        )

        assert not result.success
        assert "proposer_aid" in result.reason

    def test_mode_b_unknown_framework_fails(self, evolution):
        """Test Mode B with non-existent current framework."""
        result = evolution.evolve_from_ratification(
            current_said="Eunknown_000000000000000000000000000",
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={"proposer_aid": OTHER_AID},
        )

        assert not result.success
        assert "not found" in result.reason

    def test_mode_b_has_ratification_edge(self, evolution, base_framework):
        """Test that Mode B credential has edge to ratification."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={"proposer_aid": OTHER_AID},
        )

        raw = result.new_framework.raw
        assert "ratification" in raw["e"]
        assert raw["e"]["ratification"]["d"] == "Erat_said_0000000000000000000000000000"

    def test_mode_b_has_supersedes_edge(self, evolution, base_framework):
        """Test that Mode B credential has supersedes edge."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={"proposer_aid": OTHER_AID},
        )

        raw = result.new_framework.raw
        assert raw["e"]["supersedes"]["d"] == base_framework.said

    def test_mode_b_auto_bumps_version(self, evolution, base_framework):
        """Test that Mode B auto-bumps version."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={"proposer_aid": OTHER_AID},
        )

        assert result.new_framework.version == "1.1.0"

    def test_mode_b_registers_in_resolver(self, evolution, resolver, base_framework):
        """Test that Mode B result is registered in resolver."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={"proposer_aid": OTHER_AID},
        )

        resolved = resolver.resolve(result.new_framework.said)
        assert resolved is not None

    def test_mode_b_does_not_require_steward(self, evolution, base_framework):
        """Test that Mode B allows any proposer (collective authorization)."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={"proposer_aid": "Erandom_proposer_000000000000000000"},
        )

        # Mode B bypasses steward check — ratification IS the authorization
        assert result.success

    def test_mode_b_evolution_metadata(self, evolution, base_framework):
        """Test that Mode B credential includes evolution metadata."""
        result = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={"proposer_aid": OTHER_AID},
        )

        raw = result.new_framework.raw
        assert raw["a"]["evolution_mode"] == "B"


# ---------------------------------------------------------------------------
# Version Bumping
# ---------------------------------------------------------------------------

class TestVersionBumping:

    def test_bump_minor(self):
        assert GovernanceEvolution._bump_version("1.0.0") == "1.1.0"

    def test_bump_with_patch(self):
        assert GovernanceEvolution._bump_version("2.3.1") == "2.4.0"

    def test_bump_invalid_format(self):
        assert GovernanceEvolution._bump_version("bad") == "1.1.0"

    def test_bump_non_numeric(self):
        assert GovernanceEvolution._bump_version("a.b.c") == "1.1.0"


# ---------------------------------------------------------------------------
# Cross-Mode Tests
# ---------------------------------------------------------------------------

class TestCrossMode:

    def test_mode_a_then_mode_b(self, evolution, base_framework):
        """Test Mode A supersession followed by Mode B deliberation."""
        r1 = evolution.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
            new_version="2.0.0",
        )
        assert r1.success

        r2 = evolution.evolve_from_ratification(
            current_said=r1.new_framework.said,
            ratification_said="Erat_community_000000000000000000000",
            ratification_data={
                "proposer_aid": OTHER_AID,
                "proposed_version": "3.0.0",
            },
        )
        assert r2.success
        assert r2.prior_said == r1.new_framework.said
        assert r2.new_framework.steward == OTHER_AID

    def test_mode_b_then_mode_a(self, evolution, base_framework):
        """Test Mode B deliberation followed by Mode A supersession by new steward."""
        r1 = evolution.evolve_from_ratification(
            current_said=base_framework.said,
            ratification_said="Erat_said_0000000000000000000000000000",
            ratification_data={
                "proposer_aid": OTHER_AID,
                "proposed_version": "2.0.0",
            },
        )
        assert r1.success

        # New steward (OTHER_AID) can now supersede
        r2 = evolution.supersede(
            current_said=r1.new_framework.said,
            steward_aid=OTHER_AID,
            new_version="3.0.0",
        )
        assert r2.success

    def test_custom_credential_factory(self, resolver, base_framework):
        """Test with custom credential factory."""
        factory_calls = []

        def mock_factory(credential: dict) -> str:
            factory_calls.append(credential)
            return "Ecustom_said_00000000000000000000000000"

        evo = GovernanceEvolution(resolver, credential_factory=mock_factory)
        result = evo.supersede(
            current_said=base_framework.said,
            steward_aid=STEWARD_AID,
        )

        assert result.success
        assert len(factory_calls) == 1
        assert result.new_framework.said == "Ecustom_said_00000000000000000000000000"
