# -*- encoding: utf-8 -*-
"""
KGQL Constraint Compiler - Compiles governance framework rules into
executable constraint functions.

The compiler bridges the gap between declarative constraint expressions
stored in framework credentials and runtime evaluation during query
execution. It handles:

1. Field constraint expressions:
   "$issuer.jurisdiction == $subject.country"
   → Callable that extracts fields and compares

2. Framework-to-checker pipeline:
   Raw ACDC credential → GovernanceFramework → ConstraintChecker

3. Compiled constraint caching (keyed by framework SAID)

This is the bridge from vEGF (verifiable but human-interpreted) to
aEGF (autonomic, machine-executed).
"""

import operator
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kgql.governance.schema import GovernanceFramework, ConstraintRule
from kgql.governance.checker import ConstraintChecker, CheckResult, ConstraintViolation
from kgql.parser.ast import EdgeOperator


# Supported comparison operators in field constraint expressions
_COMPARISON_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}

# Pattern: $role.field op $role.field   OR   $role.field op "literal"
_FIELD_EXPR_PATTERN = re.compile(
    r'^\$(\w+)\.(\w+)\s*(==|!=|<|>|<=|>=)\s*'
    r'(?:\$(\w+)\.(\w+)|"([^"]*)")'
    r'$'
)


@dataclass
class CompiledFieldConstraint:
    """
    A compiled field constraint ready for evaluation.

    Attributes:
        expression: Original expression string
        left_role: Role for left operand (e.g., "issuer", "subject")
        left_field: Field name for left operand
        op: Comparison operator function
        op_str: Original operator string
        right_role: Role for right operand (None if literal)
        right_field: Field name for right operand (None if literal)
        right_literal: Literal value (None if field reference)
    """
    expression: str
    left_role: str
    left_field: str
    op: Callable[[Any, Any], bool]
    op_str: str
    right_role: Optional[str] = None
    right_field: Optional[str] = None
    right_literal: Optional[str] = None

    def evaluate(self, context: dict[str, dict]) -> bool:
        """
        Evaluate this constraint against a role->attributes context.

        Args:
            context: Dict mapping role names to attribute dicts.
                e.g., {"issuer": {"jurisdiction": "US"}, "subject": {"country": "US"}}

        Returns:
            True if constraint is satisfied
        """
        left_attrs = context.get(self.left_role, {})
        left_val = left_attrs.get(self.left_field)
        if left_val is None:
            return False  # Missing field = cannot satisfy

        if self.right_literal is not None:
            right_val = self.right_literal
        else:
            right_attrs = context.get(self.right_role, {})
            right_val = right_attrs.get(self.right_field)
            if right_val is None:
                return False

        try:
            return self.op(left_val, right_val)
        except TypeError:
            return False


def compile_field_expression(expression: str) -> Optional[CompiledFieldConstraint]:
    """
    Compile a field constraint expression string into a callable.

    Supported formats:
        "$issuer.jurisdiction == $subject.country"
        "$issuer.level >= $subject.min_level"
        "$subject.name != \"forbidden\""

    Args:
        expression: Constraint expression string

    Returns:
        CompiledFieldConstraint or None if expression is invalid
    """
    match = _FIELD_EXPR_PATTERN.match(expression.strip())
    if not match:
        return None

    left_role, left_field, op_str, right_role, right_field, right_literal = match.groups()

    op_fn = _COMPARISON_OPS.get(op_str)
    if not op_fn:
        return None

    return CompiledFieldConstraint(
        expression=expression,
        left_role=left_role,
        left_field=left_field,
        op=op_fn,
        op_str=op_str,
        right_role=right_role,
        right_field=right_field,
        right_literal=right_literal,
    )


@dataclass
class CompiledFramework:
    """
    A fully compiled governance framework ready for runtime evaluation.

    Contains the base ConstraintChecker plus compiled field constraints
    that can evaluate attribute-level rules.
    """
    checker: ConstraintChecker
    field_constraints: dict[str, list[CompiledFieldConstraint]] = field(
        default_factory=dict
    )

    @property
    def framework(self) -> GovernanceFramework:
        return self.checker.framework

    @property
    def framework_said(self) -> str:
        return self.checker.framework_said

    def check_edge_with_context(
        self,
        edge_type: str,
        actual_operator: EdgeOperator,
        context: Optional[dict[str, dict]] = None,
    ) -> CheckResult:
        """
        Check an edge with both operator and field constraints.

        Args:
            edge_type: Edge being traversed
            actual_operator: Operator on the edge
            context: Optional role->attributes dict for field constraints

        Returns:
            CheckResult combining operator and field constraint checks
        """
        # Check operator constraints first
        result = self.checker.check_edge(edge_type, actual_operator)

        # If operator check failed strict, return immediately
        if not result.allowed:
            return result

        # Check field constraints if context provided
        if context and edge_type in self.field_constraints:
            for fc in self.field_constraints[edge_type]:
                if not fc.evaluate(context):
                    violation = ConstraintViolation(
                        rule_name=f"field:{fc.expression}",
                        message=(
                            f"Field constraint failed: {fc.expression}"
                        ),
                        enforcement=self.checker.framework.get_rules_for(
                            edge_type
                        )[0].enforcement if self.checker.framework.get_rules_for(
                            edge_type
                        ) else __import__('kgql.governance.schema', fromlist=['RuleEnforcement']).RuleEnforcement.STRICT,
                        edge_type=edge_type,
                    )
                    # Field constraints are advisory by default
                    result.warnings.append(violation)

        return result


class ConstraintCompiler:
    """
    Compiles GovernanceFramework instances into executable CompiledFramework.

    The compilation pipeline:
    1. Parse GovernanceFramework (already done by from_credential)
    2. Create ConstraintChecker (operator algebra evaluation)
    3. Compile field constraint expressions into callables
    4. Cache compiled result by framework SAID

    Usage:
        compiler = ConstraintCompiler()
        compiled = compiler.compile(framework)
        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.I2I,
            context={"issuer": {"jurisdiction": "US"}, "subject": {"country": "US"}}
        )
    """

    def __init__(self):
        self._cache: dict[str, CompiledFramework] = {}

    def compile(self, framework: GovernanceFramework) -> CompiledFramework:
        """
        Compile a governance framework into an executable form.

        Results are cached by SAID (immutable content = eternal cache).

        Args:
            framework: Parsed GovernanceFramework

        Returns:
            CompiledFramework with checker and field constraints
        """
        if framework.said in self._cache:
            return self._cache[framework.said]

        checker = ConstraintChecker(framework)
        field_constraints: dict[str, list[CompiledFieldConstraint]] = {}

        for rule in framework.rules:
            if rule.field_constraints:
                compiled_list = field_constraints.setdefault(rule.applies_to, [])
                for _field_name, expression in rule.field_constraints.items():
                    compiled = compile_field_expression(expression)
                    if compiled:
                        compiled_list.append(compiled)

        result = CompiledFramework(
            checker=checker,
            field_constraints=field_constraints,
        )
        self._cache[framework.said] = result
        return result

    def is_compiled(self, framework_said: str) -> bool:
        """Check if a framework is already compiled."""
        return framework_said in self._cache

    def clear_cache(self) -> None:
        """Clear the compilation cache."""
        self._cache.clear()
