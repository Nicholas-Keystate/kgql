# -*- encoding: utf-8 -*-
"""
Schema-Driven Index Generator.

Based on Phil Feairheller's KERIA Seeker pattern from keria/db/basing.py.

Generates LMDB indices from credential schemas by:
1. Parsing schema to find indexable (scalar) fields
2. Creating composite indices for efficient querying
3. Supporting field_path, schema+field, issuer+field combinations
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional, Any


class FieldType(str, Enum):
    """Indexable field types from JSON Schema."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"


@dataclass
class IndexDefinition:
    """
    Definition for a single index on a credential field.

    Supports composite indices like KERIA's Seeker:
    - field only: enables queries by field value
    - schema + field: namespace by schema
    - issuer + field: namespace by issuer
    - issuer + schema + field: full namespacing
    """
    field: str                          # Field name/path (e.g., "personLegalName")
    schema: str                         # Schema SAID
    field_type: FieldType               # Type for index encoding
    field_path: list[str] = field(default_factory=list)  # Path for nested fields

    @property
    def index_name(self) -> str:
        """Generate index name for LMDB."""
        # Simple: use field name
        if not self.field_path:
            return f"idx_{self.field}"
        # Nested: use path
        return f"idx_{'_'.join(self.field_path)}"

    @property
    def schema_qualified_name(self) -> str:
        """Index name qualified by schema SAID."""
        return f"{self.schema[:16]}.{self.index_name}"

    def key_for_value(self, value: Any, issuer: Optional[str] = None) -> bytes:
        """
        Generate index key for a value.

        Args:
            value: Field value to index
            issuer: Optional issuer AID for namespace

        Returns:
            Bytes key suitable for LMDB ordering
        """
        # Encode based on type for proper sort order
        if self.field_type == FieldType.STRING:
            encoded = str(value).encode("utf-8")
        elif self.field_type in (FieldType.NUMBER, FieldType.INTEGER):
            # Use fixed-width encoding for numeric sort
            encoded = f"{float(value):020.6f}".encode("utf-8")
        elif self.field_type == FieldType.BOOLEAN:
            encoded = b"1" if value else b"0"
        else:
            encoded = str(value).encode("utf-8")

        # Optionally prefix with issuer for namespacing
        if issuer:
            return f"{issuer[:16]}|".encode("utf-8") + encoded
        return encoded


class SchemaIndexer:
    """
    Generate indices from credential schemas.

    Following Phil Feairheller's KERIA pattern:
    - Parse JSON Schema to find scalar fields
    - Create IndexDefinition for each indexable field
    - Support nested field paths (a.d, a.LEI, etc.)

    Example:
        >>> indexer = SchemaIndexer()
        >>> schema = {...}  # ACDC credential schema
        >>> for idx_def in indexer.generate_indexes("ESCHEMA...", schema):
        ...     print(idx_def.field, idx_def.field_type)
    """

    # Types that can be efficiently indexed
    INDEXABLE_TYPES = {
        "string": FieldType.STRING,
        "number": FieldType.NUMBER,
        "integer": FieldType.INTEGER,
        "boolean": FieldType.BOOLEAN,
    }

    # Fields to skip indexing (internal ACDC structure)
    SKIP_FIELDS = {"d", "u"}  # SAID and salt

    def generate_indexes(
        self,
        schema_said: str,
        schema: dict,
    ) -> Iterator[IndexDefinition]:
        """
        Parse schema and generate index definitions for scalar fields.

        Args:
            schema_said: SAID of the schema
            schema: JSON Schema dict

        Yields:
            IndexDefinition for each indexable field
        """
        # Get properties from schema
        properties = schema.get("properties", {})

        # Focus on attribute section ("a" field in ACDC)
        attr_def = properties.get("a", {})
        attr_props = attr_def.get("properties", {})

        # Generate indices for scalar fields in attributes
        for field_name, field_def in attr_props.items():
            # Skip internal fields
            if field_name in self.SKIP_FIELDS:
                continue

            # Check if indexable type
            field_type_str = field_def.get("type")
            if field_type_str in self.INDEXABLE_TYPES:
                yield IndexDefinition(
                    field=field_name,
                    schema=schema_said,
                    field_type=self.INDEXABLE_TYPES[field_type_str],
                    field_path=["a", field_name],
                )

            # Handle nested objects one level deep
            elif field_type_str == "object":
                nested_props = field_def.get("properties", {})
                for nested_name, nested_def in nested_props.items():
                    nested_type = nested_def.get("type")
                    if nested_type in self.INDEXABLE_TYPES:
                        yield IndexDefinition(
                            field=f"{field_name}.{nested_name}",
                            schema=schema_said,
                            field_type=self.INDEXABLE_TYPES[nested_type],
                            field_path=["a", field_name, nested_name],
                        )

        # Also index edge references if present in schema
        edge_def = properties.get("e", {})
        edge_props = edge_def.get("properties", {})

        for edge_name, edge_def_inner in edge_props.items():
            if edge_name == "d":
                continue  # Skip edges SAID
            # Index edge existence (for fast edge traversal)
            yield IndexDefinition(
                field=f"edge.{edge_name}",
                schema=schema_said,
                field_type=FieldType.STRING,
                field_path=["e", edge_name, "d"],  # Path to target SAID
            )

    def get_indexable_fields(self, schema: dict) -> list[str]:
        """
        Get list of indexable field names from schema.

        Args:
            schema: JSON Schema dict

        Returns:
            List of field names that can be indexed
        """
        fields = []
        properties = schema.get("properties", {})
        attr_props = properties.get("a", {}).get("properties", {})

        for field_name, field_def in attr_props.items():
            if field_name not in self.SKIP_FIELDS:
                field_type = field_def.get("type")
                if field_type in self.INDEXABLE_TYPES:
                    fields.append(field_name)
                elif field_type == "object":
                    nested_props = field_def.get("properties", {})
                    for nested_name, nested_def in nested_props.items():
                        if nested_def.get("type") in self.INDEXABLE_TYPES:
                            fields.append(f"{field_name}.{nested_name}")

        return fields
