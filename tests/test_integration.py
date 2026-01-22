"""
Integration tests for KGQL.

Tests the full flow from KGQL string to execution result.
Uses mocks for keripy infrastructure.
"""

import pytest
from unittest.mock import Mock, MagicMock

from kgql import KGQL
from kgql.api.kgql import QueryResult, QueryResultItem


class TestKGQLIntegration:
    """Integration tests for KGQL class."""

    @pytest.fixture
    def mock_hby(self):
        """Create a mock Habery instance."""
        hby = Mock()
        hby.db = Mock()
        hby.kevers = {}
        return hby

    @pytest.fixture
    def mock_rgy(self):
        """Create a mock Regery instance."""
        rgy = Mock()

        # Mock reger
        reger = Mock()

        # Mock issus index with results
        mock_saider = Mock()
        mock_saider.qb64 = "ESAID_CRED_1"
        reger.issus.getIter.return_value = [mock_saider]

        # Mock subjs index
        reger.subjs.getIter.return_value = [mock_saider]

        # Mock schms index
        reger.schms.getIter.return_value = [mock_saider]

        # Mock creds
        reger.creds.get.return_value = None
        reger.creds.getItemIter.return_value = []

        rgy.reger = reger
        return rgy

    @pytest.fixture
    def mock_verifier(self):
        """Create a mock Verifier instance."""
        verifier = Mock()

        mock_result = Mock()
        mock_result.revoked = False
        mock_result.issuer = "EAID_ISSUER"
        mock_result.sn = 5
        verifier.verifyChain.return_value = mock_result

        return verifier

    @pytest.fixture
    def kgql(self, mock_hby, mock_rgy, mock_verifier):
        """Create a KGQL instance with mocks."""
        return KGQL(hby=mock_hby, rgy=mock_rgy, verifier=mock_verifier)

    # --- Query execution tests ---

    def test_query_by_issuer(self, kgql, mock_rgy):
        """Test full query execution for credentials by issuer."""
        result = kgql.query(
            "MATCH (c:Credential) WHERE c.issuer = $aid",
            variables={"aid": "EAID_TEST"}
        )

        assert isinstance(result, QueryResult)
        mock_rgy.reger.issus.getIter.assert_called_once_with(keys="EAID_TEST")

    def test_query_by_subject(self, kgql, mock_rgy):
        """Test query for credentials by subject."""
        result = kgql.query(
            "MATCH (c:Credential) WHERE c.subject = $aid",
            variables={"aid": "EAID_SUBJECT"}
        )

        assert isinstance(result, QueryResult)
        mock_rgy.reger.subjs.getIter.assert_called_once_with(keys="EAID_SUBJECT")

    def test_query_with_limit(self, kgql, mock_rgy):
        """Test that LIMIT is applied to results."""
        # Add multiple results
        mock_saiders = [Mock(qb64=f"ESAID_{i}") for i in range(5)]
        mock_rgy.reger.issus.getIter.return_value = mock_saiders

        result = kgql.query(
            "MATCH (c:Credential) WHERE c.issuer = 'EAID' LIMIT 2"
        )

        assert len(result) <= 2

    # --- Convenience method tests ---

    def test_by_issuer_method(self, kgql, mock_rgy):
        """Test the by_issuer convenience method."""
        result = kgql.by_issuer("EAID_TEST")

        assert isinstance(result, QueryResult)
        mock_rgy.reger.issus.getIter.assert_called()

    def test_by_subject_method(self, kgql, mock_rgy):
        """Test the by_subject convenience method."""
        result = kgql.by_subject("EAID_TEST")

        assert isinstance(result, QueryResult)
        mock_rgy.reger.subjs.getIter.assert_called()

    def test_resolve_method(self, kgql):
        """Test the resolve convenience method."""
        result = kgql.resolve("ESAID_TEST")

        # May be None since mock doesn't have the credential
        assert result is None or isinstance(result, QueryResultItem)

    # --- Parse and plan tests ---

    def test_parse_method(self, kgql):
        """Test the parse method returns AST."""
        ast = kgql.parse("MATCH (c:Credential) WHERE c.issuer = 'EAID'")

        assert ast.match is not None
        assert ast.where is not None

    def test_plan_method(self, kgql):
        """Test the plan method returns execution plan."""
        ast = kgql.parse("MATCH (c:Credential) WHERE c.issuer = 'EAID'")
        plan = kgql.plan(ast)

        assert len(plan.steps) >= 1

    # --- Deck integration tests ---

    def test_deck_available(self, kgql):
        """Test that Deck instances are available for async integration."""
        assert hasattr(kgql, 'queries')
        assert hasattr(kgql, 'results')


class TestQueryResult:
    """Tests for QueryResult class."""

    def test_iteration(self):
        """Test QueryResult is iterable."""
        items = [
            QueryResultItem(said="ESAID_1"),
            QueryResultItem(said="ESAID_2"),
        ]
        result = QueryResult(items=items, count=2)

        saids = [item.said for item in result]
        assert saids == ["ESAID_1", "ESAID_2"]

    def test_len(self):
        """Test len() on QueryResult."""
        items = [QueryResultItem(said="ESAID_1")]
        result = QueryResult(items=items, count=1)

        assert len(result) == 1

    def test_bool_empty(self):
        """Test bool on empty QueryResult."""
        result = QueryResult()
        assert not result

    def test_bool_non_empty(self):
        """Test bool on non-empty QueryResult."""
        result = QueryResult(items=[QueryResultItem(said="ESAID_1")])
        assert result

    def test_first(self):
        """Test first property."""
        items = [
            QueryResultItem(said="ESAID_1"),
            QueryResultItem(said="ESAID_2"),
        ]
        result = QueryResult(items=items)

        assert result.first.said == "ESAID_1"

    def test_first_empty(self):
        """Test first property on empty result."""
        result = QueryResult()
        assert result.first is None

    def test_collect_saids(self):
        """Test collect_saids method."""
        items = [
            QueryResultItem(said="ESAID_1"),
            QueryResultItem(said="ESAID_2"),
        ]
        result = QueryResult(items=items)

        saids = result.collect_saids()
        assert saids == ["ESAID_1", "ESAID_2"]


class TestEndToEnd:
    """End-to-end tests simulating real usage patterns."""

    @pytest.fixture
    def mock_infra(self):
        """Create mock infrastructure for e2e tests."""
        hby = Mock()
        hby.db = Mock()
        hby.kevers = {}

        rgy = Mock()
        reger = Mock()

        # Simulate credentials
        cred_data = {
            "ESAID_SESSION_1": {
                "said": "ESAID_SESSION_1",
                "issuer": "EAID_AGENT",
                "schema": "ESessionSchema"
            },
            "ESAID_TURN_1": {
                "said": "ESAID_TURN_1",
                "issuer": "EAID_AGENT",
                "schema": "ETurnSchema"
            }
        }

        # Mock issus to return session and turn
        def issus_getiter(keys):
            for said, data in cred_data.items():
                if data["issuer"] == keys:
                    mock = Mock()
                    mock.qb64 = said
                    yield mock

        reger.issus.getIter = issus_getiter
        reger.subjs.getIter.return_value = []
        reger.schms.getIter.return_value = []
        reger.creds.get.return_value = None
        reger.creds.getItemIter.return_value = []

        rgy.reger = reger

        verifier = Mock()
        verifier.verifyChain.return_value = Mock(revoked=False)

        return hby, rgy, verifier

    def test_query_session_turns(self, mock_infra):
        """Test querying turns for a session."""
        hby, rgy, verifier = mock_infra
        kgql = KGQL(hby=hby, rgy=rgy, verifier=verifier)

        result = kgql.query(
            "MATCH (c:Credential) WHERE c.issuer = $agent_aid",
            variables={"agent_aid": "EAID_AGENT"}
        )

        # Should find the session and turn credentials
        assert len(result) >= 1
