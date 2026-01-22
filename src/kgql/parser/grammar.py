"""
KGQL Grammar - Lark EBNF grammar for KERI Graph Query Language.

This grammar defines a declarative syntax for expressing:
- Field selection and filtering
- Path traversal patterns
- Edge operator constraints (@I2I, @DI2I, @NI2I)
- Aggregations (count, collect)

The grammar translates to existing keripy methods, not new infrastructure.
"""

# Lark grammar for KGQL - simplified to avoid conflicts
KGQL_GRAMMAR = r'''
// Top-level query structure
start: query

query: context_clause? operation modifier_clause? return_clause?

// Context clauses
context_clause: keystate_context governance_context?
              | governance_context

keystate_context: "AT"i "KEYSTATE"i "(" keystate_spec ")"
governance_context: "WITHIN"i "FRAMEWORK"i STRING

keystate_spec: "aid"i "=" STRING ("," "seq"i "=" NUMBER)?

// Operations - mutually exclusive
operation: match_op
         | resolve_op
         | traverse_op
         | verify_op

// MATCH operation
match_op: "MATCH"i pattern_list

pattern_list: pattern ("," pattern)*

pattern: node_pattern (edge_pattern node_pattern)?

node_pattern: "(" NAME? (":" NAME)? ")"

edge_pattern: "-[" edge_spec? "]->"
            | "<-[" edge_spec? "]-"

edge_spec: edge_var_type
         | edge_type_only
         | edge_var_only
         | edge_colon_op_only
         | edge_op_only

edge_var_type: NAME ":" NAME operator?
edge_type_only: ":" NAME operator?
edge_var_only: NAME operator?
edge_colon_op_only: ":" operator
edge_op_only: operator

operator: "@I2I"i -> i2i
        | "@DI2I"i -> di2i
        | "@NI2I"i -> ni2i
        | "@ANY"i -> any_op

// RESOLVE operation
resolve_op: "RESOLVE"i (STRING | VARIABLE)

// TRAVERSE operation
traverse_op: traverse_to_via | traverse_follow

traverse_to_via: "TRAVERSE"i "FROM"i traverse_source "TO"i traverse_target via_clause?
traverse_follow: "TRAVERSE"i "FROM"i traverse_source "FOLLOW"i NAME

traverse_source: STRING | VARIABLE | from_pattern
traverse_target: STRING | VARIABLE | to_pattern

from_pattern: node_pattern ("WHERE"i simple_condition)?
to_pattern: node_pattern ("WHERE"i simple_condition)?

via_clause: "VIA"i edge_pattern

// VERIFY operation
verify_op: "VERIFY"i (STRING | VARIABLE) against_clause?

against_clause: "AGAINST"i keystate_spec

// Modifiers
modifier_clause: modifier+

modifier: where_clause
        | with_clause
        | order_clause
        | limit_clause

where_clause: "WHERE"i condition_list

condition_list: condition ("AND"i condition)*

condition: field_ref COMPARATOR value
         | field_ref "IN"i "(" value_list ")"
         | "NOT"i condition
         | "(" condition ")"

simple_condition: field_ref COMPARATOR value

COMPARATOR: "=" | "!=" | "<" | ">" | "<=" | ">=" | "LIKE"i | "CONTAINS"i

with_clause: "WITH"i with_option+
with_option: "PROOF"i | "KEYSTATE"i | "SOURCES"i

order_clause: "ORDER"i "BY"i field_ref sort_dir?
sort_dir: ASC | DESC
ASC: "ASC"i
DESC: "DESC"i

limit_clause: "LIMIT"i NUMBER

// Return clause
return_clause: "RETURN"i return_list

return_list: return_item ("," return_item)*

return_item: field_ref ("AS"i NAME)?
           | proof_expr ("AS"i NAME)?
           | keystate_expr ("AS"i NAME)?
           | aggregate_expr ("AS"i NAME)?
           | NAME
           | "*"

proof_expr: "PROOF"i "(" NAME ")"
keystate_expr: "KEYSTATE"i "(" NAME ")"

aggregate_expr: "COUNT"i "(" (NAME | "*") ")"
              | "COLLECT"i "(" NAME ")"
              | "LENGTH"i "(" NAME ")"

// Field references
field_ref: NAME ("." NAME)+
         | VARIABLE ("." NAME)*

// Values
value: STRING
     | NUMBER
     | "true"i -> true_val
     | "false"i -> false_val
     | "null"i -> null_val
     | VARIABLE

value_list: value ("," value)*

// Terminals
NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
VARIABLE: "$" NAME
NUMBER: /[0-9]+(\.[0-9]+)?/
STRING: /"[^"]*"/ | /'[^']*'/

// Whitespace and comments
%import common.WS
%ignore WS
COMMENT: /--[^\n]*/
%ignore COMMENT
'''


def get_grammar() -> str:
    """Return the KGQL grammar string for use with Lark."""
    return KGQL_GRAMMAR
