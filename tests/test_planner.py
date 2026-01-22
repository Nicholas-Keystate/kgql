"""
Tests for KGQL Query Planner.

Tests the translation of KGQL AST to keripy method calls.
"""

import pytest

from kgql.parser import parse
from kgql.translator import QueryPlanner, ExecutionPlan, MethodType


class TestQueryPlanner:
    """Tests for QueryPlanner class."""

    @pytest.fixture
    def planner(self):
        """Create a planner instance."""
        return QueryPlanner()

    # --- MATCH operation planning ---

    def test_plan_match_by_issuer(self, planner):
        """Test planning MATCH with issuer condition."""
        query = parse("MATCH (c:Credential) WHERE c.issuer = 'EAID123'")
        plan = planner.plan(query)

        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) >= 1

        # Should use issus index
        step = plan.steps[0]
        assert step.method_type == MethodType.REGER_INDEX
        assert step.args.get("index") == "issus"
        assert step.args.get("keys") == "EAID123"

    def test_plan_match_by_subject(self, planner):
        """Test planning MATCH with subject condition."""
        query = parse("MATCH (c:Credential) WHERE c.subject = 'EAID456'")
        plan = planner.plan(query)

        step = plan.steps[0]
        assert step.method_type == MethodType.REGER_INDEX
        assert step.args.get("index") == "subjs"

    def test_plan_match_by_schema(self, planner):
        """Test planning MATCH with schema condition."""
        query = parse("MATCH (c:Credential) WHERE c.schema = 'ESchemaSAID'")
        plan = planner.plan(query)

        step = plan.steps[0]
        assert step.method_type == MethodType.REGER_INDEX
        assert step.args.get("index") == "schms"

    def test_plan_match_with_edge_adds_verification(self, planner):
        """Test that edge operator adds verification step."""
        query = parse("MATCH (s:Session)-[:has_turn @I2I]->(t:Turn)")
        plan = planner.plan(query)

        # Should have verification step
        verify_steps = [s for s in plan.steps if s.method_type == MethodType.VERIFIER_CHAIN]
        assert len(verify_steps) >= 1

    def test_plan_match_without_index(self, planner):
        """Test planning MATCH without indexed field falls back to scan."""
        query = parse("MATCH (c:Credential)")
        plan = planner.plan(query)

        step = plan.steps[0]
        assert step.method_type == MethodType.REGER_INDEX
        assert step.method_name == "getItemIter"

    # --- RESOLVE operation planning ---

    def test_plan_resolve(self, planner):
        """Test planning RESOLVE operation."""
        query = parse("RESOLVE 'ESAID123'")
        plan = planner.plan(query)

        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.method_type == MethodType.REGER_CLONE
        assert step.method_name == "cloneCred"
        assert step.args.get("said") == "ESAID123"

    def test_plan_resolve_with_variable(self, planner):
        """Test RESOLVE with variable reference."""
        query = parse("RESOLVE $said")
        plan = planner.plan(query)

        step = plan.steps[0]
        assert step.args.get("is_variable") is True

    # --- TRAVERSE operation planning ---

    def test_plan_traverse(self, planner):
        """Test planning TRAVERSE operation."""
        query = parse("TRAVERSE FROM 'ESAID123' FOLLOW edge")
        plan = planner.plan(query)

        # Should have clone step then sources step
        assert len(plan.steps) >= 2

        clone_step = plan.steps[0]
        assert clone_step.method_type == MethodType.REGER_CLONE

        sources_step = plan.steps[1]
        assert sources_step.method_type == MethodType.REGER_SOURCES
        assert sources_step.method_name == "sources"

    def test_plan_traverse_with_target(self, planner):
        """Test TRAVERSE with target constraint."""
        query = parse("TRAVERSE FROM 'ESAID123' TO 'ESAID456' VIA -[:edge]->")
        plan = planner.plan(query)

        sources_step = [s for s in plan.steps if s.method_type == MethodType.REGER_SOURCES][0]
        assert sources_step.args.get("target_said") == "ESAID456"

    # --- VERIFY operation planning ---

    def test_plan_verify(self, planner):
        """Test planning VERIFY operation."""
        query = parse("VERIFY 'ESAID123'")
        plan = planner.plan(query)

        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.method_type == MethodType.VERIFIER_CHAIN
        assert step.method_name == "verifyChain"
        assert step.args.get("said") == "ESAID123"

    def test_plan_verify_with_keystate(self, planner):
        """Test VERIFY with keystate context."""
        query = parse("VERIFY 'ESAID123' AGAINST aid='EAID456', seq=5")
        plan = planner.plan(query)

        step = plan.steps[0]
        assert step.args.get("keystate_aid") == "EAID456"
        assert step.args.get("keystate_seq") == 5

    # --- Modifier planning ---

    def test_plan_with_limit(self, planner):
        """Test that LIMIT is captured in plan."""
        query = parse("MATCH (c:Credential) LIMIT 10")
        plan = planner.plan(query)

        assert plan.limit == 10

    def test_plan_with_order_by(self, planner):
        """Test that ORDER BY is captured in plan."""
        query = parse("MATCH (c:Credential) ORDER BY c.created DESC")
        plan = planner.plan(query)

        assert plan.order_by == "c.created"
        assert plan.order_direction == "DESC"

    def test_plan_with_proof(self, planner):
        """Test that WITH PROOF is captured in plan."""
        query = parse("MATCH (c:Credential) WITH PROOF")
        plan = planner.plan(query)

        assert plan.include_proof is True

    def test_plan_return_fields(self, planner):
        """Test that RETURN fields are captured."""
        query = parse("MATCH (c:Credential) RETURN c.issuer, c.subject")
        plan = planner.plan(query)

        assert "c.issuer" in plan.return_fields
        assert "c.subject" in plan.return_fields


class TestExecutionPlan:
    """Tests for ExecutionPlan class."""

    def test_add_step(self):
        """Test adding steps to a plan."""
        plan = ExecutionPlan()
        from kgql.translator.planner import PlanStep

        step = PlanStep(
            method_type=MethodType.REGER_INDEX,
            method_name="getIter",
            args={"index": "issus"},
            result_key="result"
        )

        idx = plan.add_step(step)
        assert idx == 0
        assert len(plan.steps) == 1

    def test_step_dependencies(self):
        """Test that step dependencies are tracked."""
        plan = ExecutionPlan()
        from kgql.translator.planner import PlanStep

        step1 = PlanStep(
            method_type=MethodType.REGER_CLONE,
            method_name="cloneCred",
            result_key="cred"
        )
        idx1 = plan.add_step(step1)

        step2 = PlanStep(
            method_type=MethodType.REGER_SOURCES,
            method_name="sources",
            depends_on=[idx1]
        )
        plan.add_step(step2)

        assert plan.steps[1].depends_on == [0]
