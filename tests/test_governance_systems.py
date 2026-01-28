# -*- encoding: utf-8 -*-
"""
Tests for KGQL Governance Systems Registry.

Verifies that all 8 workspace governance systems produce valid
GovernanceFramework configurations that work with ConstraintChecker.
"""

import pytest
from kgql.parser.ast import EdgeOperator
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    CredentialMatrixEntry,
)
from kgql.governance.checker import ConstraintChecker
from kgql.governance.compiler import ConstraintCompiler
from kgql.governance.resolver import FrameworkResolver
from kgql.governance.systems import (
    SYSTEM_CATALOG,
    build_framework,
    build_all_frameworks,
    register_all_frameworks,
    build_claudemd_framework,
    build_daid_framework,
    build_skill_framework,
    build_artifact_framework,
    build_deliberation_framework,
    build_plan_framework,
    build_kgql_framework,
    build_stack_framework,
)


STEWARD = "Etest_steward_aid_00000000000000000000"


# ---------------------------------------------------------------------------
# Catalog Tests
# ---------------------------------------------------------------------------

class TestSystemCatalog:

    def test_has_8_entries(self):
        assert len(SYSTEM_CATALOG) == 8

    def test_all_slugs_present(self):
        expected = {
            "claudemd", "daid", "skill", "artifact",
            "deliberation", "plan", "kgql", "stack",
        }
        assert set(SYSTEM_CATALOG.keys()) == expected

    def test_entries_have_required_fields(self):
        for slug, entry in SYSTEM_CATALOG.items():
            assert entry.name, f"{slug} missing name"
            assert entry.slug, f"{slug} missing slug"
            assert entry.description, f"{slug} missing description"
            assert entry.governance_mode, f"{slug} missing governance_mode"
            assert entry.authorization_model, f"{slug} missing authorization_model"


# ---------------------------------------------------------------------------
# Builder Tests (parametrized across all 8 systems)
# ---------------------------------------------------------------------------

@pytest.fixture(params=[
    "claudemd", "daid", "skill", "artifact",
    "deliberation", "plan", "kgql", "stack",
])
def system_framework(request):
    """Build a framework for each system."""
    return request.param, build_framework(request.param, STEWARD)


class TestAllSystems:

    def test_produces_governance_framework(self, system_framework):
        slug, fw = system_framework
        assert isinstance(fw, GovernanceFramework), f"{slug} did not produce GovernanceFramework"

    def test_has_said(self, system_framework):
        slug, fw = system_framework
        assert fw.said.startswith("E"), f"{slug} SAID doesn't start with E"

    def test_has_steward(self, system_framework):
        slug, fw = system_framework
        assert fw.steward == STEWARD, f"{slug} steward mismatch"

    def test_has_version(self, system_framework):
        slug, fw = system_framework
        assert fw.version == "1.0.0", f"{slug} version mismatch"

    def test_has_rules(self, system_framework):
        slug, fw = system_framework
        assert len(fw.rules) > 0, f"{slug} has no rules"
        assert all(isinstance(r, ConstraintRule) for r in fw.rules)

    def test_has_matrix(self, system_framework):
        slug, fw = system_framework
        assert len(fw.credential_matrix) > 0, f"{slug} has no credential matrix"
        assert all(isinstance(e, CredentialMatrixEntry) for e in fw.credential_matrix)

    def test_checker_works(self, system_framework):
        slug, fw = system_framework
        checker = ConstraintChecker(fw)
        assert checker.framework_said == fw.said

    def test_compiler_works(self, system_framework):
        slug, fw = system_framework
        compiler = ConstraintCompiler()
        compiled = compiler.compile(fw)
        assert compiled is not None

    def test_unique_saids(self):
        """All 8 systems produce distinct SAIDs."""
        frameworks = build_all_frameworks(STEWARD)
        saids = [fw.said for fw in frameworks.values()]
        assert len(set(saids)) == 8, "Framework SAIDs are not unique"


# ---------------------------------------------------------------------------
# System-Specific Behavioral Tests
# ---------------------------------------------------------------------------

class TestClaudemdGovernance:

    def test_master_can_rotate(self):
        fw = build_claudemd_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("rotate", "master", EdgeOperator.I2I)
        assert result.allowed

    def test_session_cannot_rotate(self):
        fw = build_claudemd_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("rotate", "session", EdgeOperator.I2I)
        assert not result.allowed

    def test_external_cannot_rotate(self):
        fw = build_claudemd_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("rotate", "external", EdgeOperator.I2I)
        assert not result.allowed

    def test_session_can_read(self):
        fw = build_claudemd_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("read", "session", EdgeOperator.NI2I)
        assert result.allowed


class TestDAIDGovernance:

    def test_controller_can_rotate(self):
        fw = build_daid_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("rotate", "controller", EdgeOperator.DI2I)
        assert result.allowed

    def test_reader_cannot_rotate(self):
        fw = build_daid_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("rotate", "reader", EdgeOperator.DI2I)
        assert not result.allowed

    def test_delegation_depth_limit(self):
        fw = build_daid_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_delegation_depth("delegate", 4)
        assert not result.allowed


class TestSkillGovernance:

    def test_controller_can_activate(self):
        fw = build_skill_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("activate", "controller", EdgeOperator.I2I)
        assert result.allowed

    def test_executor_cannot_activate(self):
        fw = build_skill_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("activate", "executor", EdgeOperator.I2I)
        assert not result.allowed

    def test_executor_can_execute(self):
        fw = build_skill_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("execute", "executor", EdgeOperator.NI2I)
        assert result.allowed


class TestDeliberationGovernance:

    def test_proposer_can_propose(self):
        fw = build_deliberation_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("propose", "proposer", EdgeOperator.NI2I)
        assert result.allowed

    def test_proposer_cannot_ratify(self):
        fw = build_deliberation_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("ratify", "proposer", EdgeOperator.I2I)
        assert not result.allowed

    def test_voter_can_support(self):
        fw = build_deliberation_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("support", "voter", EdgeOperator.DI2I)
        assert result.allowed


class TestPlanGovernance:

    def test_master_can_create(self):
        fw = build_plan_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("create", "master", EdgeOperator.I2I)
        assert result.allowed

    def test_collaborator_cannot_create(self):
        fw = build_plan_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("create", "collaborator", EdgeOperator.I2I)
        assert not result.allowed

    def test_collaborator_can_read(self):
        fw = build_plan_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("read", "collaborator", EdgeOperator.NI2I)
        assert result.allowed


class TestKGQLSelfGovernance:

    def test_steward_can_evolve(self):
        fw = build_kgql_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("evolve", "steward", EdgeOperator.I2I)
        assert result.allowed

    def test_checker_cannot_evolve(self):
        fw = build_kgql_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("evolve", "checker", EdgeOperator.I2I)
        assert not result.allowed

    def test_querier_can_query(self):
        fw = build_kgql_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("query", "querier", EdgeOperator.NI2I)
        assert result.allowed


class TestStackGovernance:

    def test_master_can_delegate(self):
        fw = build_stack_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("delegate", "master", EdgeOperator.I2I)
        assert result.allowed

    def test_session_cannot_delegate(self):
        fw = build_stack_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("delegate", "session", EdgeOperator.I2I)
        assert not result.allowed

    def test_session_can_attest(self):
        fw = build_stack_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("attest", "session", EdgeOperator.DI2I)
        assert result.allowed

    def test_session_cannot_issue_external(self):
        fw = build_stack_framework(STEWARD)
        checker = ConstraintChecker(fw)
        result = checker.check_action("issue_external", "session", EdgeOperator.I2I)
        assert not result.allowed


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestBuildAllFrameworks:

    def test_returns_8_frameworks(self):
        frameworks = build_all_frameworks(STEWARD)
        assert len(frameworks) == 8

    def test_all_keys_match_catalog(self):
        frameworks = build_all_frameworks(STEWARD)
        assert set(frameworks.keys()) == set(SYSTEM_CATALOG.keys())


class TestRegisterAllFrameworks:

    def test_registers_in_resolver(self):
        resolver = FrameworkResolver()
        saids = register_all_frameworks(resolver, STEWARD)

        assert len(saids) == 8
        for slug, said in saids.items():
            resolved = resolver.resolve(said)
            assert resolved is not None, f"{slug} not resolvable"

    def test_all_saids_resolvable(self):
        resolver = FrameworkResolver()
        saids = register_all_frameworks(resolver, STEWARD)

        for said in saids.values():
            fw = resolver.resolve(said)
            assert fw is not None
            checker = ConstraintChecker(fw)
            assert checker.framework_said == said


class TestBuildFrameworkBySlug:

    def test_valid_slug(self):
        fw = build_framework("claudemd", STEWARD)
        assert fw.name == "CLAUDE.md Governance"

    def test_invalid_slug_raises(self):
        with pytest.raises(KeyError, match="Unknown system"):
            build_framework("nonexistent", STEWARD)

    def test_custom_version(self):
        fw = build_framework("daid", STEWARD, version="2.0.0")
        assert fw.version == "2.0.0"
