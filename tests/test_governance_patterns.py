# -*- encoding: utf-8 -*-
"""
Tests for KGQL Constraint Pattern Library.

Tests each pattern factory function and the composite vLEI framework.
"""

import pytest
from kgql.parser.ast import EdgeOperator
from kgql.governance.schema import (
    ConstraintRule,
    CredentialMatrixEntry,
    GovernanceFramework,
    RuleEnforcement,
)
from kgql.governance.checker import ConstraintChecker
from kgql.governance.compiler import ConstraintCompiler
from kgql.governance.patterns import (
    jurisdiction_match,
    delegation_depth,
    operator_floor,
    role_action_matrix,
    temporal_validity,
    chain_integrity,
    vlei_standard_framework,
)


# ---------------------------------------------------------------------------
# Pattern 1: Jurisdiction Match
# ---------------------------------------------------------------------------

class TestJurisdictionMatch:

    def test_produces_one_rule(self):
        rules = jurisdiction_match("iss")
        assert len(rules) == 1
        assert isinstance(rules[0], ConstraintRule)

    def test_rule_name(self):
        rules = jurisdiction_match("iss")
        assert rules[0].name == "jurisdiction-match"

    def test_applies_to_passthrough(self):
        rules = jurisdiction_match("QVI->LE")
        assert rules[0].applies_to == "QVI->LE"

    def test_default_operator_di2i(self):
        rules = jurisdiction_match("iss")
        assert rules[0].required_operator == EdgeOperator.DI2I

    def test_field_constraint_expression(self):
        rules = jurisdiction_match("iss")
        fc = rules[0].field_constraints
        assert "jurisdiction" in fc
        assert "$issuer.jurisdiction == $subject.country" in fc["jurisdiction"]

    def test_custom_fields(self):
        rules = jurisdiction_match(
            "iss",
            issuer_field="region",
            subject_field="locale",
        )
        fc = rules[0].field_constraints["jurisdiction"]
        assert "$issuer.region" in fc
        assert "$subject.locale" in fc

    def test_advisory_enforcement(self):
        rules = jurisdiction_match("iss", enforcement=RuleEnforcement.ADVISORY)
        assert rules[0].enforcement == RuleEnforcement.ADVISORY

    def test_strict_enforcement_default(self):
        rules = jurisdiction_match("iss")
        assert rules[0].enforcement == RuleEnforcement.STRICT

    def test_serialization_roundtrip(self):
        rules = jurisdiction_match("iss")
        d = rules[0].to_dict()
        restored = ConstraintRule.from_dict(d)
        assert restored.name == "jurisdiction-match"
        assert restored.applies_to == "iss"


# ---------------------------------------------------------------------------
# Pattern 2: Delegation Depth
# ---------------------------------------------------------------------------

class TestDelegationDepth:

    def test_produces_one_rule(self):
        rules = delegation_depth("delegate", max_depth=3)
        assert len(rules) == 1

    def test_max_depth_value(self):
        rules = delegation_depth("delegate", max_depth=5)
        assert rules[0].max_delegation_depth == 5

    def test_default_operator(self):
        rules = delegation_depth("delegate")
        assert rules[0].required_operator == EdgeOperator.DI2I

    def test_custom_operator(self):
        rules = delegation_depth(
            "delegate", required_operator=EdgeOperator.I2I
        )
        assert rules[0].required_operator == EdgeOperator.I2I

    def test_default_depth_is_3(self):
        rules = delegation_depth("delegate")
        assert rules[0].max_delegation_depth == 3

    def test_checker_passes_within_depth(self):
        rules = delegation_depth("delegate", max_depth=3)
        fw = GovernanceFramework(said="Etest", rules=rules)
        checker = ConstraintChecker(fw)
        result = checker.check_delegation_depth("delegate", 2)
        assert result.allowed

    def test_checker_fails_beyond_depth(self):
        rules = delegation_depth("delegate", max_depth=3)
        fw = GovernanceFramework(said="Etest", rules=rules)
        checker = ConstraintChecker(fw)
        result = checker.check_delegation_depth("delegate", 4)
        assert not result.allowed
        assert len(result.violations) == 1

    def test_checker_exact_depth_passes(self):
        rules = delegation_depth("delegate", max_depth=3)
        fw = GovernanceFramework(said="Etest", rules=rules)
        checker = ConstraintChecker(fw)
        result = checker.check_delegation_depth("delegate", 3)
        assert result.allowed


# ---------------------------------------------------------------------------
# Pattern 3: Operator Floor
# ---------------------------------------------------------------------------

class TestOperatorFloor:

    def test_one_rule_per_edge_type(self):
        rules = operator_floor(["iss", "rev", "delegate"])
        assert len(rules) == 3

    def test_default_minimum_di2i(self):
        rules = operator_floor(["iss"])
        assert rules[0].required_operator == EdgeOperator.DI2I

    def test_custom_minimum(self):
        rules = operator_floor(["iss"], minimum=EdgeOperator.I2I)
        assert rules[0].required_operator == EdgeOperator.I2I

    def test_rule_names_include_edge_type(self):
        rules = operator_floor(["iss", "rev"])
        names = {r.name for r in rules}
        assert "operator-floor-iss" in names
        assert "operator-floor-rev" in names

    def test_applies_to_matches(self):
        rules = operator_floor(["iss", "rev"])
        applies = {r.applies_to for r in rules}
        assert applies == {"iss", "rev"}

    def test_empty_list(self):
        rules = operator_floor([])
        assert rules == []

    def test_checker_passes_stronger(self):
        rules = operator_floor(["iss"], minimum=EdgeOperator.DI2I)
        fw = GovernanceFramework(said="Etest", rules=rules)
        checker = ConstraintChecker(fw)
        result = checker.check_edge("iss", EdgeOperator.I2I)
        assert result.allowed

    def test_checker_fails_weaker(self):
        rules = operator_floor(["iss"], minimum=EdgeOperator.DI2I)
        fw = GovernanceFramework(said="Etest", rules=rules)
        checker = ConstraintChecker(fw)
        result = checker.check_edge("iss", EdgeOperator.NI2I)
        assert not result.allowed


# ---------------------------------------------------------------------------
# Pattern 4: Role-Action Matrix
# ---------------------------------------------------------------------------

class TestRoleActionMatrix:

    def test_cartesian_product(self):
        matrix = role_action_matrix(
            roles=["QVI", "LE"],
            actions=["issue", "revoke"],
        )
        assert len(matrix) == 4

    def test_all_entries_are_credential_matrix(self):
        matrix = role_action_matrix(
            roles=["QVI"], actions=["issue"],
        )
        assert all(isinstance(e, CredentialMatrixEntry) for e in matrix)

    def test_default_operator(self):
        matrix = role_action_matrix(
            roles=["QVI"], actions=["issue"],
            default_operator=EdgeOperator.I2I,
        )
        assert matrix[0].required_operator == EdgeOperator.I2I

    def test_denied_entry(self):
        matrix = role_action_matrix(
            roles=["QVI", "LE"],
            actions=["issue"],
            denied={("issue", "LE"): True},
        )
        le_entry = [e for e in matrix if e.role == "LE"][0]
        assert not le_entry.allowed

    def test_override_operator(self):
        matrix = role_action_matrix(
            roles=["QVI"],
            actions=["issue"],
            overrides={("issue", "QVI"): EdgeOperator.I2I},
        )
        assert matrix[0].required_operator == EdgeOperator.I2I

    def test_denied_overrides_operator(self):
        """Denied takes precedence — operator is ANY but allowed is False."""
        matrix = role_action_matrix(
            roles=["QVI"],
            actions=["issue"],
            denied={("issue", "QVI"): True},
            overrides={("issue", "QVI"): EdgeOperator.I2I},
        )
        assert not matrix[0].allowed

    def test_checker_integration(self):
        matrix = role_action_matrix(
            roles=["QVI", "LE"],
            actions=["issue", "query"],
            denied={("issue", "LE"): True},
        )
        fw = GovernanceFramework(said="Etest", credential_matrix=matrix)
        checker = ConstraintChecker(fw)

        # QVI can issue
        r = checker.check_action("issue", "QVI", EdgeOperator.DI2I)
        assert r.allowed

        # LE cannot issue
        r = checker.check_action("issue", "LE", EdgeOperator.I2I)
        assert not r.allowed


# ---------------------------------------------------------------------------
# Pattern 5: Temporal Validity
# ---------------------------------------------------------------------------

class TestTemporalValidity:

    def test_produces_two_rules(self):
        rules = temporal_validity("iss")
        assert len(rules) == 2

    def test_expiry_rule_strict(self):
        rules = temporal_validity("iss")
        expiry = [r for r in rules if r.name == "temporal-not-expired"][0]
        assert expiry.enforcement == RuleEnforcement.STRICT

    def test_freshness_rule_advisory(self):
        rules = temporal_validity("iss")
        freshness = [r for r in rules if r.name == "temporal-freshness"][0]
        assert freshness.enforcement == RuleEnforcement.ADVISORY

    def test_expiry_field_constraint(self):
        rules = temporal_validity("iss")
        expiry = [r for r in rules if r.name == "temporal-not-expired"][0]
        assert "expiry" in expiry.field_constraints
        assert "$subject.expiry_date > $now.timestamp" in expiry.field_constraints["expiry"]

    def test_custom_field_names(self):
        rules = temporal_validity(
            "iss",
            freshness_field="created_at",
            expiry_field="valid_until",
        )
        expiry = [r for r in rules if r.name == "temporal-not-expired"][0]
        assert "$subject.valid_until" in expiry.field_constraints["expiry"]

    def test_advisory_enforcement_overrides_expiry(self):
        rules = temporal_validity("iss", enforcement=RuleEnforcement.ADVISORY)
        expiry = [r for r in rules if r.name == "temporal-not-expired"][0]
        assert expiry.enforcement == RuleEnforcement.ADVISORY

    def test_all_apply_to_same_edge(self):
        rules = temporal_validity("qvi_issue")
        assert all(r.applies_to == "qvi_issue" for r in rules)


# ---------------------------------------------------------------------------
# Pattern 6: Chain Integrity
# ---------------------------------------------------------------------------

class TestChainIntegrity:

    def test_decreasing_operator_strength(self):
        rules = chain_integrity(
            chain_edges=["root", "mid", "leaf"],
        )
        assert rules[0].required_operator == EdgeOperator.I2I
        assert rules[1].required_operator == EdgeOperator.DI2I
        assert rules[2].required_operator == EdgeOperator.NI2I

    def test_single_edge_is_root(self):
        rules = chain_integrity(chain_edges=["only"])
        assert len(rules) == 1
        # Single edge is both root and leaf — root wins
        assert rules[0].required_operator == EdgeOperator.I2I
        assert "root" in rules[0].name

    def test_two_edges_root_and_leaf(self):
        rules = chain_integrity(chain_edges=["first", "last"])
        assert rules[0].required_operator == EdgeOperator.I2I
        assert rules[1].required_operator == EdgeOperator.NI2I

    def test_empty_chain(self):
        rules = chain_integrity(chain_edges=[])
        assert rules == []

    def test_custom_operators(self):
        rules = chain_integrity(
            chain_edges=["a", "b", "c"],
            root_operator=EdgeOperator.I2I,
            intermediate_operator=EdgeOperator.I2I,
            leaf_operator=EdgeOperator.DI2I,
        )
        assert all(
            r.required_operator in (EdgeOperator.I2I, EdgeOperator.DI2I)
            for r in rules
        )

    def test_names_reflect_position(self):
        rules = chain_integrity(chain_edges=["a", "b", "c"])
        assert "root" in rules[0].name
        assert "intermediate" in rules[1].name
        assert "leaf" in rules[2].name

    def test_all_strict_enforcement(self):
        rules = chain_integrity(chain_edges=["a", "b", "c"])
        assert all(r.enforcement == RuleEnforcement.STRICT for r in rules)

    def test_checker_validates_chain(self):
        rules = chain_integrity(
            chain_edges=["gleif_auth", "qvi_issue", "le_assign"],
        )
        fw = GovernanceFramework(said="Etest", rules=rules)
        checker = ConstraintChecker(fw)

        # Root requires I2I
        r = checker.check_edge("gleif_auth", EdgeOperator.I2I)
        assert r.allowed

        # Root fails with DI2I
        r = checker.check_edge("gleif_auth", EdgeOperator.DI2I)
        assert not r.allowed

        # Leaf passes with NI2I
        r = checker.check_edge("le_assign", EdgeOperator.NI2I)
        assert r.allowed


# ---------------------------------------------------------------------------
# Composite: vLEI Standard Framework
# ---------------------------------------------------------------------------

class TestVleiStandardFramework:

    def test_returns_dict_with_required_keys(self):
        config = vlei_standard_framework()
        assert "rules" in config
        assert "credential_matrix" in config
        assert "authorities" in config

    def test_rules_are_constraint_rules(self):
        config = vlei_standard_framework()
        assert all(isinstance(r, ConstraintRule) for r in config["rules"])

    def test_matrix_entries_are_typed(self):
        config = vlei_standard_framework()
        assert all(
            isinstance(e, CredentialMatrixEntry)
            for e in config["credential_matrix"]
        )

    def test_rules_count(self):
        """At least 6 patterns composed: jurisdiction + depth + 3 floors + 3 chains + 2 temporal."""
        config = vlei_standard_framework()
        assert len(config["rules"]) >= 9

    def test_matrix_covers_gleif_qvi_le(self):
        config = vlei_standard_framework()
        roles = {e.role for e in config["credential_matrix"]}
        assert roles == {"GLEIF", "QVI", "LE"}

    def test_le_cannot_issue(self):
        config = vlei_standard_framework()
        le_issue = [
            e for e in config["credential_matrix"]
            if e.action == "issue" and e.role == "LE"
        ]
        assert len(le_issue) == 1
        assert not le_issue[0].allowed

    def test_gleif_requires_i2i_for_issue(self):
        config = vlei_standard_framework()
        gleif_issue = [
            e for e in config["credential_matrix"]
            if e.action == "issue" and e.role == "GLEIF"
        ]
        assert len(gleif_issue) == 1
        assert gleif_issue[0].required_operator == EdgeOperator.I2I

    def test_builds_framework(self):
        """Full integration: compose into GovernanceFramework and check."""
        config = vlei_standard_framework()
        fw = GovernanceFramework(
            said="Etest_vlei",
            name="vLEI Standard",
            rules=config["rules"],
            credential_matrix=config["credential_matrix"],
            authorities=config["authorities"],
        )
        checker = ConstraintChecker(fw)

        # GLEIF can issue (I2I required, I2I provided)
        r = checker.check_action("issue", "GLEIF", EdgeOperator.I2I)
        assert r.allowed

        # LE cannot issue
        r = checker.check_action("issue", "LE", EdgeOperator.I2I)
        assert not r.allowed

        # Delegation depth
        r = checker.check_delegation_depth("delegate", 2)
        assert r.allowed
        r = checker.check_delegation_depth("delegate", 4)
        assert not r.allowed

    def test_compiler_accepts_framework(self):
        """Patterns work with the constraint compiler."""
        config = vlei_standard_framework()
        fw = GovernanceFramework(
            said="Etest_vlei_compile",
            name="vLEI Standard",
            rules=config["rules"],
            credential_matrix=config["credential_matrix"],
        )
        compiler = ConstraintCompiler()
        compiled = compiler.compile(fw)
        assert compiled is not None
        assert compiled.checker is not None
