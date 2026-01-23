# -*- encoding: utf-8 -*-
"""
Schema-Driven Indexer for KGQL.

Based on Phil Feairheller's KERIA Seeker pattern:
- Dynamic index generation from credential schemas
- Query operators ($eq, $begins, etc.)
- Composite indices (field, schema+field, issuer+field)
"""

from kgql.indexer.schema_indexer import (
    SchemaIndexer,
    IndexDefinition,
    FieldType,
)
from kgql.indexer.query_operators import (
    QueryOperator,
    Eq,
    Begins,
    Lt,
    Gt,
    Lte,
    Gte,
    Contains,
    parse_query_value,
)
from kgql.indexer.query_engine import (
    QueryEngine,
    Query,
    QueryResult,
    create_query_engine,
)

__all__ = [
    # Indexer
    "SchemaIndexer",
    "IndexDefinition",
    "FieldType",
    # Operators
    "QueryOperator",
    "Eq",
    "Begins",
    "Lt",
    "Gt",
    "Lte",
    "Gte",
    "Contains",
    "parse_query_value",
    # Query Engine
    "QueryEngine",
    "Query",
    "QueryResult",
    "create_query_engine",
]
