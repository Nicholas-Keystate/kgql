# -*- encoding: utf-8 -*-
"""
Tests for KGQL Governance Schema - Phase 4.1

Tests the governance framework credential data model:
- GovernanceFramework parsing from ACDC credentials
- ConstraintRule serialization/deserialization
- CredentialMatrixEntry lookups
- FrameworkVersion and supersession
- FrameworkResolver caching
- ConstraintChecker evaluation (operator algebra, matrix, depth)
"""

import pytest

from kgql.parser.ast import EdgeOperator
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
    CredentialMatrixEntry,
    FrameworkVersion,
)
from kgql.governance.resolver import FrameworkResolver
from kgql.governance.checker import (
    ConstraintChecker,
    CheckResult,
    ConstraintViolation,
    operator_satisfies,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def vlei_framework_credential():
    """Simulated vLEI governance framework ACDC credential."""
    return {
        "v": "ACDC10JSON000500_",
        "d": "EFrameworkSAID123456789012345678901234",
        "i": "EStewardAID1234567890123456789012345",
        "s": "EGovernanceSchemaSAID12345678901234567",
        "a": {
            "d": "EAttrSAID1234567890123456789012345678",
            "name": "vLEI Ecosystem Governance Framework",
            "version": "1.2.0",
            "rules": [
                {
                    "name": "qvi-issuance",
                    "description": "QVIs must use I2I edges to issue LE credentials",
                    "applies_to": "iss",
                    "required_operator": "I2I",
                    "enforcement": "strict",
                },
                {
                    "name": "delegation-depth",
                    "description": "Delegation chains limited to 3 levels",
                    "applies_to": "delegation",
                    "required_operator": "DI2I",
                    "max_delegation_depth": 3,
                    "enforcement": "strict",
                },
                {
                    "name": "jurisdiction-match",
                    "description": "Issuer jurisdiction should match subject country",
                    "applies_to": "iss",
                    "required_operator": "ANY",
                    "field_constraints": {
                        "jurisdiction": "$issuer.jurisdiction == $subject.country"
                    },
                    "enforcement": "advisory",
                },
            ],
            "credential_matrix": [
                {"action": "issue", "role": "QVI", "required_operator": "I2I", "allowed": True},
                {"action": "issue", "role": "LE", "required_operator": "DI2I", "allowed": True},
                {"action": "issue", "role": "Agent", "required_operator": "ANY", "allowed": False},
                {"action": "revoke", "role": "QVI", "required_operator": "I2I", "allowed": True},
                {"action": "revoke", "role": "LE", "required_operator": "ANY", "allowed": False},
                {"action": "query", "role": "QVI", "required_operator": "ANY", "allowed": True},
                {"action": "query", "role": "LE", "required_operator": "ANY", "allowed": True},
                {"action": "query", "role": "Agent", "required_operator": "ANY", "allowed": True},
            ],
            "authorities": {
                "QVI": ["EQVI_AID_1234567890123456789012345"],
                "LE": [],
            },
        },
        "e": {
            "supersedes": {
                "v": "ACDC10JSON000200_",
                "d": "EPriorFrameworkSAID1234567890123456",
                "i": "EStewardAID1234567890123456789012345",
                "s": "EGovernanceSchemaSAID12345678901234567",
            },
        },
        "r": {
            "d": "ERulesSAID12345678901234567890123456",
            "human_readable": "QVIs authorized by GLEIF may issue LE credentials...",
        },
    }


@pytest.fixture
def minimal_framework_credential():
    """Minimal valid governance framework credential."""
    return {
        "v": "ACDC10JSON000100_",
        "d": "EMinimalFrameworkSAID12345678901234567",
        "i": "EStewardAID1234567890123456789012345",
        "s": "EGovernanceSchemaSAID12345678901234567",
        "a": {
            "d": "EAttrSAID1234567890123456789012345678",
            "name": "Minimal Framework",
            "version": "0.1.0",
            "rules": [],
        },
    }


@pytest.fixture
def vlei_framework(vlei_framework_credential):
    """Parsed GovernanceFramework from the vLEI credential."""
    return GovernanceFramework.from_credential(vlei_framework_credential)


# ── ConstraintRule Tests ──────────────────────────────────────────────


class TestConstraintRule:
    def test_from_dict(self):
        rule = ConstraintRule.from_dict({
            "name": "test-rule",
            "description": "A test rule",
            "applies_to": "iss",
            "required_operator": "I2I",
            "enforcement": "strict",
        })
        assert rule.name == "test-rule"
        assert rule.required_operator == EdgeOperator.I2I
        assert rule.enforcement == RuleEnforcement.STRICT

    def test_to_dict_roundtrip(self):
        original = ConstraintRule(
            name="roundtrip",
            description="Test roundtrip",
            applies_to="acdc",
            required_operator=EdgeOperator.DI2I,
            field_constraints={"x": "$a == $b"},
            max_delegation_depth=5,
            enforcement=RuleEnforcement.ADVISORY,
        )
        data = original.to_dict()
        restored = ConstraintRule.from_dict(data)
        assert restored.name == original.name
        assert restored.required_operator == original.required_operator
        assert restored.field_constraints == original.field_constraints
        assert restored.max_delegation_depth == 5
        assert restored.enforcement == RuleEnforcement.ADVISORY

    def test_defaults(self):
        rule = ConstraintRule(name="bare")
        assert rule.required_operator == EdgeOperator.ANY
        assert rule.enforcement == RuleEnforcement.STRICT
        assert rule.max_delegation_depth is None
        assert rule.field_constraints == {}

    def test_from_dict_defaults(self):
        rule = ConstraintRule.from_dict({"name": "minimal"})
        assert rule.required_operator == EdgeOperator.ANY
        assert rule.enforcement == RuleEnforcement.STRICT


# ── CredentialMatrixEntry Tests ───────────────────────────────────────


class TestCredentialMatrixEntry:
    def test_from_dict(self):
        entry = CredentialMatrixEntry.from_dict({
            "action": "issue",
            "role": "QVI",
            "required_operator": "I2I",
            "allowed": True,
        })
        assert entry.action == "issue"
        assert entry.role == "QVI"
        assert entry.required_operator == EdgeOperator.I2I
        assert entry.allowed is True

    def test_roundtrip(self):
        original = CredentialMatrixEntry(
            action="revoke", role="LE",
            required_operator=EdgeOperator.DI2I, allowed=False,
        )
        restored = CredentialMatrixEntry.from_dict(original.to_dict())
        assert restored.action == "revoke"
        assert restored.role == "LE"
        assert restored.allowed is False


# ── GovernanceFramework Tests ─────────────────────────────────────────


class TestGovernanceFramework:
    def test_from_credential(self, vlei_framework):
        assert vlei_framework.said == "EFrameworkSAID123456789012345678901234"
        assert vlei_framework.name == "vLEI Ecosystem Governance Framework"
        assert vlei_framework.version == "1.2.0"
        assert vlei_framework.steward == "EStewardAID1234567890123456789012345"
        assert len(vlei_framework.rules) == 3
        assert len(vlei_framework.credential_matrix) == 8

    def test_supersedes(self, vlei_framework):
        assert vlei_framework.supersedes == "EPriorFrameworkSAID1234567890123456"

    def test_no_supersedes(self, minimal_framework_credential):
        fw = GovernanceFramework.from_credential(minimal_framework_credential)
        assert fw.supersedes is None

    def test_get_rules_for(self, vlei_framework):
        iss_rules = vlei_framework.get_rules_for("iss")
        assert len(iss_rules) == 2  # qvi-issuance + jurisdiction-match
        assert iss_rules[0].name == "qvi-issuance"

    def test_get_rules_for_missing(self, vlei_framework):
        assert vlei_framework.get_rules_for("nonexistent") == []

    def test_get_matrix_entry(self, vlei_framework):
        entry = vlei_framework.get_matrix_entry("issue", "QVI")
        assert entry is not None
        assert entry.required_operator == EdgeOperator.I2I
        assert entry.allowed is True

    def test_get_matrix_entry_disallowed(self, vlei_framework):
        entry = vlei_framework.get_matrix_entry("issue", "Agent")
        assert entry is not None
        assert entry.allowed is False

    def test_get_matrix_entry_missing(self, vlei_framework):
        assert vlei_framework.get_matrix_entry("delete", "Admin") is None

    def test_is_action_allowed(self, vlei_framework):
        assert vlei_framework.is_action_allowed("issue", "QVI") is True
        assert vlei_framework.is_action_allowed("issue", "Agent") is False
        assert vlei_framework.is_action_allowed("revoke", "LE") is False
        # Not in matrix = allowed
        assert vlei_framework.is_action_allowed("unknown", "unknown") is True

    def test_required_operator_for(self, vlei_framework):
        assert vlei_framework.required_operator_for("issue", "QVI") == EdgeOperator.I2I
        assert vlei_framework.required_operator_for("issue", "LE") == EdgeOperator.DI2I
        # Not in matrix = ANY
        assert vlei_framework.required_operator_for("unknown", "x") == EdgeOperator.ANY

    def test_authorities(self, vlei_framework):
        assert "QVI" in vlei_framework.authorities
        assert len(vlei_framework.authorities["QVI"]) == 1

    def test_to_dict(self, vlei_framework):
        d = vlei_framework.to_dict()
        assert d["name"] == "vLEI Ecosystem Governance Framework"
        assert d["version"] == "1.2.0"
        assert len(d["rules"]) == 3
        assert len(d["credential_matrix"]) == 8

    def test_raw_preserved(self, vlei_framework_credential):
        fw = GovernanceFramework.from_credential(vlei_framework_credential)
        assert fw.raw is vlei_framework_credential

    def test_invalid_credential(self):
        with pytest.raises(ValueError):
            GovernanceFramework.from_credential("not a dict")
        with pytest.raises(ValueError):
            GovernanceFramework.from_credential({})

    def test_minimal_credential(self, minimal_framework_credential):
        fw = GovernanceFramework.from_credential(minimal_framework_credential)
        assert fw.name == "Minimal Framework"
        assert fw.version == "0.1.0"
        assert fw.rules == []
        assert fw.credential_matrix == []


# ── FrameworkResolver Tests ───────────────────────────────────────────


class TestFrameworkResolver:
    def test_resolve_from_cache(self, vlei_framework):
        resolver = FrameworkResolver()
        resolver.register(vlei_framework)
        result = resolver.resolve(vlei_framework.said)
        assert result is vlei_framework

    def test_resolve_not_found(self):
        resolver = FrameworkResolver()
        assert resolver.resolve("ENonexistent") is None

    def test_resolve_no_resolver_fn(self):
        resolver = FrameworkResolver(credential_resolver=None)
        assert resolver.resolve("ESomeSAID") is None

    def test_resolve_via_callable(self, vlei_framework_credential):
        def mock_resolve(said):
            if said == "EFrameworkSAID123456789012345678901234":
                # Return an object with .data attribute
                class FakeResult:
                    data = vlei_framework_credential
                return FakeResult()
            return None

        resolver = FrameworkResolver(credential_resolver=mock_resolve)
        fw = resolver.resolve("EFrameworkSAID123456789012345678901234")
        assert fw is not None
        assert fw.name == "vLEI Ecosystem Governance Framework"
        # Should be cached now
        assert resolver.is_cached("EFrameworkSAID123456789012345678901234")

    def test_resolve_via_raw_dict(self, vlei_framework_credential):
        def mock_resolve(said):
            return vlei_framework_credential

        resolver = FrameworkResolver(credential_resolver=mock_resolve)
        fw = resolver.resolve("EFrameworkSAID123456789012345678901234")
        assert fw is not None

    def test_clear_cache(self, vlei_framework):
        resolver = FrameworkResolver()
        resolver.register(vlei_framework)
        assert resolver.is_cached(vlei_framework.said)
        resolver.clear_cache()
        assert not resolver.is_cached(vlei_framework.said)


# ── Operator Algebra Tests ────────────────────────────────────────────


class TestOperatorAlgebra:
    """Test the constraint algebra partial order: I2I > DI2I > NI2I > ANY."""

    def test_i2i_satisfies_all(self):
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.I2I)
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.DI2I)
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.NI2I)
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.ANY)

    def test_di2i_satisfies_di2i_and_below(self):
        assert not operator_satisfies(EdgeOperator.DI2I, EdgeOperator.I2I)
        assert operator_satisfies(EdgeOperator.DI2I, EdgeOperator.DI2I)
        assert operator_satisfies(EdgeOperator.DI2I, EdgeOperator.NI2I)
        assert operator_satisfies(EdgeOperator.DI2I, EdgeOperator.ANY)

    def test_ni2i_satisfies_ni2i_and_below(self):
        assert not operator_satisfies(EdgeOperator.NI2I, EdgeOperator.I2I)
        assert not operator_satisfies(EdgeOperator.NI2I, EdgeOperator.DI2I)
        assert operator_satisfies(EdgeOperator.NI2I, EdgeOperator.NI2I)
        assert operator_satisfies(EdgeOperator.NI2I, EdgeOperator.ANY)

    def test_any_satisfies_only_any(self):
        assert not operator_satisfies(EdgeOperator.ANY, EdgeOperator.I2I)
        assert not operator_satisfies(EdgeOperator.ANY, EdgeOperator.DI2I)
        assert not operator_satisfies(EdgeOperator.ANY, EdgeOperator.NI2I)
        assert operator_satisfies(EdgeOperator.ANY, EdgeOperator.ANY)


# ── ConstraintChecker Tests ───────────────────────────────────────────


class TestConstraintChecker:
    def test_check_edge_passes(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_edge("iss", EdgeOperator.I2I)
        assert result.allowed is True
        assert result.violations == []

    def test_check_edge_fails_strict(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        # "iss" requires I2I (from qvi-issuance rule)
        result = checker.check_edge("iss", EdgeOperator.NI2I)
        assert result.allowed is False
        assert len(result.violations) == 1
        assert result.violations[0].rule_name == "qvi-issuance"

    def test_check_edge_advisory_warning(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        # jurisdiction-match is advisory, applies_to "iss", requires ANY
        # So it won't trigger with ANY, but let's verify advisory mechanism
        # by creating a framework with advisory rules that would fail
        fw = GovernanceFramework(
            said="Etest",
            rules=[ConstraintRule(
                name="advisory-rule",
                applies_to="test_edge",
                required_operator=EdgeOperator.I2I,
                enforcement=RuleEnforcement.ADVISORY,
            )],
        )
        checker2 = ConstraintChecker(fw)
        result = checker2.check_edge("test_edge", EdgeOperator.NI2I)
        # Advisory violations don't block
        assert result.allowed is True
        assert len(result.warnings) == 1
        assert result.warnings[0].rule_name == "advisory-rule"

    def test_check_edge_no_rules(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_edge("nonexistent_edge", EdgeOperator.ANY)
        assert result.allowed is True

    def test_check_action_allowed(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_action("issue", "QVI", EdgeOperator.I2I)
        assert result.allowed is True

    def test_check_action_disallowed(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_action("issue", "Agent", EdgeOperator.I2I)
        assert result.allowed is False
        assert "not allowed" in result.violations[0].message

    def test_check_action_weak_operator(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        # issue by QVI requires I2I, but we provide NI2I
        result = checker.check_action("issue", "QVI", EdgeOperator.NI2I)
        assert result.allowed is False
        assert "requires" in result.violations[0].message

    def test_check_action_not_in_matrix(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_action("unknown_action", "unknown_role")
        assert result.allowed is True

    def test_check_delegation_depth_ok(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_delegation_depth("delegation", 2)
        assert result.allowed is True

    def test_check_delegation_depth_exceeded(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_delegation_depth("delegation", 5)
        assert result.allowed is False
        assert "exceeds maximum" in result.violations[0].message

    def test_check_delegation_depth_no_limit(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        # "iss" rules have no max_delegation_depth
        result = checker.check_delegation_depth("iss", 100)
        assert result.allowed is True

    def test_get_field_constraints(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        constraints = checker.get_field_constraints("iss")
        assert "jurisdiction" in constraints
        assert "$issuer.jurisdiction" in constraints["jurisdiction"]

    def test_framework_said_on_result(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_edge("iss", EdgeOperator.I2I)
        assert result.framework_said == vlei_framework.said

    def test_check_result_to_dict(self, vlei_framework):
        checker = ConstraintChecker(vlei_framework)
        result = checker.check_edge("iss", EdgeOperator.NI2I)
        d = result.to_dict()
        assert d["allowed"] is False
        assert len(d["violations"]) > 0
        assert d["framework_said"] == vlei_framework.said
