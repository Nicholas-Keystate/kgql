"""
KGQL AST - Abstract Syntax Tree nodes for KGQL queries.

These dataclasses represent the parsed structure of KGQL queries,
enabling translation to keripy method calls.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union


class EdgeOperator(Enum):
    """
    Edge constraint operators for KERI property graph queries.

    These operators define the relationship constraints between
    credential issuers and subjects:

    - I2I: Issuer-to-Issuer (child issuer == parent subject)
    - DI2I: Delegated-Issuer-to-Issuer (child issuer in delegation chain)
    - NI2I: No-Issuer-to-Issuer constraint (third-party attestation)
    - ANY: Accept any valid edge (no constraint)
    """
    I2I = "I2I"
    DI2I = "DI2I"
    NI2I = "NI2I"
    ANY = "ANY"


class SortDirection(Enum):
    """Sort direction for ORDER BY clause."""
    ASC = "ASC"
    DESC = "DESC"


class Comparator(Enum):
    """Comparison operators for WHERE conditions."""
    EQ = "="
    NE = "!="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    LIKE = "LIKE"
    CONTAINS = "CONTAINS"
    IN = "IN"


@dataclass
class KeyStateContext:
    """
    Context for key state-scoped queries.

    Specifies the AID and optional sequence number for
    temporal key state verification.
    """
    aid: str
    seq: Optional[int] = None


@dataclass
class GovernanceContext:
    """
    Context for governance framework-scoped queries.

    Specifies the governance framework to apply for
    constraint checking (e.g., 'vLEI').
    """
    framework: str


@dataclass
class NodePattern:
    """
    Pattern for matching nodes in the property graph.

    Represents: (variable:NodeType)
    """
    variable: Optional[str] = None
    node_type: Optional[str] = None


@dataclass
class EdgePattern:
    """
    Pattern for matching edges between nodes.

    Represents: -[variable:EdgeType @Operator]->
    """
    variable: Optional[str] = None
    edge_type: Optional[str] = None
    operator: EdgeOperator = EdgeOperator.ANY
    direction: str = "outgoing"  # "outgoing" (->) or "incoming" (<-)


@dataclass
class Condition:
    """
    A single condition in a WHERE clause.

    Represents: field comparator value
    """
    field: str
    comparator: Comparator
    value: Union[str, int, float, bool, list, None]
    negated: bool = False


@dataclass
class WhereClause:
    """
    WHERE clause containing one or more conditions.

    Conditions are combined with AND.
    """
    conditions: list[Condition] = field(default_factory=list)


@dataclass
class ReturnItem:
    """
    A single item in a RETURN clause.

    Can be a field reference, proof expression, or aggregate.
    """
    expression: str
    alias: Optional[str] = None
    is_proof: bool = False
    is_keystate: bool = False
    is_aggregate: bool = False
    aggregate_type: Optional[str] = None  # COUNT, COLLECT, LENGTH


@dataclass
class ReturnClause:
    """RETURN clause specifying what to return from the query."""
    items: list[ReturnItem] = field(default_factory=list)
    return_all: bool = False


@dataclass
class MatchOperation:
    """
    MATCH operation for pattern matching.

    Translates to: reger.issus.get(), reger.subjs.get(), etc.
    """
    patterns: list[tuple[NodePattern, Optional[EdgePattern]]] = field(default_factory=list)


@dataclass
class ResolveOperation:
    """
    RESOLVE operation for direct SAID resolution.

    Translates to: reger.cloneCred(said)
    """
    said: str
    is_variable: bool = False


@dataclass
class TraverseOperation:
    """
    TRAVERSE operation for path traversal.

    Translates to: reger.sources(db, creder) for recursive chains
    """
    from_said: Optional[str] = None
    from_pattern: Optional[NodePattern] = None
    from_condition: Optional[Condition] = None

    to_said: Optional[str] = None
    to_pattern: Optional[NodePattern] = None
    to_condition: Optional[Condition] = None

    via_edge: Optional[EdgePattern] = None
    follow_type: Optional[str] = None


@dataclass
class VerifyOperation:
    """
    VERIFY operation for verification against key state.

    Translates to: verifier.verifyChain(nodeSaid, op, issuer)
    """
    said: str
    is_variable: bool = False
    against_keystate: Optional[KeyStateContext] = None


@dataclass
class WithOptions:
    """Options from WITH clause."""
    include_proof: bool = False
    include_keystate: bool = False
    include_sources: bool = False


@dataclass
class OrderClause:
    """ORDER BY clause."""
    field: str
    direction: SortDirection = SortDirection.ASC


@dataclass
class KGQLQuery:
    """
    Complete KGQL query AST.

    This is the root node of the AST, containing:
    - Optional context (key state and/or governance)
    - Operation (MATCH, RESOLVE, TRAVERSE, or VERIFY)
    - Optional modifiers (WHERE, WITH, ORDER BY, LIMIT)
    - Optional RETURN clause
    """
    # Context
    keystate_context: Optional[KeyStateContext] = None
    governance_context: Optional[GovernanceContext] = None

    # Operation (one of these will be set)
    match: Optional[MatchOperation] = None
    resolve: Optional[ResolveOperation] = None
    traverse: Optional[TraverseOperation] = None
    verify: Optional[VerifyOperation] = None

    # Modifiers
    where: Optional[WhereClause] = None
    with_options: Optional[WithOptions] = None
    order_by: Optional[OrderClause] = None
    limit: Optional[int] = None

    # Return
    return_clause: Optional[ReturnClause] = None

    # Variables for parameter binding
    variables: dict[str, any] = field(default_factory=dict)

    @property
    def operation_type(self) -> str:
        """Return the type of operation in this query."""
        if self.match:
            return "match"
        elif self.resolve:
            return "resolve"
        elif self.traverse:
            return "traverse"
        elif self.verify:
            return "verify"
        return "unknown"
