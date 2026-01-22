"""
KGQL Parser - Lark-based parser for KERI Graph Query Language.

Parses KGQL query strings into AST nodes that can be translated
to keripy method calls.
"""

from typing import Optional

from lark import Lark, Transformer, v_args, Token

from kgql.parser.grammar import get_grammar
from kgql.parser.ast import (
    KGQLQuery,
    MatchOperation,
    ResolveOperation,
    TraverseOperation,
    VerifyOperation,
    EdgeOperator,
    SortDirection,
    Comparator,
    KeyStateContext,
    GovernanceContext,
    NodePattern,
    EdgePattern,
    Condition,
    WhereClause,
    WithOptions,
    OrderClause,
    ReturnItem,
    ReturnClause,
)


class KGQLTransformer(Transformer):
    """
    Lark Transformer that converts parse tree to KGQL AST nodes.
    """

    # --- Terminal handling ---

    def NAME(self, token):
        return str(token)

    def VARIABLE(self, token):
        return str(token)  # includes the $ prefix

    def NUMBER(self, token):
        s = str(token)
        return float(s) if '.' in s else int(s)

    def STRING(self, token):
        # Remove surrounding quotes
        s = str(token)
        return s[1:-1]

    def COMPARATOR(self, token):
        return str(token).upper()

    # --- Boolean/null values ---

    def true_val(self, _):
        return True

    def false_val(self, _):
        return False

    def null_val(self, _):
        return None

    # --- Edge operators ---

    def i2i(self, _):
        return EdgeOperator.I2I

    def di2i(self, _):
        return EdgeOperator.DI2I

    def ni2i(self, _):
        return EdgeOperator.NI2I

    def any_op(self, _):
        return EdgeOperator.ANY

    def operator(self, items):
        return items[0] if items else EdgeOperator.ANY

    # --- Key state context ---

    def keystate_spec(self, items):
        aid = items[0]
        seq = int(items[1]) if len(items) > 1 else None
        return KeyStateContext(aid=aid, seq=seq)

    def keystate_context(self, items):
        return ("keystate", items[0])

    def governance_context(self, items):
        return ("governance", GovernanceContext(framework=items[0]))

    def context_clause(self, items):
        result = {}
        for item in items:
            if isinstance(item, tuple):
                if item[0] == "keystate":
                    result["keystate"] = item[1]
                elif item[0] == "governance":
                    result["governance"] = item[1]
        return result

    # --- Patterns ---

    def node_pattern(self, items):
        variable = None
        node_type = None
        for item in items:
            if isinstance(item, str):
                if variable is None:
                    variable = item
                else:
                    node_type = item
        return NodePattern(variable=variable, node_type=node_type)

    def edge_var_only(self, items):
        """Edge with just variable: [e] or [e @I2I]"""
        variable = items[0]
        op = items[1] if len(items) > 1 and isinstance(items[1], EdgeOperator) else EdgeOperator.ANY
        return (variable, None, op)

    def edge_type_only(self, items):
        """Edge with just type: [:Type] or [:Type @I2I]"""
        edge_type = items[0]
        op = items[1] if len(items) > 1 and isinstance(items[1], EdgeOperator) else EdgeOperator.ANY
        return (None, edge_type, op)

    def edge_var_type(self, items):
        """Edge with both: [e:Type] or [e:Type @I2I]"""
        variable = items[0]
        edge_type = items[1]
        op = items[2] if len(items) > 2 and isinstance(items[2], EdgeOperator) else EdgeOperator.ANY
        return (variable, edge_type, op)

    def edge_op_only(self, items):
        """Edge with just operator: [@I2I]"""
        op = items[0] if items and isinstance(items[0], EdgeOperator) else EdgeOperator.ANY
        return (None, None, op)

    def edge_colon_op_only(self, items):
        """Edge with colon and operator only: [:@I2I]"""
        op = items[0] if items and isinstance(items[0], EdgeOperator) else EdgeOperator.ANY
        return (None, None, op)

    def edge_spec(self, items):
        """Extract edge spec from subrule result."""
        if items and isinstance(items[0], tuple):
            return items[0]
        # Operator only case
        if items and isinstance(items[0], EdgeOperator):
            return (None, None, items[0])
        return (None, None, EdgeOperator.ANY)

    def edge_pattern(self, items):
        variable = None
        edge_type = None
        op = EdgeOperator.ANY
        for item in items:
            if isinstance(item, tuple) and len(item) == 3:
                variable, edge_type, op = item
        return EdgePattern(
            variable=variable,
            edge_type=edge_type,
            operator=op,
            direction="outgoing"
        )

    def pattern(self, items):
        node = None
        edge = None
        for item in items:
            if isinstance(item, NodePattern) and node is None:
                node = item
            elif isinstance(item, EdgePattern):
                edge = item
        return (node, edge)

    def pattern_list(self, items):
        return [item for item in items if isinstance(item, tuple)]

    # --- MATCH operation ---

    def match_op(self, items):
        patterns = items[0] if items else []
        return MatchOperation(patterns=patterns)

    # --- RESOLVE operation ---

    def resolve_op(self, items):
        value = items[0]
        is_variable = isinstance(value, str) and value.startswith("$")
        return ResolveOperation(said=value, is_variable=is_variable)

    # --- TRAVERSE operation ---

    def from_pattern(self, items):
        return ("from_pattern", items[0], items[1] if len(items) > 1 else None)

    def to_pattern(self, items):
        return ("to_pattern", items[0], items[1] if len(items) > 1 else None)

    def via_clause(self, items):
        return ("via", items[0])

    def traverse_source(self, items):
        """Extract source from TRAVERSE FROM clause."""
        item = items[0]
        if isinstance(item, str):
            return ("source_said", item)
        elif isinstance(item, tuple) and item[0] == "from_pattern":
            return item
        return ("source_said", item)

    def traverse_target(self, items):
        """Extract target from TRAVERSE TO clause."""
        item = items[0]
        if isinstance(item, str):
            return ("target_said", item)
        elif isinstance(item, tuple) and item[0] == "to_pattern":
            return item
        return ("target_said", item)

    def traverse_to_via(self, items):
        """Handle TRAVERSE FROM ... TO ... VIA ... form."""
        op = TraverseOperation()
        for item in items:
            if isinstance(item, tuple):
                if item[0] == "source_said":
                    op.from_said = item[1]
                elif item[0] == "from_pattern":
                    op.from_pattern = item[1]
                    if len(item) > 2:
                        op.from_condition = item[2]
                elif item[0] == "target_said":
                    op.to_said = item[1]
                elif item[0] == "to_pattern":
                    op.to_pattern = item[1]
                    if len(item) > 2:
                        op.to_condition = item[2]
                elif item[0] == "via":
                    op.via_edge = item[1]
        return op

    def traverse_follow(self, items):
        """Handle TRAVERSE FROM ... FOLLOW name form."""
        op = TraverseOperation()
        for item in items:
            if isinstance(item, str):
                op.follow_type = item
            elif isinstance(item, tuple):
                if item[0] == "source_said":
                    op.from_said = item[1]
                elif item[0] == "from_pattern":
                    op.from_pattern = item[1]
                    if len(item) > 2:
                        op.from_condition = item[2]
        return op

    def traverse_op(self, items):
        """Extract traverse operation from subrule result."""
        return items[0] if items else TraverseOperation()

    # --- VERIFY operation ---

    def against_clause(self, items):
        return items[0]

    def verify_op(self, items):
        said = items[0]
        is_variable = isinstance(said, str) and said.startswith("$")
        against = None
        for item in items[1:]:
            if isinstance(item, KeyStateContext):
                against = item
        return VerifyOperation(
            said=said,
            is_variable=is_variable,
            against_keystate=against
        )

    # --- Conditions ---

    def field_ref(self, items):
        return ".".join(str(i) for i in items)

    def value(self, items):
        return items[0]

    def value_list(self, items):
        return list(items)

    def simple_condition(self, items):
        field = items[0]
        comparator_str = items[1]
        value = items[2]

        comp_map = {
            "=": Comparator.EQ,
            "!=": Comparator.NE,
            "<": Comparator.LT,
            ">": Comparator.GT,
            "<=": Comparator.LE,
            ">=": Comparator.GE,
            "LIKE": Comparator.LIKE,
            "CONTAINS": Comparator.CONTAINS,
        }
        comparator = comp_map.get(comparator_str, Comparator.EQ)

        return Condition(field=field, comparator=comparator, value=value)

    def condition(self, items):
        if len(items) == 1 and isinstance(items[0], Condition):
            return items[0]

        negated = False
        field = None
        comparator = Comparator.EQ
        value = None

        i = 0
        # Check for NOT
        if items and str(items[0]).upper() == "NOT":
            negated = True
            i += 1
            if isinstance(items[i], Condition):
                cond = items[i]
                cond.negated = True
                return cond

        # Check for nested condition
        if len(items) > i and isinstance(items[i], Condition):
            cond = items[i]
            cond.negated = negated
            return cond

        # Parse field, comparator, value
        if len(items) > i:
            field = items[i]
            i += 1

        if len(items) > i:
            comp_str = str(items[i]).upper()
            comp_map = {
                "=": Comparator.EQ,
                "!=": Comparator.NE,
                "<": Comparator.LT,
                ">": Comparator.GT,
                "<=": Comparator.LE,
                ">=": Comparator.GE,
                "LIKE": Comparator.LIKE,
                "CONTAINS": Comparator.CONTAINS,
                "IN": Comparator.IN,
            }
            comparator = comp_map.get(comp_str, Comparator.EQ)
            i += 1

        if len(items) > i:
            value = items[i]

        return Condition(
            field=field,
            comparator=comparator,
            value=value,
            negated=negated
        )

    def condition_list(self, items):
        return [item for item in items if isinstance(item, Condition)]

    def where_clause(self, items):
        conditions = items[0] if items else []
        return WhereClause(conditions=conditions)

    # --- WITH clause ---

    def with_option(self, items):
        return str(items[0]).upper() if items else "PROOF"

    def with_clause(self, items):
        options = WithOptions()
        for item in items:
            if isinstance(item, str):
                item_upper = item.upper()
                if item_upper == "PROOF":
                    options.include_proof = True
                elif item_upper == "KEYSTATE":
                    options.include_keystate = True
                elif item_upper == "SOURCES":
                    options.include_sources = True
        return options

    # --- ORDER BY ---

    def ASC(self, token):
        return SortDirection.ASC

    def DESC(self, token):
        return SortDirection.DESC

    def sort_dir(self, items):
        return items[0] if items else SortDirection.ASC

    def order_clause(self, items):
        field = items[0]
        direction = SortDirection.ASC
        for item in items[1:]:
            if isinstance(item, SortDirection):
                direction = item
        return OrderClause(field=field, direction=direction)

    # --- LIMIT ---

    def limit_clause(self, items):
        return ("limit", int(items[0]))

    # --- RETURN clause ---

    def proof_expr(self, items):
        return ReturnItem(
            expression=f"PROOF({items[0]})",
            is_proof=True
        )

    def keystate_expr(self, items):
        return ReturnItem(
            expression=f"KEYSTATE({items[0]})",
            is_keystate=True
        )

    def aggregate_expr(self, items):
        agg_type = str(items[0]).upper()
        target = items[1] if len(items) > 1 else "*"
        return ReturnItem(
            expression=f"{agg_type}({target})",
            is_aggregate=True,
            aggregate_type=agg_type
        )

    def return_item(self, items):
        if isinstance(items[0], ReturnItem):
            item = items[0]
            if len(items) > 1:
                item.alias = items[1]
            return item

        expression = items[0]
        alias = items[1] if len(items) > 1 else None

        if expression == "*":
            return ReturnItem(expression="*")

        return ReturnItem(expression=str(expression), alias=alias)

    def return_list(self, items):
        return [item for item in items if isinstance(item, ReturnItem)]

    def return_clause(self, items):
        return_items = items[0] if items else []
        return_all = any(item.expression == "*" for item in return_items)
        return ReturnClause(items=return_items, return_all=return_all)

    # --- Operation (pass-through) ---

    def operation(self, items):
        """Extract the operation from the operation rule."""
        return items[0] if items else None

    # --- Modifiers ---

    def modifier(self, items):
        return items[0]

    def modifier_clause(self, items):
        result = {}
        for item in items:
            if isinstance(item, WhereClause):
                result["where"] = item
            elif isinstance(item, WithOptions):
                result["with"] = item
            elif isinstance(item, OrderClause):
                result["order"] = item
            elif isinstance(item, tuple) and item[0] == "limit":
                result["limit"] = item[1]
        return result

    # --- Top-level query ---

    def query(self, items):
        query = KGQLQuery()

        for item in items:
            # Context
            if isinstance(item, dict) and ("keystate" in item or "governance" in item):
                query.keystate_context = item.get("keystate")
                query.governance_context = item.get("governance")

            # Operations
            elif isinstance(item, MatchOperation):
                query.match = item
            elif isinstance(item, ResolveOperation):
                query.resolve = item
            elif isinstance(item, TraverseOperation):
                query.traverse = item
            elif isinstance(item, VerifyOperation):
                query.verify = item

            # Modifiers dict
            elif isinstance(item, dict) and any(k in item for k in ("where", "with", "order", "limit")):
                query.where = item.get("where")
                query.with_options = item.get("with")
                query.order_by = item.get("order")
                query.limit = item.get("limit")

            # Return clause
            elif isinstance(item, ReturnClause):
                query.return_clause = item

        return query

    def start(self, items):
        return items[0]


class KGQLParser:
    """
    KGQL Parser using Lark.

    Parses KGQL query strings into KGQLQuery AST nodes.

    Example:
        parser = KGQLParser()
        query = parser.parse("MATCH (c:Credential) WHERE c.issuer = $aid")
    """

    def __init__(self):
        self._parser = Lark(
            get_grammar(),
            parser='lalr',
            transformer=KGQLTransformer(),
        )

    def parse(self, query_string: str, variables: Optional[dict] = None) -> KGQLQuery:
        """
        Parse a KGQL query string into an AST.

        Args:
            query_string: The KGQL query to parse
            variables: Optional dict of variable bindings ($name -> value)

        Returns:
            KGQLQuery AST node

        Raises:
            lark.exceptions.LarkError: If parsing fails
        """
        result = self._parser.parse(query_string)

        if variables:
            result.variables = variables

        return result


def parse(query_string: str, variables: Optional[dict] = None) -> KGQLQuery:
    """
    Convenience function to parse a KGQL query.

    Creates a parser instance and parses the query string.
    For repeated parsing, use KGQLParser directly for better performance.

    Args:
        query_string: The KGQL query to parse
        variables: Optional dict of variable bindings

    Returns:
        KGQLQuery AST node
    """
    parser = KGQLParser()
    return parser.parse(query_string, variables)
