# -*- encoding: utf-8 -*-
"""
Tests for KGQL Governance Execution - Phase 4.2

Tests the WITHIN FRAMEWORK query execution pipeline:
- Planner emits FRAMEWORK_LOAD step for governance context
- Executor loads framework and attaches ConstraintChecker
- Governance metadata appears in query results
"""

import pytest

from kgql.parser.ast import (
    KGQLQuery,
    GovernanceContext,
    MatchOperation,
    NodePattern,
    WhereClause,
    Condition,
    Comparator,
    EdgeOperator,
)
from kgql.translator.planner import QueryPlanner, MethodType, ExecutionPlan
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
    CredentialMatrixEntry,
    FrameworkVersion,
)
from kgql.governance.resolver import FrameworkResolver
from kgql.governance.checker import ConstraintChecker


# ── Planner Tests ─────────────────────────────────────────────────────


class TestPlannerGovernanceContext:
    """Planner emits FRAMEWORK_LOAD step when governance context present."""

    def test_plan_with_governance_context(self):
        """WITHIN FRAMEWORK adds FRAMEWORK_LOAD as first step."""
        query = KGQLQuery(
            governance_context=GovernanceContext(framework="EFrameworkSAID123"),
            match=MatchOperation(
                patterns=[(NodePattern(variable="c", node_type="Credential"), None)]
            ),
            where=WhereClause(conditions=[
                Condition(field="c.issuer", comparator=Comparator.EQ, value="EAID...")
            ]),
        )
        planner = QueryPlanner()
        plan = planner.plan(query)

        assert plan.framework_said == "EFrameworkSAID123"
        assert len(plan.steps) >= 2  # FRAMEWORK_LOAD + index query
        assert plan.steps[0].method_type == MethodType.FRAMEWORK_LOAD
        assert plan.steps[0].args["framework_said"] == "EFrameworkSAID123"
        assert plan.steps[0].result_key == "governance_framework"

    def test_plan_without_governance_context(self):
        """No FRAMEWORK_LOAD step when no governance context."""
        query = KGQLQuery(
            match=MatchOperation(
                patterns=[(NodePattern(variable="c", node_type="Credential"), None)]
            ),
            where=WhereClause(conditions=[
                Condition(field="c.issuer", comparator=Comparator.EQ, value="EAID...")
            ]),
        )
        planner = QueryPlanner()
        plan = planner.plan(query)

        assert plan.framework_said is None
        for step in plan.steps:
            assert step.method_type != MethodType.FRAMEWORK_LOAD

    def test_framework_said_on_execution_plan(self):
        plan = ExecutionPlan(framework_said="ESAID123")
        assert plan.framework_said == "ESAID123"

    def test_framework_said_default_none(self):
        plan = ExecutionPlan()
        assert plan.framework_said is None


# ── FrameworkResolver Integration ─────────────────────────────────────


class TestFrameworkResolverIntegration:
    """FrameworkResolver wired into the execution pipeline."""

    def test_resolver_with_registered_framework(self):
        fw = GovernanceFramework(
            said="ETestFramework123",
            name="Test Framework",
            version_info=FrameworkVersion(said="ETestFramework123", version="1.0.0"),
            rules=[
                ConstraintRule(
                    name="strict-issuance",
                    applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                    enforcement=RuleEnforcement.STRICT,
                ),
            ],
            credential_matrix=[
                CredentialMatrixEntry(
                    action="issue", role="QVI",
                    required_operator=EdgeOperator.I2I, allowed=True,
                ),
                CredentialMatrixEntry(
                    action="issue", role="Agent",
                    required_operator=EdgeOperator.ANY, allowed=False,
                ),
            ],
        )

        resolver = FrameworkResolver()
        resolver.register(fw)

        # Simulate what executor does
        loaded = resolver.resolve("ETestFramework123")
        assert loaded is fw

        checker = ConstraintChecker(loaded)
        assert checker.framework_said == "ETestFramework123"

        # Check edge passes
        result = checker.check_edge("iss", EdgeOperator.I2I)
        assert result.allowed is True

        # Check edge fails (NI2I < I2I)
        result = checker.check_edge("iss", EdgeOperator.NI2I)
        assert result.allowed is False

    def test_resolver_returns_none_for_unknown(self):
        resolver = FrameworkResolver()
        assert resolver.resolve("EUnknown") is None


# ── ConstraintChecker Wiring ──────────────────────────────────────────


class TestCheckerInExecutionContext:
    """ConstraintChecker correctly evaluates in query execution context."""

    @pytest.fixture
    def checker(self):
        fw = GovernanceFramework(
            said="EVLEIFramework",
            name="vLEI",
            rules=[
                ConstraintRule(
                    name="qvi-i2i",
                    applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                ),
                ConstraintRule(
                    name="depth-limit",
                    applies_to="delegation",
                    required_operator=EdgeOperator.DI2I,
                    max_delegation_depth=4,
                ),
            ],
            credential_matrix=[
                CredentialMatrixEntry("issue", "QVI", EdgeOperator.I2I, True),
                CredentialMatrixEntry("issue", "Agent", EdgeOperator.ANY, False),
                CredentialMatrixEntry("query", "Agent", EdgeOperator.ANY, True),
            ],
        )
        return ConstraintChecker(fw)

    def test_edge_check_i2i_passes(self, checker):
        result = checker.check_edge("iss", EdgeOperator.I2I)
        assert result.allowed

    def test_edge_check_di2i_fails_when_i2i_required(self, checker):
        result = checker.check_edge("iss", EdgeOperator.DI2I)
        assert not result.allowed

    def test_action_issue_qvi_with_i2i(self, checker):
        result = checker.check_action("issue", "QVI", EdgeOperator.I2I)
        assert result.allowed

    def test_action_issue_agent_blocked(self, checker):
        result = checker.check_action("issue", "Agent", EdgeOperator.I2I)
        assert not result.allowed

    def test_action_query_agent_allowed(self, checker):
        result = checker.check_action("query", "Agent", EdgeOperator.ANY)
        assert result.allowed

    def test_delegation_depth_within_limit(self, checker):
        result = checker.check_delegation_depth("delegation", 3)
        assert result.allowed

    def test_delegation_depth_exceeds_limit(self, checker):
        result = checker.check_delegation_depth("delegation", 5)
        assert not result.allowed

    def test_governance_metadata_shape(self, checker):
        """Test metadata dict shape that executor attaches to results."""
        metadata = {
            "governance": {
                "framework_said": checker.framework_said,
                "framework_name": checker.framework.name,
            }
        }
        assert metadata["governance"]["framework_said"] == "EVLEIFramework"
        assert metadata["governance"]["framework_name"] == "vLEI"
