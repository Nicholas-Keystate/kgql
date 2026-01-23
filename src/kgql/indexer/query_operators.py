# -*- encoding: utf-8 -*-
"""
Query Operators for Schema-Driven Indexing.

Based on Phil Feairheller's KERIA pattern:
- $eq: Exact match (default)
- $begins: Prefix match (efficient for LMDB range scans)
- $lt, $gt, $lte, $gte: Comparisons for numeric/date fields
- $contains: Substring match (requires full scan)

Example query structure:
    {
        "personLegalName": "Alice",                    # $eq implicit
        "LEI": {"$begins": "USNY"},                   # Prefix match
        "issuanceDate": {"$gte": "2026-01-01"},       # Date comparison
    }
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


class QueryOperator(ABC):
    """
    Abstract base for query operators.

    Each operator knows:
    - How to match a value in-memory
    - How to generate an index key for range scans
    """

    @abstractmethod
    def matches(self, value: Any) -> bool:
        """Check if a value matches this operator's condition."""
        ...

    @abstractmethod
    def index_key(self) -> Optional[str]:
        """
        Return key for index lookup.

        Returns:
            String key for index lookup, or None if full scan required
        """
        ...

    @property
    @abstractmethod
    def operator_name(self) -> str:
        """Return operator name for serialization."""
        ...


@dataclass
class Eq(QueryOperator):
    """
    Equality operator.

    Matches: {"field": value} or {"field": {"$eq": value}}

    Index: Exact key lookup (most efficient)
    """
    value: Any

    def matches(self, value: Any) -> bool:
        return value == self.value

    def index_key(self) -> str:
        return str(self.value)

    @property
    def operator_name(self) -> str:
        return "$eq"


@dataclass
class Begins(QueryOperator):
    """
    Prefix match operator.

    Matches: {"field": {"$begins": "prefix"}}

    Index: Range scan from prefix to prefix + max_char (efficient)

    Example:
        >>> op = Begins("US")
        >>> op.matches("USNY12345")  # True
        >>> op.matches("GBLO00001")  # False
    """
    prefix: str

    def matches(self, value: Any) -> bool:
        return str(value).startswith(self.prefix)

    def index_key(self) -> str:
        # For range scan: start at prefix, end at prefix + max char
        return self.prefix

    def index_key_end(self) -> str:
        """End key for range scan (prefix + max char)."""
        if not self.prefix:
            return "\xff"
        # Increment last character for range end
        return self.prefix[:-1] + chr(ord(self.prefix[-1]) + 1)

    @property
    def operator_name(self) -> str:
        return "$begins"


@dataclass
class Lt(QueryOperator):
    """
    Less than operator.

    Matches: {"field": {"$lt": value}}

    Index: Range scan from min to value (exclusive)
    """
    value: Any

    def matches(self, value: Any) -> bool:
        try:
            return value < self.value
        except TypeError:
            return str(value) < str(self.value)

    def index_key(self) -> str:
        return str(self.value)

    @property
    def operator_name(self) -> str:
        return "$lt"


@dataclass
class Gt(QueryOperator):
    """
    Greater than operator.

    Matches: {"field": {"$gt": value}}

    Index: Range scan from value (exclusive) to max
    """
    value: Any

    def matches(self, value: Any) -> bool:
        try:
            return value > self.value
        except TypeError:
            return str(value) > str(self.value)

    def index_key(self) -> str:
        return str(self.value)

    @property
    def operator_name(self) -> str:
        return "$gt"


@dataclass
class Lte(QueryOperator):
    """
    Less than or equal operator.

    Matches: {"field": {"$lte": value}}

    Index: Range scan from min to value (inclusive)
    """
    value: Any

    def matches(self, value: Any) -> bool:
        try:
            return value <= self.value
        except TypeError:
            return str(value) <= str(self.value)

    def index_key(self) -> str:
        return str(self.value)

    @property
    def operator_name(self) -> str:
        return "$lte"


@dataclass
class Gte(QueryOperator):
    """
    Greater than or equal operator.

    Matches: {"field": {"$gte": value}}

    Index: Range scan from value (inclusive) to max
    """
    value: Any

    def matches(self, value: Any) -> bool:
        try:
            return value >= self.value
        except TypeError:
            return str(value) >= str(self.value)

    def index_key(self) -> str:
        return str(self.value)

    @property
    def operator_name(self) -> str:
        return "$gte"


@dataclass
class Contains(QueryOperator):
    """
    Substring match operator.

    Matches: {"field": {"$contains": "substring"}}

    Index: None (requires full scan)

    Note: Less efficient - use $begins when possible.
    """
    substring: str

    def matches(self, value: Any) -> bool:
        return self.substring in str(value)

    def index_key(self) -> Optional[str]:
        # Cannot use index for substring match
        return None

    @property
    def operator_name(self) -> str:
        return "$contains"


def parse_query_value(field_value: Any) -> QueryOperator:
    """
    Parse a query value into an operator.

    Args:
        field_value: Either a direct value (implicit $eq) or dict with operator

    Returns:
        Appropriate QueryOperator instance

    Examples:
        >>> parse_query_value("Alice")
        Eq(value="Alice")

        >>> parse_query_value({"$begins": "US"})
        Begins(prefix="US")

        >>> parse_query_value({"$gte": "2026-01-01"})
        Gte(value="2026-01-01")
    """
    # Direct value = equality
    if not isinstance(field_value, dict):
        return Eq(value=field_value)

    # Explicit operator
    operators = {
        "$eq": lambda v: Eq(value=v),
        "$begins": lambda v: Begins(prefix=v),
        "$lt": lambda v: Lt(value=v),
        "$gt": lambda v: Gt(value=v),
        "$lte": lambda v: Lte(value=v),
        "$gte": lambda v: Gte(value=v),
        "$contains": lambda v: Contains(substring=v),
    }

    for op_name, constructor in operators.items():
        if op_name in field_value:
            return constructor(field_value[op_name])

    # Default to equality if unknown structure
    return Eq(value=field_value)
