# -*- encoding: utf-8 -*-
"""
Tests for KGQL Advanced Features Integration - Phase 5.4

Cross-cutting integration tests combining:
- Temporal queries (AT KEYSTATE) + governance frameworks (WITHIN FRAMEWORK)
- Trust path analysis + operator filtering via governance
- End-to-end: parse → plan → temporal resolve → governance check → path analysis
"""

import pytest

from kgql.parser.ast import (
    KGQLQuery,
    KeyStateContext,
    GovernanceContext,
    MatchOperation,
    NodePattern,
    WhereClause,
    Condition,
    Comparator,
    VerifyOperation,
    EdgeOperator,
)
from kgql.translator.planner import QueryPlanner, MethodType
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
    CredentialMatrixEntry,
    FrameworkVersion,
)
from kgql.governance.resolver import FrameworkResolver, VersionChain
from kgql.governance.checker import ConstraintChecker
from kgql.governance.compiler import ConstraintCompiler
from kgql.temporal.resolver import KeyStateResolver, KeyStateSnapshot
from kgql.temporal.verifier import TemporalVerifier
from kgql.trust_path.analyzer import TrustPathAnalyzer, VerifiedPath, PathStep


# ── Combined Temporal + Governance Tests ─────────────────────────────


class TestTemporalGovernanceIntegration:
    """AT KEYSTATE combined with WITHIN FRAMEWORK."""

    def test_planner_emits_both_steps(self):
        """Both KEVER_STATE and FRAMEWORK_LOAD appear in correct order."""
        query = KGQLQuery(
            keystate_context=KeyStateContext(aid="EAID_Issuer", seq=5),
            governance_context=GovernanceContext(framework="EFrameworkSAID"),
            match=MatchOperation(
                patterns=[(NodePattern(variable="c", node_type="Credential"), None)]
            ),
            where=WhereClause(conditions=[
                Condition(field="c.issuer", comparator=Comparator.EQ, value="EAID...")
            ]),
        )
        planner = QueryPlanner()
        plan = planner.plan(query)

        # KEVER_STATE first, then FRAMEWORK_LOAD
        assert plan.steps[0].method_type == MethodType.KEVER_STATE
        assert plan.steps[1].method_type == MethodType.FRAMEWORK_LOAD
        assert plan.framework_said == "EFrameworkSAID"

    def test_temporal_verify_with_governance_check(self):
        """Verify credential at historical key state, then check governance."""
        # Set up key state resolver
        ks_resolver = KeyStateResolver()
        ks_resolver.register(KeyStateSnapshot(
            aid="EAID_Issuer", seq=3, keys=["key_v2"],
        ))

        # Set up governance
        fw = GovernanceFramework(
            said="EFW_SAID",
            name="Test Framework",
            rules=[
                ConstraintRule(
                    name="i2i-required",
                    applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                    enforcement=RuleEnforcement.STRICT,
                ),
            ],
        )
        checker = ConstraintChecker(fw)

        # Step 1: Temporal verification
        verifier = TemporalVerifier(ks_resolver)
        temporal_result = verifier.verify_at_keystate(
            credential_said="ECred_123",
            issuer_aid="EAID_Issuer",
            seq=3,
        )
        assert temporal_result.valid is True
        assert temporal_result.snapshot.keys == ["key_v2"]

        # Step 2: Governance check on the edge
        gov_result = checker.check_edge("iss", EdgeOperator.I2I)
        assert gov_result.allowed is True

        # Step 3: Combined check — weaker operator fails governance
        gov_fail = checker.check_edge("iss", EdgeOperator.NI2I)
        assert gov_fail.allowed is False

    def test_versioned_framework_at_keystate(self):
        """Use pinned framework version with temporal key state."""
        # Framework v1 allows NI2I, v2 requires I2I
        resolver = FrameworkResolver()
        fw_v1 = GovernanceFramework(
            said="EFW_V1",
            name="FW v1",
            version_info=FrameworkVersion(said="EFW_V1", version="1.0.0"),
            rules=[
                ConstraintRule(
                    name="r1", applies_to="iss",
                    required_operator=EdgeOperator.NI2I,
                ),
            ],
        )
        fw_v2 = GovernanceFramework(
            said="EFW_V2",
            name="FW v2",
            version_info=FrameworkVersion(
                said="EFW_V2", version="2.0.0", supersedes_said="EFW_V1",
            ),
            rules=[
                ConstraintRule(
                    name="r1", applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                ),
            ],
        )
        resolver.register(fw_v1)
        resolver.register(fw_v2)

        # At the time of key state seq=3, framework v1 was active
        # Pin to v1 for historical accuracy
        pinned = resolver.resolve("EFW_V1")
        checker = ConstraintChecker(pinned)

        # NI2I was sufficient under v1
        result = checker.check_edge("iss", EdgeOperator.NI2I)
        assert result.allowed is True

        # But current active (v2) requires I2I
        active = resolver.resolve_active("EFW_V1")
        active_checker = ConstraintChecker(active)
        result = active_checker.check_edge("iss", EdgeOperator.NI2I)
        assert result.allowed is False


# ── Trust Path + Governance Tests ────────────────────────────────────


class TestTrustPathGovernanceIntegration:
    """Trust paths filtered by governance framework constraints."""

    def _build_governed_graph(self):
        """Graph where governance constrains which paths are valid."""
        return {
            "ROOT": [
                ("QVI_A", "iss", EdgeOperator.I2I, None),
                ("QVI_B", "iss", EdgeOperator.DI2I, None),
            ],
            "QVI_A": [
                ("LE_1", "iss", EdgeOperator.DI2I, None),
            ],
            "QVI_B": [
                ("LE_1", "iss", EdgeOperator.NI2I, None),
            ],
            "LE_1": [],
        }

    def test_governance_filters_trust_paths(self):
        """Only paths satisfying governance operator requirements."""
        graph = self._build_governed_graph()
        analyzer = TrustPathAnalyzer(
            neighbor_fn=lambda said: graph.get(said, [])
        )

        # Framework requires DI2I for iss edges
        # ROOT->QVI_A(I2I)->LE_1(DI2I) — all satisfy DI2I
        # ROOT->QVI_B(DI2I)->LE_1(NI2I) — NI2I doesn't satisfy DI2I
        paths = analyzer.find_paths(
            "ROOT", "LE_1",
            operator_filter=EdgeOperator.DI2I,
        )
        assert len(paths) == 1
        assert paths[0].steps[0].target_said == "QVI_A"

    def test_compiled_framework_with_path_analysis(self):
        """Compile framework, then analyze paths with governance."""
        fw = GovernanceFramework(
            said="EFW_Path",
            name="Path Governance",
            rules=[
                ConstraintRule(
                    name="di2i-required",
                    applies_to="iss",
                    required_operator=EdgeOperator.DI2I,
                    enforcement=RuleEnforcement.STRICT,
                    field_constraints={
                        "jurisdiction": "$issuer.jurisdiction == $subject.country",
                    },
                ),
            ],
        )
        compiler = ConstraintCompiler()
        compiled = compiler.compile(fw)

        # Check each step of a path against governance
        path = VerifiedPath(
            steps=[
                PathStep("ROOT", "QVI_A", "iss", EdgeOperator.I2I),
                PathStep("QVI_A", "LE_1", "iss", EdgeOperator.DI2I),
            ],
            root_said="ROOT",
            target_said="LE_1",
        )

        # Verify each step
        for step in path.steps:
            result = compiled.check_edge_with_context(
                step.edge_type, step.operator,
                context={
                    "issuer": {"jurisdiction": "US"},
                    "subject": {"country": "US"},
                },
            )
            assert result.allowed is True


# ── Temporal + Trust Path Tests ──────────────────────────────────────


class TestTemporalTrustPath:
    """Trust paths verified at historical key states."""

    def test_path_steps_verified_at_keystate(self):
        """Each step in a trust path is verified at the temporal anchor."""
        ks_resolver = KeyStateResolver()
        ks_resolver.register(KeyStateSnapshot(
            aid="ROOT_AID", seq=5, keys=["root_key"],
        ))
        ks_resolver.register(KeyStateSnapshot(
            aid="QVI_AID", seq=3, keys=["qvi_key"],
        ))
        ks_resolver.register(KeyStateSnapshot(
            aid="LE_AID", seq=1, keys=["le_key"],
        ))
        verifier = TemporalVerifier(ks_resolver)

        # Simulate verifying each edge at the issuer's key state
        edges = [
            ("E_Edge_1", "ROOT_AID", "QVI_AID", 5),
            ("E_Edge_2", "QVI_AID", "LE_AID", 3),
        ]

        for edge_said, issuer, subject, seq in edges:
            result = verifier.check_edge_at_keystate(
                edge_said=edge_said,
                issuer_aid=issuer,
                subject_aid=subject,
                seq=seq,
            )
            assert result.valid is True, f"Edge {edge_said} failed temporal check"


# ── Full End-to-End Integration ──────────────────────────────────────


class TestEndToEndAdvanced:
    """Full pipeline: parse → plan → governance + temporal + path."""

    def test_full_pipeline_governance_temporal(self):
        """
        Simulate the full execution flow:
        1. Parse query with AT KEYSTATE + WITHIN FRAMEWORK
        2. Planner produces steps
        3. Resolve key state
        4. Load governance framework
        5. Compile framework
        6. Verify credentials at key state with governance
        """
        # 1. Build query AST
        query = KGQLQuery(
            keystate_context=KeyStateContext(aid="EAID_Root", seq=10),
            governance_context=GovernanceContext(framework="EFW_vLEI"),
            verify=VerifyOperation(said="ECred_Target"),
        )

        # 2. Plan
        planner = QueryPlanner()
        plan = planner.plan(query)
        assert plan.steps[0].method_type == MethodType.KEVER_STATE
        assert plan.steps[1].method_type == MethodType.FRAMEWORK_LOAD
        assert plan.steps[2].method_type == MethodType.VERIFIER_CHAIN

        # 3. Resolve key state
        ks_resolver = KeyStateResolver()
        ks_resolver.register(KeyStateSnapshot(
            aid="EAID_Root", seq=10, keys=["signing_key_v10"],
        ))
        snapshot = ks_resolver.resolve("EAID_Root", seq=10)
        assert snapshot is not None
        assert snapshot.keys == ["signing_key_v10"]

        # 4. Load governance framework
        fw = GovernanceFramework(
            said="EFW_vLEI",
            name="vLEI Framework",
            rules=[
                ConstraintRule(
                    name="strict-iss",
                    applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                ),
            ],
            credential_matrix=[
                CredentialMatrixEntry("issue", "QVI", EdgeOperator.I2I, True),
                CredentialMatrixEntry("issue", "Agent", EdgeOperator.ANY, False),
            ],
        )

        # 5. Compile
        compiler = ConstraintCompiler()
        compiled = compiler.compile(fw)

        # 6. Verify: I2I operator passes governance
        result = compiled.checker.check_edge("iss", EdgeOperator.I2I)
        assert result.allowed is True
        assert result.framework_said == "EFW_vLEI"

        # 6b. Verify: Agent cannot issue
        action_result = compiled.checker.check_action(
            "issue", "Agent", EdgeOperator.I2I
        )
        assert action_result.allowed is False

    def test_path_with_governance_and_temporal(self):
        """Trust path where each step is temporally and governance verified."""
        # Governance: requires DI2I minimum
        fw = GovernanceFramework(
            said="EFW_Combo",
            name="Combo FW",
            rules=[
                ConstraintRule(
                    name="di2i-min",
                    applies_to="iss",
                    required_operator=EdgeOperator.DI2I,
                ),
            ],
        )
        checker = ConstraintChecker(fw)

        # Temporal: key states exist
        ks_resolver = KeyStateResolver()
        for aid in ["ROOT", "MID", "TARGET"]:
            ks_resolver.register(KeyStateSnapshot(
                aid=aid, seq=1, keys=[f"{aid}_key"],
            ))
        verifier = TemporalVerifier(ks_resolver)

        # Trust path: ROOT -> MID -> TARGET
        path = VerifiedPath(
            steps=[
                PathStep("ROOT", "MID", "iss", EdgeOperator.I2I),
                PathStep("MID", "TARGET", "iss", EdgeOperator.DI2I),
            ],
            root_said="ROOT",
            target_said="TARGET",
        )

        # Verify each step: governance + temporal
        for step in path.steps:
            # Governance check
            gov_result = checker.check_edge(step.edge_type, step.operator)
            assert gov_result.allowed is True, (
                f"Governance failed at {step.source_said} -> {step.target_said}"
            )

            # Temporal check
            temp_result = verifier.check_edge_at_keystate(
                edge_said=f"E_{step.source_said}_{step.target_said}",
                issuer_aid=step.source_said,
                subject_aid=step.target_said,
                seq=1,
            )
            assert temp_result.valid is True, (
                f"Temporal check failed at {step.source_said} -> {step.target_said}"
            )
