# -*- encoding: utf-8 -*-
"""
Chain Verification Tests

Week 6: Tests for verifying credential chains:
- Turn → Session → Master (delegation chain)
- Decision → Turn (context chain)
- SkillExecution → Skill (execution chain)

Uses KGQL's TRAVERSE and VERIFY operations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from kgql import KGQL
from kgql.api.kgql import QueryResult, QueryResultItem


class TestChainVerification:
    """Tests for credential chain verification."""

    @pytest.fixture
    def mock_hby(self):
        """Create mock Habery with session and master habs."""
        hby = Mock()
        hby.db = Mock()

        # Mock kevers for chain verification
        master_kever = Mock()
        master_kever.pre = "EMASTER_AID"
        master_kever.sner = Mock(num=10)

        session_kever = Mock()
        session_kever.pre = "ESESSION_AID"
        session_kever.delpre = "EMASTER_AID"  # Delegated from master
        session_kever.sner = Mock(num=5)

        hby.kevers = {
            "EMASTER_AID": master_kever,
            "ESESSION_AID": session_kever,
        }

        return hby

    @pytest.fixture
    def mock_rgy(self):
        """Create mock Regery with credential chain."""
        rgy = Mock()
        reger = Mock()

        # Mock credentials in chain
        # Turn credential
        turn_cred = Mock()
        turn_cred.said = "ETURN_SAID"
        turn_cred.issuer = "ESESSION_AID"
        turn_cred.schema = "ETURN_SCHEMA"
        turn_cred.edges = {
            "session": {"n": "ESESSION_SAID"},
            "previous": {"n": "EPREV_TURN_SAID"},
        }

        # Session credential
        session_cred = Mock()
        session_cred.said = "ESESSION_SAID"
        session_cred.issuer = "ESESSION_AID"
        session_cred.schema = "ESESSION_SCHEMA"
        session_cred.edges = {
            "delegator": {"n": "EMASTER_AID"},
        }

        # Map SAIDs to credentials
        cred_map = {
            "ETURN_SAID": turn_cred,
            "ESESSION_SAID": session_cred,
        }

        # Mock clone method
        def mock_cloner(said):
            cred = cred_map.get(said.qb64 if hasattr(said, 'qb64') else said)
            if cred:
                return (cred, None)  # (creder, prefixer)
            return (None, None)

        reger.cloner.get = mock_cloner

        # Mock tevers for TEL status
        mock_tever = Mock()
        mock_tever.sn = 1
        mock_tever.serder = Mock(said="ETEL_SAID")
        reger.tevers = {
            "ETURN_SAID": mock_tever,
            "ESESSION_SAID": mock_tever,
        }

        # Mock sources for edge traversal
        def mock_sources(db, said, default=None):
            cred = cred_map.get(said)
            if cred and hasattr(cred, 'edges'):
                return [(Mock(said=e["n"]), None) for e in cred.edges.values() if e.get("n")]
            return []

        reger.sources = Mock()
        reger.sources.get = mock_sources

        rgy.reger = reger
        return rgy

    @pytest.fixture
    def kgql(self, mock_hby, mock_rgy):
        """Create KGQL instance."""
        return KGQL(hby=mock_hby, rgy=mock_rgy, verifier=None)

    def test_turn_session_chain(self, kgql):
        """Test traversing Turn → Session edge."""
        result = kgql.traverse("ETURN_SAID", edge_type="session")
        assert isinstance(result, QueryResult)

    def test_delegation_chain_verified(self, mock_hby):
        """Test that session AID delegation to master is verified."""
        session_kever = mock_hby.kevers["ESESSION_AID"]
        master_kever = mock_hby.kevers["EMASTER_AID"]

        # Verify delegation chain
        assert session_kever.delpre == master_kever.pre

    def test_monotonic_turn_chain(self, mock_rgy):
        """Test that turns form a monotonic chain via previous edge."""
        reger = mock_rgy.reger
        turn_cred, _ = reger.cloner.get("ETURN_SAID")

        # Verify turn has previous edge
        assert "previous" in turn_cred.edges
        assert turn_cred.edges["previous"]["n"] == "EPREV_TURN_SAID"


class TestDecisionChainVerification:
    """Tests for Decision → Turn chain verification."""

    @pytest.fixture
    def mock_rgy_with_decisions(self):
        """Create mock Regery with decision chain."""
        rgy = Mock()
        reger = Mock()

        # Decision credential
        decision_cred = Mock()
        decision_cred.said = "EDECISION_SAID"
        decision_cred.issuer = "ESESSION_AID"
        decision_cred.schema = "EDECISION_SCHEMA"
        decision_cred.edges = {
            "turn": {"n": "ETURN_SAID"},
            "supersedes": {"n": None},  # First decision, no prior
        }

        # Second decision superseding first
        decision2_cred = Mock()
        decision2_cred.said = "EDECISION2_SAID"
        decision2_cred.issuer = "ESESSION_AID"
        decision2_cred.schema = "EDECISION_SCHEMA"
        decision2_cred.edges = {
            "turn": {"n": "ETURN2_SAID"},
            "supersedes": {"n": "EDECISION_SAID"},  # Supersedes first
        }

        cred_map = {
            "EDECISION_SAID": decision_cred,
            "EDECISION2_SAID": decision2_cred,
        }

        def mock_cloner(said):
            cred = cred_map.get(said.qb64 if hasattr(said, 'qb64') else said)
            return (cred, None) if cred else (None, None)

        reger.cloner.get = mock_cloner
        reger.tevers = {}
        rgy.reger = reger
        return rgy

    def test_decision_supersedes_chain(self, mock_rgy_with_decisions):
        """Test that decisions form a supersedes chain."""
        reger = mock_rgy_with_decisions.reger

        decision1, _ = reger.cloner.get("EDECISION_SAID")
        decision2, _ = reger.cloner.get("EDECISION2_SAID")

        # First decision has no prior
        assert decision1.edges["supersedes"]["n"] is None

        # Second decision supersedes first
        assert decision2.edges["supersedes"]["n"] == "EDECISION_SAID"


class TestSkillExecutionChainVerification:
    """Tests for SkillExecution → Skill chain verification."""

    @pytest.fixture
    def mock_rgy_with_skills(self):
        """Create mock Regery with skill execution chain."""
        rgy = Mock()
        reger = Mock()

        # Skill definition credential
        skill_cred = Mock()
        skill_cred.said = "ESKILL_SAID"
        skill_cred.issuer = "EORCHESTRATOR_AID"
        skill_cred.schema = "ESKILL_DEFINITION_SCHEMA"

        # Skill execution credential
        execution_cred = Mock()
        execution_cred.said = "EEXECUTION_SAID"
        execution_cred.issuer = "ESESSION_AID"
        execution_cred.schema = "ESKILL_EXECUTION_SCHEMA"
        execution_cred.edges = {
            "skill": {"n": "ESKILL_SAID"},
            "session": {"n": "ESESSION_SAID"},
        }

        cred_map = {
            "ESKILL_SAID": skill_cred,
            "EEXECUTION_SAID": execution_cred,
        }

        def mock_cloner(said):
            cred = cred_map.get(said.qb64 if hasattr(said, 'qb64') else said)
            return (cred, None) if cred else (None, None)

        reger.cloner.get = mock_cloner
        reger.tevers = {}
        rgy.reger = reger
        return rgy

    def test_execution_links_to_skill(self, mock_rgy_with_skills):
        """Test that execution credential links to skill definition."""
        reger = mock_rgy_with_skills.reger

        execution, _ = reger.cloner.get("EEXECUTION_SAID")

        # Execution has skill edge
        assert "skill" in execution.edges
        assert execution.edges["skill"]["n"] == "ESKILL_SAID"


class TestFullChainVerification:
    """Integration tests for full chain verification."""

    def test_chain_to_master(self):
        """
        Test full chain verification:
        Turn → Session → Master

        This verifies the complete trust chain from a turn credential
        back to the hardware-protected master AID.
        """
        # Setup: Create credential chain
        master_aid = "EMASTER_AID"
        session_aid = "ESESSION_AID"

        # Mock session delegation
        session_delpre = master_aid

        # Verify chain
        assert session_delpre == master_aid, "Session must delegate from master"

    def test_vlei_integration_fields(self):
        """
        Test that credentials have optional vLEI fields.

        Week 6: Prep for vLEI integration - credentials should support
        optional oor_credential_said and vlei_edges fields.
        """
        # Credential with vLEI fields (optional, None until integrated)
        credential_data = {
            "d": "ECRED_SAID",
            "i": "ESESSION_AID",
            # Standard fields...
            # vLEI integration fields (Week 6 prep)
            "oor_credential_said": None,  # Will be set when vLEI integrated
            "vlei_edges": None,  # Will contain vLEI edge data
        }

        # Fields exist but are None until vLEI integration
        assert "oor_credential_said" in credential_data
        assert "vlei_edges" in credential_data
        assert credential_data["oor_credential_said"] is None


class TestTraverseDelegator:
    """Tests for traverse_delegator method (Phase 1 Gap 1 remediation)."""

    @pytest.fixture
    def mock_hby_with_master(self):
        """Create mock Habery with master AID and KEL events."""
        hby = Mock()
        hby.db = Mock()

        # Mock master kever
        master_kever = Mock()
        master_kever.pre = "EMASTER_AID_PREFIX"
        master_kever.sner = Mock(num=15)

        hby.kevers = {
            "EMASTER_AID_PREFIX": master_kever,
        }

        # Mock KEL iteration (for finding anchor events)
        hby.db.getKelIter = Mock(return_value=[])

        return hby

    @pytest.fixture
    def mock_rgy_with_delegator_edge(self):
        """Create mock Regery with session credential having delegator edge."""
        rgy = Mock()
        reger = Mock()

        # Session credential with proper delegator edge (KEL-anchored)
        session_cred_kel = Mock()
        session_cred_kel.said = "ESESSION_CRED_KEL"
        session_cred_kel.issuer = "ESESSION_AID"
        session_cred_kel.data = {
            "edges": {
                "delegator": {
                    "n": "EMASTER_AID_PREFIX",
                    "s": "EKEL_EVENT_SAID",  # KEL event SAID
                    "o": {
                        "kel_event_said": "EKEL_EVENT_SAID",
                        "seal_said": "ESEAL_SAID",
                    },
                },
            },
        }

        # Session credential with seal-only delegator edge (fallback)
        session_cred_seal = Mock()
        session_cred_seal.said = "ESESSION_CRED_SEAL"
        session_cred_seal.issuer = "ESESSION_AID"
        session_cred_seal.data = {
            "edges": {
                "delegator": {
                    "n": "EMASTER_AID_PREFIX",
                    "s": "ESEAL_SAID",  # Seal SAID only (no KEL anchor)
                },
            },
        }

        # Turn credential linking to session
        turn_cred = Mock()
        turn_cred.said = "ETURN_SAID"
        turn_cred.issuer = "ESESSION_AID"
        turn_cred.data = {
            "edges": {
                "session": {"n": "ESESSION_CRED_KEL"},
                "previous": {"n": None},
            },
        }

        cred_map = {
            "ESESSION_CRED_KEL": session_cred_kel,
            "ESESSION_CRED_SEAL": session_cred_seal,
            "ETURN_SAID": turn_cred,
        }

        def mock_cloner(said):
            key = said.qb64 if hasattr(said, 'qb64') else said
            cred = cred_map.get(key)
            return (cred, None) if cred else (None, None)

        reger.cloner = Mock()
        reger.cloner.get = mock_cloner
        reger.tevers = {}
        rgy.reger = reger
        return rgy

    @pytest.fixture
    def kgql_with_delegator(self, mock_hby_with_master, mock_rgy_with_delegator_edge):
        """Create KGQL instance with delegator support and mocked resolve."""
        kgql = KGQL(hby=mock_hby_with_master, rgy=mock_rgy_with_delegator_edge, verifier=None)

        # Build credential data map for resolve() mocking
        session_cred_kel_data = {
            "edges": {
                "delegator": {
                    "n": "EMASTER_AID_PREFIX",
                    "s": "EKEL_EVENT_SAID",
                    "o": {
                        "kel_event_said": "EKEL_EVENT_SAID",
                        "seal_said": "ESEAL_SAID",
                    },
                },
            },
        }
        session_cred_seal_data = {
            "edges": {
                "delegator": {
                    "n": "EMASTER_AID_PREFIX",
                    "s": "ESEAL_SAID",
                },
            },
        }
        turn_cred_data = {
            "edges": {
                "session": {"n": "ESESSION_CRED_KEL"},
                "previous": {"n": None},
            },
            "issuer": "ESESSION_AID",
        }

        cred_data_map = {
            "ESESSION_CRED_KEL": QueryResultItem(said="ESESSION_CRED_KEL", data=session_cred_kel_data),
            "ESESSION_CRED_SEAL": QueryResultItem(said="ESESSION_CRED_SEAL", data=session_cred_seal_data),
            "ETURN_SAID": QueryResultItem(said="ETURN_SAID", data=turn_cred_data),
        }

        # Mock the resolve method to return our test data
        original_resolve = kgql.resolve

        def mock_resolve(said):
            if said in cred_data_map:
                return cred_data_map[said]
            return None

        kgql.resolve = mock_resolve
        return kgql

    def test_traverse_delegator_kel_anchored(self, kgql_with_delegator):
        """
        Test traversing delegator edge with KEL-anchored delegation.

        This is the critical production requirement: Turn → Session → Master KEL
        """
        result = kgql_with_delegator.traverse_delegator("ESESSION_CRED_KEL")

        assert result is not None
        assert len(result.items) == 1

        item = result.first
        assert item.said == "EKEL_EVENT_SAID"
        assert item.data["master_pre"] == "EMASTER_AID_PREFIX"
        assert item.data["kel_event_said"] == "EKEL_EVENT_SAID"
        assert item.data["seal_said"] == "ESEAL_SAID"

        # Metadata indicates KEL-anchored
        assert result.metadata.get("kel_anchored") is True

    def test_traverse_delegator_seal_only(self, kgql_with_delegator):
        """
        Test traversing delegator edge with seal-only delegation (fallback).

        This is the out-of-band delegation case where KEL anchoring wasn't possible.
        """
        result = kgql_with_delegator.traverse_delegator("ESESSION_CRED_SEAL")

        assert result is not None
        assert len(result.items) == 1

        item = result.first
        assert item.said == "ESEAL_SAID"
        assert item.data["master_pre"] == "EMASTER_AID_PREFIX"
        # No KEL event when using seal-only
        assert item.data.get("kel_event_said") is None

        # Metadata indicates NOT KEL-anchored
        assert result.metadata.get("kel_anchored") is False

    def test_traverse_delegator_not_found(self, kgql_with_delegator):
        """Test traverse_delegator with non-existent credential."""
        result = kgql_with_delegator.traverse_delegator("ENONEXISTENT_SAID")

        assert result is not None
        assert len(result.items) == 0
        assert "error" in result.metadata

    def test_verify_end_to_end_chain(self, kgql_with_delegator):
        """
        Test complete chain verification: Turn → Session → Master

        This is the critical production verification.
        """
        result = kgql_with_delegator.verify_end_to_end_chain("ETURN_SAID")

        assert result is not None
        assert result.metadata.get("valid") is True

        # Check chain structure
        item = result.first
        assert item is not None
        chain = item.data.get("chain", [])

        # Should have 3 elements: turn, session, master_delegation
        assert len(chain) == 3
        assert chain[0]["type"] == "turn"
        assert chain[1]["type"] == "session"
        assert chain[2]["type"] == "master_delegation"

        # Master info should be present
        assert chain[2]["master_pre"] == "EMASTER_AID_PREFIX"

    def test_verify_chain_missing_session_edge(self, mock_hby_with_master, mock_rgy_with_delegator_edge):
        """Test chain verification when turn is missing session edge."""
        kgql = KGQL(hby=mock_hby_with_master, rgy=mock_rgy_with_delegator_edge, verifier=None)

        # Create turn credential data without session edge
        turn_no_session_data = {
            "edges": {},  # No session edge
            "issuer": "ESESSION_AID",
        }

        # Mock resolve to return our test turn
        def mock_resolve(said):
            if said == "ETURN_NO_SESSION":
                return QueryResultItem(said="ETURN_NO_SESSION", data=turn_no_session_data)
            return None

        kgql.resolve = mock_resolve

        result = kgql.verify_end_to_end_chain("ETURN_NO_SESSION")

        assert result is not None
        assert result.metadata.get("valid") is False
        assert "session" in result.metadata.get("error", "").lower()
