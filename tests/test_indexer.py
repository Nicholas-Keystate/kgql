# -*- encoding: utf-8 -*-
"""
Tests for Schema-Driven Indexer.

Tests the Phase 2 implementation based on Phil Feairheller's KERIA Seeker pattern.
"""

import pytest

from kgql.indexer import (
    SchemaIndexer,
    IndexDefinition,
    FieldType,
    QueryOperator,
    Eq,
    Begins,
    Lt,
    Gt,
    Lte,
    Gte,
    Contains,
    parse_query_value,
    QueryEngine,
    Query,
    create_query_engine,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def person_schema():
    """vLEI-style person credential schema."""
    return {
        "$id": "EPerson_Schema_SAID",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Person Credential",
        "type": "object",
        "properties": {
            "v": {"type": "string"},
            "d": {"type": "string"},
            "i": {"type": "string"},
            "s": {"type": "string"},
            "a": {
                "type": "object",
                "properties": {
                    "d": {"type": "string"},  # SAID - should be skipped
                    "dt": {"type": "string"},
                    "personLegalName": {"type": "string"},
                    "LEI": {"type": "string"},
                    "engagementContextRole": {"type": "string"},
                    "age": {"type": "integer"},
                    "verified": {"type": "boolean"},
                    "address": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                            "country": {"type": "string"},
                        },
                    },
                },
            },
            "e": {
                "type": "object",
                "properties": {
                    "d": {"type": "string"},
                    "auth": {
                        "type": "object",
                        "properties": {
                            "d": {"type": "string"},
                            "i": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


@pytest.fixture
def sample_credentials():
    """Sample credentials for query testing."""
    return [
        {
            "v": "ACDC10JSON000197_",
            "d": "ECRED_ALICE_SAID",
            "i": "EISSUER_ACME_AID",
            "s": "EPerson_Schema_SAID",
            "a": {
                "d": "EATTRS_SAID_1",
                "dt": "2026-01-22T10:00:00Z",
                "personLegalName": "Alice Smith",
                "LEI": "USNY123456789012345678",
                "engagementContextRole": "Engineer",
                "age": 30,
                "verified": True,
                "address": {
                    "city": "New York",
                    "country": "USA",
                },
            },
        },
        {
            "v": "ACDC10JSON000197_",
            "d": "ECRED_BOB_SAID",
            "i": "EISSUER_ACME_AID",
            "s": "EPerson_Schema_SAID",
            "a": {
                "d": "EATTRS_SAID_2",
                "dt": "2026-01-21T15:30:00Z",
                "personLegalName": "Bob Johnson",
                "LEI": "GBLO987654321098765432",
                "engagementContextRole": "Manager",
                "age": 45,
                "verified": True,
                "address": {
                    "city": "London",
                    "country": "UK",
                },
            },
        },
        {
            "v": "ACDC10JSON000197_",
            "d": "ECRED_CHARLIE_SAID",
            "i": "EISSUER_GLOBEX_AID",
            "s": "EPerson_Schema_SAID",
            "a": {
                "d": "EATTRS_SAID_3",
                "dt": "2026-01-20T08:00:00Z",
                "personLegalName": "Charlie Brown",
                "LEI": "USCA111111111111111111",
                "engagementContextRole": "Engineer",
                "age": 25,
                "verified": False,
                "address": {
                    "city": "San Francisco",
                    "country": "USA",
                },
            },
        },
    ]


# =============================================================================
# SchemaIndexer Tests
# =============================================================================


class TestSchemaIndexer:
    """Tests for SchemaIndexer."""

    def test_generate_indexes_scalar_fields(self, person_schema):
        """Test that scalar fields generate index definitions."""
        indexer = SchemaIndexer()
        indices = list(indexer.generate_indexes("EPerson_Schema_SAID", person_schema))

        # Should have indices for scalar fields (excluding 'd')
        field_names = [idx.field for idx in indices]

        assert "personLegalName" in field_names
        assert "LEI" in field_names
        assert "engagementContextRole" in field_names
        assert "age" in field_names
        assert "verified" in field_names
        assert "dt" in field_names

        # Should NOT include internal SAID field
        assert "d" not in field_names

    def test_generate_indexes_nested_fields(self, person_schema):
        """Test that nested object fields are indexed."""
        indexer = SchemaIndexer()
        indices = list(indexer.generate_indexes("EPerson_Schema_SAID", person_schema))

        field_names = [idx.field for idx in indices]

        # Nested fields should have dotted notation
        assert "address.city" in field_names
        assert "address.country" in field_names

    def test_generate_indexes_edge_references(self, person_schema):
        """Test that edge references are indexed."""
        indexer = SchemaIndexer()
        indices = list(indexer.generate_indexes("EPerson_Schema_SAID", person_schema))

        field_names = [idx.field for idx in indices]

        # Edge references should be indexed
        assert "edge.auth" in field_names

    def test_index_definition_types(self, person_schema):
        """Test that index definitions have correct field types."""
        indexer = SchemaIndexer()
        indices = list(indexer.generate_indexes("EPerson_Schema_SAID", person_schema))

        type_map = {idx.field: idx.field_type for idx in indices}

        assert type_map["personLegalName"] == FieldType.STRING
        assert type_map["age"] == FieldType.INTEGER
        assert type_map["verified"] == FieldType.BOOLEAN

    def test_index_definition_names(self, person_schema):
        """Test index name generation."""
        indexer = SchemaIndexer()
        indices = list(indexer.generate_indexes("EPerson_Schema_SAID", person_schema))

        # Find personLegalName index
        name_idx = next(idx for idx in indices if idx.field == "personLegalName")

        assert name_idx.index_name == "idx_a_personLegalName"
        assert name_idx.schema_qualified_name.startswith("EPerson_Schema_")

    def test_key_for_value_string(self, person_schema):
        """Test key generation for string values."""
        indexer = SchemaIndexer()
        indices = list(indexer.generate_indexes("EPerson_Schema_SAID", person_schema))

        name_idx = next(idx for idx in indices if idx.field == "personLegalName")
        key = name_idx.key_for_value("Alice")

        assert key == b"Alice"

    def test_key_for_value_with_issuer(self, person_schema):
        """Test key generation with issuer prefix."""
        indexer = SchemaIndexer()
        indices = list(indexer.generate_indexes("EPerson_Schema_SAID", person_schema))

        name_idx = next(idx for idx in indices if idx.field == "personLegalName")
        key = name_idx.key_for_value("Alice", issuer="EISSUER_AID_123456")

        assert key.startswith(b"EISSUER_AID_1234|")
        assert b"Alice" in key

    def test_get_indexable_fields(self, person_schema):
        """Test getting list of indexable fields."""
        indexer = SchemaIndexer()
        fields = indexer.get_indexable_fields(person_schema)

        assert "personLegalName" in fields
        assert "LEI" in fields
        assert "address.city" in fields
        assert "d" not in fields  # Internal field excluded


# =============================================================================
# QueryOperator Tests
# =============================================================================


class TestQueryOperators:
    """Tests for query operators."""

    def test_eq_matches(self):
        """Test Eq operator matching."""
        op = Eq(value="Alice")

        assert op.matches("Alice") is True
        assert op.matches("Bob") is False
        assert op.matches("alice") is False  # Case sensitive

    def test_eq_index_key(self):
        """Test Eq index key generation."""
        op = Eq(value="Alice")
        assert op.index_key() == "Alice"

    def test_begins_matches(self):
        """Test Begins operator matching."""
        op = Begins(prefix="US")

        assert op.matches("USNY123456") is True
        assert op.matches("USCA999999") is True
        assert op.matches("GBLO123456") is False

    def test_begins_index_key(self):
        """Test Begins index key generation."""
        op = Begins(prefix="US")
        assert op.index_key() == "US"
        assert op.index_key_end() == "UT"  # Next char after S

    def test_lt_matches(self):
        """Test Lt operator matching."""
        op = Lt(value=30)

        assert op.matches(25) is True
        assert op.matches(30) is False
        assert op.matches(35) is False

    def test_gt_matches(self):
        """Test Gt operator matching."""
        op = Gt(value=30)

        assert op.matches(35) is True
        assert op.matches(30) is False
        assert op.matches(25) is False

    def test_lte_matches(self):
        """Test Lte operator matching."""
        op = Lte(value=30)

        assert op.matches(25) is True
        assert op.matches(30) is True
        assert op.matches(35) is False

    def test_gte_matches(self):
        """Test Gte operator matching."""
        op = Gte(value=30)

        assert op.matches(35) is True
        assert op.matches(30) is True
        assert op.matches(25) is False

    def test_contains_matches(self):
        """Test Contains operator matching."""
        op = Contains(substring="Smith")

        assert op.matches("Alice Smith") is True
        assert op.matches("Bob Johnson") is False
        assert op.matches("Smithson") is True

    def test_contains_no_index(self):
        """Test Contains has no index key."""
        op = Contains(substring="Smith")
        assert op.index_key() is None


class TestParseQueryValue:
    """Tests for parse_query_value function."""

    def test_parse_direct_value(self):
        """Test parsing direct value as Eq."""
        op = parse_query_value("Alice")
        assert isinstance(op, Eq)
        assert op.value == "Alice"

    def test_parse_eq_explicit(self):
        """Test parsing explicit $eq."""
        op = parse_query_value({"$eq": "Alice"})
        assert isinstance(op, Eq)
        assert op.value == "Alice"

    def test_parse_begins(self):
        """Test parsing $begins."""
        op = parse_query_value({"$begins": "US"})
        assert isinstance(op, Begins)
        assert op.prefix == "US"

    def test_parse_comparison_operators(self):
        """Test parsing comparison operators."""
        assert isinstance(parse_query_value({"$lt": 30}), Lt)
        assert isinstance(parse_query_value({"$gt": 30}), Gt)
        assert isinstance(parse_query_value({"$lte": 30}), Lte)
        assert isinstance(parse_query_value({"$gte": 30}), Gte)

    def test_parse_contains(self):
        """Test parsing $contains."""
        op = parse_query_value({"$contains": "Smith"})
        assert isinstance(op, Contains)
        assert op.substring == "Smith"


# =============================================================================
# Query Tests
# =============================================================================


class TestQuery:
    """Tests for Query parsing."""

    def test_from_dict_simple(self):
        """Test parsing simple query."""
        query = Query.from_dict({
            "personLegalName": "Alice",
        })

        assert query.schema is None
        assert query.issuer is None
        assert "personLegalName" in query.field_conditions
        assert isinstance(query.field_conditions["personLegalName"], Eq)

    def test_from_dict_with_filters(self):
        """Test parsing query with schema and issuer filters."""
        query = Query.from_dict({
            "-s": "ESCHEMA_SAID",
            "-i": "EISSUER_AID",
            "LEI": {"$begins": "US"},
        })

        assert query.schema == "ESCHEMA_SAID"
        assert query.issuer == "EISSUER_AID"
        assert isinstance(query.field_conditions["LEI"], Begins)


# =============================================================================
# QueryEngine Tests
# =============================================================================


class TestQueryEngine:
    """Tests for QueryEngine."""

    def test_register_schema(self, person_schema):
        """Test schema registration."""
        engine = QueryEngine()
        engine.register_schema("EPerson_Schema_SAID", person_schema)

        indices = engine.get_index_definitions("EPerson_Schema_SAID")
        assert len(indices) > 0

    def test_query_eq(self, person_schema, sample_credentials):
        """Test equality query."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {"personLegalName": "Alice Smith"},
        ))

        assert len(results) == 1
        assert results[0].said == "ECRED_ALICE_SAID"

    def test_query_begins(self, person_schema, sample_credentials):
        """Test prefix query."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {"LEI": {"$begins": "US"}},
        ))

        # Should match Alice (USNY...) and Charlie (USCA...)
        assert len(results) == 2
        saids = {r.said for r in results}
        assert "ECRED_ALICE_SAID" in saids
        assert "ECRED_CHARLIE_SAID" in saids

    def test_query_comparison(self, person_schema, sample_credentials):
        """Test comparison query."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {"age": {"$gte": 30}},
        ))

        # Should match Alice (30) and Bob (45)
        assert len(results) == 2
        saids = {r.said for r in results}
        assert "ECRED_ALICE_SAID" in saids
        assert "ECRED_BOB_SAID" in saids

    def test_query_multiple_conditions(self, person_schema, sample_credentials):
        """Test query with multiple conditions."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {
                "engagementContextRole": "Engineer",
                "age": {"$lt": 30},
            },
        ))

        # Should only match Charlie (Engineer, age 25)
        assert len(results) == 1
        assert results[0].said == "ECRED_CHARLIE_SAID"

    def test_query_nested_field(self, person_schema, sample_credentials):
        """Test query on nested field."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {"address.country": "USA"},
        ))

        # Should match Alice and Charlie
        assert len(results) == 2
        saids = {r.said for r in results}
        assert "ECRED_ALICE_SAID" in saids
        assert "ECRED_CHARLIE_SAID" in saids

    def test_query_schema_filter(self, person_schema, sample_credentials):
        """Test query with schema filter."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {
                "-s": "EPerson_Schema_SAID",
                "verified": True,
            },
        ))

        # Should match Alice and Bob (verified=True)
        assert len(results) == 2

    def test_query_issuer_filter(self, person_schema, sample_credentials):
        """Test query with issuer filter."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {
                "-i": "EISSUER_GLOBEX_AID",
            },
        ))

        # Should only match Charlie (issued by Globex)
        assert len(results) == 1
        assert results[0].said == "ECRED_CHARLIE_SAID"

    def test_query_no_matches(self, person_schema, sample_credentials):
        """Test query with no matches."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {"personLegalName": "Nonexistent Person"},
        ))

        assert len(results) == 0

    def test_explain_query(self, person_schema):
        """Test query explanation."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        plan = engine.explain({
            "-s": "EPerson_Schema_SAID",
            "personLegalName": "Alice",
            "LEI": {"$begins": "US"},
        })

        assert plan["schema_filter"] == "EPerson_Schema_SAID"
        assert len(plan["field_conditions"]) == 2

        # Check index usage for registered schema
        assert len(plan["index_usage"]) >= 1


class TestQueryEngineEdgeCases:
    """Edge case tests for QueryEngine."""

    def test_empty_credentials(self, person_schema):
        """Test query on empty credentials list."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query([], {"personLegalName": "Alice"}))
        assert len(results) == 0

    def test_missing_field(self, person_schema, sample_credentials):
        """Test query on field not present in credential."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {"nonexistentField": "value"},
        ))

        # No matches - field doesn't exist
        assert len(results) == 0

    def test_contains_operator(self, person_schema, sample_credentials):
        """Test contains operator (full scan)."""
        engine = create_query_engine({"EPerson_Schema_SAID": person_schema})

        results = list(engine.query(
            sample_credentials,
            {"personLegalName": {"$contains": "Smith"}},
        ))

        # Should match Alice Smith
        assert len(results) == 1
        assert results[0].said == "ECRED_ALICE_SAID"
