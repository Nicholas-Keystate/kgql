# -*- encoding: utf-8 -*-
"""
Tests for KGQL Temporal Module - Phase 5.1

Tests AT KEYSTATE temporal query execution:
- KeyStateSnapshot data model
- KeyStateResolver with caching
- TemporalVerifier credential verification against historical key states
- Planner integration with KEVER_STATE steps
"""

import pytest

from kgql.parser.ast import (
    KGQLQuery,
    KeyStateContext,
    MatchOperation,
    NodePattern,
    WhereClause,
    Condition,
    Comparator,
    VerifyOperation,
    EdgeOperator,
)
from kgql.translator.planner import QueryPlanner, MethodType
from kgql.temporal.resolver import KeyStateResolver, KeyStateSnapshot
from kgql.temporal.verifier import TemporalVerifier, TemporalCheckResult


# ── KeyStateSnapshot Tests ───────────────────────────────────────────


class TestKeyStateSnapshot:
    """Key state snapshot data model."""

    def test_basic_snapshot(self):
        snap = KeyStateSnapshot(
            aid="EAID_123",
            seq=3,
            keys=["key1", "key2"],
            ndigs=["dig1", "dig2"],
            tholder="2",
        )
        assert snap.aid == "EAID_123"
        assert snap.seq == 3
        assert len(snap.keys) == 2
        assert snap.is_delegated is False

    def test_delegated_snapshot(self):
        snap = KeyStateSnapshot(
            aid="EAID_123",
            seq=5,
            keys=["key1"],
            delpre="EDelegate_AID",
        )
        assert snap.is_delegated is True
        assert snap.delpre == "EDelegate_AID"

    def test_cache_key(self):
        snap = KeyStateSnapshot(aid="EAID_123", seq=3)
        assert snap.cache_key == ("EAID_123", 3)

    def test_to_dict(self):
        snap = KeyStateSnapshot(
            aid="EAID_123",
            seq=3,
            keys=["key1"],
            tholder="1",
            delpre="EDelPre",
        )
        d = snap.to_dict()
        assert d["aid"] == "EAID_123"
        assert d["seq"] == 3
        assert d["keys"] == ["key1"]
        assert d["tholder"] == "1"
        assert d["delpre"] == "EDelPre"

    def test_to_dict_no_delpre(self):
        snap = KeyStateSnapshot(aid="EAID_123", seq=0, keys=[])
        d = snap.to_dict()
        assert "delpre" not in d

    def test_not_delegated_empty_delpre(self):
        snap = KeyStateSnapshot(aid="EAID_123", seq=0, delpre="")
        assert snap.is_delegated is False


# ── KeyStateResolver Tests ───────────────────────────────────────────


class TestKeyStateResolver:
    """Key state resolver with caching."""

    def test_resolve_with_getter(self):
        """Resolves key state via getter function."""
        class MockKever:
            def __init__(self):
                self.sn = 3
                self.prefixer = type('P', (), {'qb64': 'EAID_123'})()
                self.verfers = []
                self.ndigers = []
                self.tholder = None
                self.delpre = None

        def getter(aid, seq):
            if aid == "EAID_123":
                return MockKever()
            return None

        resolver = KeyStateResolver(kever_getter=getter)
        snap = resolver.resolve("EAID_123", seq=3)
        assert snap is not None
        assert snap.aid == "EAID_123"
        assert snap.seq == 3

    def test_resolve_not_found(self):
        resolver = KeyStateResolver(kever_getter=lambda aid, seq: None)
        assert resolver.resolve("EAID_MISSING", seq=0) is None

    def test_resolve_no_getter(self):
        resolver = KeyStateResolver()
        assert resolver.resolve("EAID_123", seq=0) is None

    def test_register_and_resolve(self):
        resolver = KeyStateResolver()
        snap = KeyStateSnapshot(aid="EAID_123", seq=5, keys=["k1"])
        resolver.register(snap)
        result = resolver.resolve("EAID_123", seq=5)
        assert result is snap

    def test_caching(self):
        call_count = 0

        class MockKever:
            def __init__(self):
                self.sn = 2
                self.prefixer = type('P', (), {'qb64': 'EAID_123'})()
                self.verfers = []
                self.ndigers = []
                self.tholder = None
                self.delpre = None

        def getter(aid, seq):
            nonlocal call_count
            call_count += 1
            return MockKever()

        resolver = KeyStateResolver(kever_getter=getter)
        resolver.resolve("EAID_123", seq=2)
        resolver.resolve("EAID_123", seq=2)
        assert call_count == 1  # Second call hits cache

    def test_is_cached(self):
        resolver = KeyStateResolver()
        snap = KeyStateSnapshot(aid="EAID_123", seq=5, keys=[])
        resolver.register(snap)
        assert resolver.is_cached("EAID_123", 5)
        assert not resolver.is_cached("EAID_123", 6)

    def test_clear_cache(self):
        resolver = KeyStateResolver()
        snap = KeyStateSnapshot(aid="EAID_123", seq=5, keys=[])
        resolver.register(snap)
        resolver.clear_cache()
        assert not resolver.is_cached("EAID_123", 5)


# ── TemporalVerifier Tests ──────────────────────────────────────────


class TestTemporalVerifier:
    """Temporal verification against historical key states."""

    @pytest.fixture
    def resolver_with_states(self):
        resolver = KeyStateResolver()
        # AID at seq=1: one key
        resolver.register(KeyStateSnapshot(
            aid="EAID_Issuer", seq=1, keys=["key_v1"],
        ))
        # AID at seq=3: rotated key
        resolver.register(KeyStateSnapshot(
            aid="EAID_Issuer", seq=3, keys=["key_v2"],
        ))
        # Subject AID
        resolver.register(KeyStateSnapshot(
            aid="EAID_Subject", seq=0, keys=["subj_key"],
        ))
        return resolver

    def test_verify_keystate_exists(self, resolver_with_states):
        verifier = TemporalVerifier(resolver_with_states)
        result = verifier.verify_at_keystate(
            credential_said="ECred_123",
            issuer_aid="EAID_Issuer",
            seq=3,
        )
        assert result.valid is True
        assert result.snapshot.seq == 3
        assert result.snapshot.keys == ["key_v2"]

    def test_verify_keystate_not_found(self, resolver_with_states):
        verifier = TemporalVerifier(resolver_with_states)
        result = verifier.verify_at_keystate(
            credential_said="ECred_123",
            issuer_aid="EAID_Missing",
            seq=1,
        )
        assert result.valid is False
        assert "not found" in result.message

    def test_verify_with_verify_fn_success(self, resolver_with_states):
        verifier = TemporalVerifier(resolver_with_states)
        result = verifier.verify_at_keystate(
            credential_said="ECred_123",
            issuer_aid="EAID_Issuer",
            seq=1,
            verify_fn=lambda said, keys: keys == ["key_v1"],
        )
        assert result.valid is True

    def test_verify_with_verify_fn_failure(self, resolver_with_states):
        """Verify against wrong key state version → fails."""
        verifier = TemporalVerifier(resolver_with_states)
        # Credential signed with key_v1 but verifying at seq=3 (key_v2)
        result = verifier.verify_at_keystate(
            credential_said="ECred_123",
            issuer_aid="EAID_Issuer",
            seq=3,
            verify_fn=lambda said, keys: keys == ["key_v1"],  # expects v1
        )
        assert result.valid is False
        assert result.snapshot.keys == ["key_v2"]

    def test_verify_fn_exception(self, resolver_with_states):
        verifier = TemporalVerifier(resolver_with_states)
        result = verifier.verify_at_keystate(
            credential_said="ECred_123",
            issuer_aid="EAID_Issuer",
            seq=1,
            verify_fn=lambda said, keys: (_ for _ in ()).throw(ValueError("bad")),
        )
        assert result.valid is False
        assert "error" in result.message.lower()

    def test_check_edge_at_keystate(self, resolver_with_states):
        verifier = TemporalVerifier(resolver_with_states)
        result = verifier.check_edge_at_keystate(
            edge_said="EEdge_123",
            issuer_aid="EAID_Issuer",
            subject_aid="EAID_Subject",
            seq=3,
        )
        assert result.valid is True
        assert result.snapshot.seq == 3

    def test_check_edge_issuer_missing(self, resolver_with_states):
        verifier = TemporalVerifier(resolver_with_states)
        result = verifier.check_edge_at_keystate(
            edge_said="EEdge_123",
            issuer_aid="EAID_Missing",
            subject_aid="EAID_Subject",
            seq=1,
        )
        assert result.valid is False
        assert "Issuer" in result.message

    def test_check_edge_subject_missing(self):
        resolver = KeyStateResolver()
        resolver.register(KeyStateSnapshot(
            aid="EAID_Issuer", seq=1, keys=["k1"],
        ))
        verifier = TemporalVerifier(resolver)
        result = verifier.check_edge_at_keystate(
            edge_said="EEdge_123",
            issuer_aid="EAID_Issuer",
            subject_aid="EAID_Missing",
            seq=1,
        )
        assert result.valid is False
        assert "Subject" in result.message

    def test_result_to_dict(self, resolver_with_states):
        verifier = TemporalVerifier(resolver_with_states)
        result = verifier.verify_at_keystate(
            credential_said="ECred_123",
            issuer_aid="EAID_Issuer",
            seq=1,
        )
        d = result.to_dict()
        assert d["valid"] is True
        assert d["credential_said"] == "ECred_123"
        assert d["keystate"]["aid"] == "EAID_Issuer"
        assert d["keystate"]["seq"] == 1


# ── Planner Integration Tests ───────────────────────────────────────


class TestPlannerKeystateIntegration:
    """Planner emits KEVER_STATE step for AT KEYSTATE queries."""

    def test_plan_with_keystate_context(self):
        query = KGQLQuery(
            keystate_context=KeyStateContext(aid="EAID_123", seq=5),
            match=MatchOperation(
                patterns=[(NodePattern(variable="c", node_type="Credential"), None)]
            ),
            where=WhereClause(conditions=[
                Condition(field="c.issuer", comparator=Comparator.EQ, value="EAID...")
            ]),
        )
        planner = QueryPlanner()
        plan = planner.plan(query)

        # KEVER_STATE should be first step
        assert plan.steps[0].method_type == MethodType.KEVER_STATE
        assert plan.steps[0].args["aid"] == "EAID_123"
        assert plan.steps[0].args["seq"] == 5
        assert plan.steps[0].result_key == "keystate_snapshot"

    def test_plan_without_keystate_context(self):
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

        for step in plan.steps:
            assert step.method_type != MethodType.KEVER_STATE

    def test_plan_keystate_before_framework(self):
        """KEVER_STATE comes before FRAMEWORK_LOAD."""
        query = KGQLQuery(
            keystate_context=KeyStateContext(aid="EAID_123", seq=2),
            governance_context=type('GC', (), {'framework': 'EFW_SAID'})(),
            match=MatchOperation(
                patterns=[(NodePattern(variable="c", node_type="Credential"), None)]
            ),
            where=WhereClause(conditions=[
                Condition(field="c.issuer", comparator=Comparator.EQ, value="EAID...")
            ]),
        )
        planner = QueryPlanner()
        plan = planner.plan(query)

        assert plan.steps[0].method_type == MethodType.KEVER_STATE
        assert plan.steps[1].method_type == MethodType.FRAMEWORK_LOAD

    def test_plan_verify_with_keystate(self):
        """VERIFY operation uses keystate from AGAINST clause."""
        query = KGQLQuery(
            verify=VerifyOperation(
                said="ECred_SAID",
                against_keystate=KeyStateContext(aid="EAID_123", seq=7),
            ),
        )
        planner = QueryPlanner()
        plan = planner.plan(query)

        # Find the verifier step
        verify_step = next(
            s for s in plan.steps if s.method_type == MethodType.VERIFIER_CHAIN
        )
        assert verify_step.args["keystate_aid"] == "EAID_123"
        assert verify_step.args["keystate_seq"] == 7

    def test_plan_keystate_seq_none(self):
        """AT KEYSTATE without seq → current key state."""
        query = KGQLQuery(
            keystate_context=KeyStateContext(aid="EAID_123"),
            match=MatchOperation(
                patterns=[(NodePattern(variable="c", node_type="Credential"), None)]
            ),
            where=WhereClause(conditions=[
                Condition(field="c.issuer", comparator=Comparator.EQ, value="EAID...")
            ]),
        )
        planner = QueryPlanner()
        plan = planner.plan(query)

        ks_step = plan.steps[0]
        assert ks_step.args["aid"] == "EAID_123"
        assert ks_step.args["seq"] is None
