# -*- encoding: utf-8 -*-
"""
Query Engine for Schema-Driven Credential Queries.

Combines SchemaIndexer and QueryOperators to execute queries:
1. Parse query dict into field->operator mappings
2. Use schema to validate fields
3. Execute against credentials (with optional index acceleration)

Based on Phil Feairheller's KERIA Seeker pattern.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from kgql.indexer.schema_indexer import SchemaIndexer, IndexDefinition, FieldType
from kgql.indexer.query_operators import QueryOperator, parse_query_value

# Semantic slug generation
try:
    from agents.inference.embedding_store import generate_semantic_slug
    HAS_SLUG_GENERATOR = True
except ImportError:
    HAS_SLUG_GENERATOR = False

    def generate_semantic_slug(text: str, max_words: int = 3) -> str:
        """Fallback slug generation."""
        import re
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9]{2,}\b', text.lower())
        stopwords = {'the', 'and', 'for', 'this', 'that', 'with', 'from', 'are', 'was'}
        keywords = [w for w in words if w not in stopwords][:max_words]
        return "-".join(keywords) if keywords else ""


@dataclass
class QueryResult:
    """Result from a credential query."""
    credential: dict                    # Matched credential
    schema_said: str                    # Schema of credential
    issuer: str                         # Issuer AID
    said: str                           # Credential SAID
    matched_fields: dict = field(default_factory=dict)  # Fields that matched
    slug: str = ""                      # Semantic colloquial name

    def display_id(self) -> str:
        """Return SAID with slug for human-readable display."""
        if self.slug:
            return f"{self.said[:12]}... ({self.slug})"
        return f"{self.said[:12]}..."


@dataclass
class Query:
    """
    Parsed query ready for execution.

    Attributes:
        schema: Optional schema SAID to filter by
        issuer: Optional issuer AID to filter by
        field_conditions: Map of field -> QueryOperator
    """
    schema: Optional[str] = None
    issuer: Optional[str] = None
    field_conditions: dict[str, QueryOperator] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, query_dict: dict) -> "Query":
        """
        Parse query from dict format.

        Args:
            query_dict: Query dict like:
                {
                    "-s": "ESCHEMA...",          # Schema filter
                    "-i": "EISSUER...",          # Issuer filter
                    "personLegalName": "Alice",  # Field = value (implicit $eq)
                    "LEI": {"$begins": "US"},    # Field with operator
                }

        Returns:
            Parsed Query instance
        """
        schema = query_dict.pop("-s", None)
        issuer = query_dict.pop("-i", None)

        field_conditions = {}
        for field_name, field_value in query_dict.items():
            if not field_name.startswith("-"):  # Skip meta fields
                field_conditions[field_name] = parse_query_value(field_value)

        return cls(
            schema=schema,
            issuer=issuer,
            field_conditions=field_conditions,
        )


class QueryEngine:
    """
    Execute queries against credentials.

    Uses schema information for validation and index generation.
    Falls back to full scan when indices not available.

    Example:
        >>> engine = QueryEngine()
        >>> engine.register_schema("ESCHEMA...", schema_dict)
        >>> results = engine.query(
        ...     credentials,
        ...     {"personLegalName": "Alice", "LEI": {"$begins": "US"}}
        ... )
    """

    def __init__(self):
        self._schemas: dict[str, dict] = {}  # schema_said -> schema
        self._indexer = SchemaIndexer()
        self._indices: dict[str, list[IndexDefinition]] = {}  # schema_said -> indices

    def register_schema(self, schema_said: str, schema: dict):
        """
        Register a schema for query validation and indexing.

        Args:
            schema_said: SAID of the schema
            schema: JSON Schema dict
        """
        self._schemas[schema_said] = schema
        self._indices[schema_said] = list(
            self._indexer.generate_indexes(schema_said, schema)
        )

    def get_index_definitions(self, schema_said: str) -> list[IndexDefinition]:
        """Get index definitions for a schema."""
        return self._indices.get(schema_said, [])

    def query(
        self,
        credentials: list[dict],
        query_dict: dict,
    ) -> Iterator[QueryResult]:
        """
        Execute query against credentials.

        Args:
            credentials: List of credential dicts
            query_dict: Query dict with field conditions

        Yields:
            QueryResult for each matching credential
        """
        query = Query.from_dict(query_dict.copy())

        for cred in credentials:
            if self._matches_credential(cred, query):
                # Generate semantic slug from credential attributes
                attrs = cred.get("a", {})
                slug_source = " ".join([
                    str(attrs.get("title", "")),
                    str(attrs.get("summary", "")),
                    str(attrs.get("name", "")),
                    str(attrs.get("type", "")),
                ])
                slug = generate_semantic_slug(slug_source, max_words=3) if slug_source.strip() else ""

                yield QueryResult(
                    credential=cred,
                    schema_said=cred.get("s", ""),
                    issuer=cred.get("i", ""),
                    said=cred.get("d", ""),
                    matched_fields={
                        f: op.operator_name
                        for f, op in query.field_conditions.items()
                    },
                    slug=slug,
                )

    def _matches_credential(self, credential: dict, query: Query) -> bool:
        """Check if credential matches query conditions."""
        # Schema filter
        if query.schema and credential.get("s") != query.schema:
            return False

        # Issuer filter
        if query.issuer and credential.get("i") != query.issuer:
            return False

        # Field conditions
        attrs = credential.get("a", {})

        for field_name, operator in query.field_conditions.items():
            value = self._get_field_value(attrs, field_name)
            if value is None or not operator.matches(value):
                return False

        return True

    def _get_field_value(self, attrs: dict, field_name: str) -> Any:
        """
        Get field value from attributes, supporting nested paths.

        Args:
            attrs: Credential attributes dict
            field_name: Field name, possibly with dots (e.g., "address.city")

        Returns:
            Field value or None
        """
        if "." not in field_name:
            return attrs.get(field_name)

        # Navigate nested path
        parts = field_name.split(".")
        current = attrs
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def explain(self, query_dict: dict) -> dict:
        """
        Explain query execution plan.

        Args:
            query_dict: Query dict

        Returns:
            Explanation dict with index usage info
        """
        query = Query.from_dict(query_dict.copy())

        plan = {
            "schema_filter": query.schema,
            "issuer_filter": query.issuer,
            "field_conditions": [],
            "index_usage": [],
        }

        for field_name, operator in query.field_conditions.items():
            condition = {
                "field": field_name,
                "operator": operator.operator_name,
                "index_key": operator.index_key(),
            }
            plan["field_conditions"].append(condition)

            # Check if we have an index for this field
            if query.schema and query.schema in self._indices:
                for idx_def in self._indices[query.schema]:
                    if idx_def.field == field_name:
                        plan["index_usage"].append({
                            "field": field_name,
                            "index": idx_def.index_name,
                            "can_use_index": operator.index_key() is not None,
                        })
                        break

        return plan


# Convenience function
def create_query_engine(schemas: dict[str, dict] = None) -> QueryEngine:
    """
    Create a QueryEngine with optional pre-registered schemas.

    Args:
        schemas: Dict mapping schema_said to schema dict

    Returns:
        Configured QueryEngine
    """
    engine = QueryEngine()
    if schemas:
        for said, schema in schemas.items():
            engine.register_schema(said, schema)
    return engine
