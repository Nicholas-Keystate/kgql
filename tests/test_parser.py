"""
Tests for KGQL Parser.

Tests the Lark-based parser for KGQL query strings.
"""

import pytest

from kgql.parser import KGQLParser, parse
from kgql.parser.ast import (
    KGQLQuery,
    MatchOperation,
    ResolveOperation,
    TraverseOperation,
    VerifyOperation,
    EdgeOperator,
    Comparator,
)


class TestKGQLParser:
    """Tests for KGQLParser class."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return KGQLParser()

    # --- MATCH operation tests ---

    def test_parse_simple_match(self, parser):
        """Test parsing a simple MATCH query."""
        query = "MATCH (c:Credential)"
        result = parser.parse(query)

        assert isinstance(result, KGQLQuery)
        assert result.match is not None
        assert len(result.match.patterns) == 1

        node, edge = result.match.patterns[0]
        assert node.variable == "c"
        assert node.node_type == "Credential"

    def test_parse_match_with_where(self, parser):
        """Test MATCH with WHERE clause."""
        query = "MATCH (c:Credential) WHERE c.issuer = 'EAID123'"
        result = parser.parse(query)

        assert result.match is not None
        assert result.where is not None
        assert len(result.where.conditions) == 1

        cond = result.where.conditions[0]
        assert cond.field == "c.issuer"
        assert cond.comparator == Comparator.EQ
        assert cond.value == "EAID123"

    def test_parse_match_with_variable(self, parser):
        """Test MATCH with variable reference."""
        query = "MATCH (c:Credential) WHERE c.issuer = $aid"
        result = parser.parse(query, variables={"aid": "EAID456"})

        assert result.where is not None
        cond = result.where.conditions[0]
        assert cond.value == "$aid" or cond.value == "aid"
        assert result.variables.get("aid") == "EAID456"

    def test_parse_match_with_edge(self, parser):
        """Test MATCH with edge pattern."""
        query = "MATCH (s:Session)-[:has_turn @I2I]->(t:Turn)"
        result = parser.parse(query)

        assert result.match is not None
        patterns = result.match.patterns

        # First pattern has the edge
        node, edge = patterns[0]
        assert node.node_type == "Session"
        assert edge is not None
        assert edge.edge_type == "has_turn"
        assert edge.operator == EdgeOperator.I2I

    def test_parse_match_with_edge_operators(self, parser):
        """Test parsing different edge operators."""
        test_cases = [
            ("@I2I", EdgeOperator.I2I),
            ("@DI2I", EdgeOperator.DI2I),
            ("@NI2I", EdgeOperator.NI2I),
            ("@ANY", EdgeOperator.ANY),
        ]

        for op_str, expected_op in test_cases:
            query = f"MATCH (a)-[:{op_str}]->(b)"
            result = parser.parse(query)
            _, edge = result.match.patterns[0]
            assert edge.operator == expected_op, f"Failed for {op_str}"

    # --- RESOLVE operation tests ---

    def test_parse_resolve(self, parser):
        """Test parsing RESOLVE operation."""
        query = "RESOLVE 'ESAID123'"
        result = parser.parse(query)

        assert result.resolve is not None
        assert result.resolve.said == "ESAID123"
        assert not result.resolve.is_variable

    def test_parse_resolve_with_variable(self, parser):
        """Test RESOLVE with variable."""
        query = "RESOLVE $said"
        result = parser.parse(query)

        assert result.resolve is not None
        assert result.resolve.is_variable

    # --- TRAVERSE operation tests ---

    def test_parse_traverse(self, parser):
        """Test parsing TRAVERSE operation."""
        query = "TRAVERSE FROM 'ESAID123' TO 'ESAID456'"
        result = parser.parse(query)

        assert result.traverse is not None
        assert result.traverse.from_said == "ESAID123"
        assert result.traverse.to_said == "ESAID456"

    def test_parse_traverse_with_follow(self, parser):
        """Test TRAVERSE with FOLLOW clause."""
        query = "TRAVERSE FROM $said FOLLOW edge"
        result = parser.parse(query)

        assert result.traverse is not None
        assert result.traverse.follow_type == "edge"

    def test_parse_traverse_with_via(self, parser):
        """Test TRAVERSE with VIA clause."""
        query = "TRAVERSE FROM $said TO $target VIA -[:source @I2I]->"
        result = parser.parse(query)

        assert result.traverse is not None
        assert result.traverse.via_edge is not None
        assert result.traverse.via_edge.operator == EdgeOperator.I2I

    # --- VERIFY operation tests ---

    def test_parse_verify(self, parser):
        """Test parsing VERIFY operation."""
        query = "VERIFY 'ESAID123'"
        result = parser.parse(query)

        assert result.verify is not None
        assert result.verify.said == "ESAID123"

    def test_parse_verify_with_keystate(self, parser):
        """Test VERIFY with AGAINST clause."""
        query = "VERIFY $said AGAINST aid='EAID123', seq=5"
        result = parser.parse(query)

        assert result.verify is not None
        assert result.verify.against_keystate is not None
        assert result.verify.against_keystate.aid == "EAID123"
        assert result.verify.against_keystate.seq == 5

    # --- Context tests ---

    def test_parse_with_keystate_context(self, parser):
        """Test query with AT KEYSTATE context."""
        query = "AT KEYSTATE(aid='EAID123', seq=5) MATCH (c:Credential)"
        result = parser.parse(query)

        assert result.keystate_context is not None
        assert result.keystate_context.aid == "EAID123"
        assert result.keystate_context.seq == 5

    def test_parse_with_governance_context(self, parser):
        """Test query with WITHIN FRAMEWORK context."""
        query = "WITHIN FRAMEWORK 'vLEI' MATCH (c:Credential)"
        result = parser.parse(query)

        assert result.governance_context is not None
        assert result.governance_context.framework == "vLEI"

    # --- Modifier tests ---

    def test_parse_with_limit(self, parser):
        """Test query with LIMIT clause."""
        query = "MATCH (c:Credential) LIMIT 10"
        result = parser.parse(query)

        assert result.limit == 10

    def test_parse_with_order_by(self, parser):
        """Test query with ORDER BY clause."""
        query = "MATCH (c:Credential) ORDER BY c.created DESC"
        result = parser.parse(query)

        assert result.order_by is not None
        assert result.order_by.field == "c.created"
        assert result.order_by.direction.value == "DESC"

    def test_parse_with_proof(self, parser):
        """Test query with WITH PROOF clause."""
        query = "MATCH (c:Credential) WITH PROOF"
        result = parser.parse(query)

        assert result.with_options is not None
        assert result.with_options.include_proof is True

    # --- RETURN clause tests ---

    def test_parse_return_clause(self, parser):
        """Test RETURN clause parsing."""
        query = "MATCH (c:Credential) RETURN c"
        result = parser.parse(query)

        assert result.return_clause is not None
        assert len(result.return_clause.items) == 1
        assert result.return_clause.items[0].expression == "c"

    def test_parse_return_with_alias(self, parser):
        """Test RETURN with alias."""
        query = "MATCH (c:Credential) RETURN c.issuer AS issuer_aid"
        result = parser.parse(query)

        assert result.return_clause is not None
        item = result.return_clause.items[0]
        assert item.alias == "issuer_aid"

    def test_parse_return_with_proof(self, parser):
        """Test RETURN with PROOF expression."""
        query = "MATCH (c:Credential) WITH PROOF RETURN c, PROOF(c) AS cred_proof"
        result = parser.parse(query)

        assert result.return_clause is not None
        assert len(result.return_clause.items) == 2
        proof_item = result.return_clause.items[1]
        assert proof_item.is_proof is True
        assert proof_item.alias == "cred_proof"

    # --- Complex query tests ---

    def test_parse_complex_query(self, parser):
        """Test parsing a complex query with multiple clauses."""
        query = """
        AT KEYSTATE(aid='EAID123')
        MATCH (s:Session)-[:has_turn @I2I]->(t:Turn)
        WHERE s.said = $session_said
        WITH PROOF
        ORDER BY t.sequence DESC
        LIMIT 10
        RETURN t, PROOF(t)
        """
        result = parser.parse(query, variables={"session_said": "ESAID..."})

        assert result.keystate_context is not None
        assert result.match is not None
        assert result.where is not None
        assert result.with_options.include_proof is True
        assert result.order_by is not None
        assert result.limit == 10
        assert result.return_clause is not None


class TestParseFunction:
    """Tests for the parse() convenience function."""

    def test_parse_function(self):
        """Test the parse() function."""
        result = parse("MATCH (c:Credential)")
        assert isinstance(result, KGQLQuery)
        assert result.match is not None

    def test_parse_with_variables(self):
        """Test parse() with variables."""
        result = parse(
            "MATCH (c:Credential) WHERE c.issuer = $aid",
            variables={"aid": "EAID123"}
        )
        assert result.variables.get("aid") == "EAID123"


class TestParserErrors:
    """Tests for parser error handling."""

    @pytest.fixture
    def parser(self):
        return KGQLParser()

    def test_invalid_syntax(self, parser):
        """Test that invalid syntax raises an error."""
        with pytest.raises(Exception):
            parser.parse("INVALID QUERY SYNTAX")

    def test_incomplete_query(self, parser):
        """Test that incomplete query raises an error."""
        with pytest.raises(Exception):
            parser.parse("MATCH")

    def test_missing_node_pattern(self, parser):
        """Test missing node pattern raises error."""
        with pytest.raises(Exception):
            parser.parse("MATCH WHERE x = 1")
