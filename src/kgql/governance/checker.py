# -*- encoding: utf-8 -*-
"""
KGQL Constraint Checker - Evaluates governance rules during query execution.

When a query includes `WITHIN FRAMEWORK 'ESAID...'`, the ConstraintChecker
is attached to the execution context. Each edge traversal is checked against
the framework's rules and credential matrix.

The constraint algebra defines a partial order:
    I2I > DI2I > NI2I > ANY

A rule requiring @DI2I is satisfied by @DI2I or @I2I (stronger), but not
by @NI2I or @ANY (weaker).
"""

from dataclasses import dataclass, field
from typing import Optional

from kgql.parser.ast import EdgeOperator
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
)


# Operator strength for the partial order (higher = stronger)
_OPERATOR_STRENGTH: dict[EdgeOperator, int] = {
    EdgeOperator.ANY: 0,
    EdgeOperator.NI2I: 1,
    EdgeOperator.DI2I: 2,
    EdgeOperator.I2I: 3,
}


def operator_satisfies(actual: EdgeOperator, required: EdgeOperator) -> bool:
    """
    Check if an actual operator satisfies a required operator.

    The constraint algebra partial order:
        I2I > DI2I > NI2I > ANY

    An operator satisfies a requirement if it is equal or stronger.

    Args:
        actual: The operator present on the edge
        required: The operator the rule requires

    Returns:
        True if actual >= required in the partial order
    """
    return _OPERATOR_STRENGTH[actual] >= _OPERATOR_STRENGTH[required]


@dataclass
class ConstraintViolation:
    """A single constraint violation found during checking."""
    rule_name: str
    message: str
    enforcement: RuleEnforcement
    edge_type: str = ""
    actual_operator: Optional[EdgeOperator] = None
    required_operator: Optional[EdgeOperator] = None

    @property
    def is_strict(self) -> bool:
        return self.enforcement == RuleEnforcement.STRICT


@dataclass
class CheckResult:
    """Result of constraint checking against a framework."""
    allowed: bool = True
    violations: list[ConstraintViolation] = field(default_factory=list)
    warnings: list[ConstraintViolation] = field(default_factory=list)
    framework_said: str = ""

    @property
    def has_strict_violations(self) -> bool:
        return any(v.is_strict for v in self.violations)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "framework_said": self.framework_said,
            "violations": [
                {
                    "rule": v.rule_name,
                    "message": v.message,
                    "enforcement": v.enforcement.value,
                }
                for v in self.violations
            ],
            "warnings": [
                {
                    "rule": w.rule_name,
                    "message": w.message,
                }
                for w in self.warnings
            ],
        }


class ConstraintChecker:
    """
    Evaluates governance framework constraints during query execution.

    Attached to query context when WITHIN FRAMEWORK is used. Checks:
    1. Edge operator strength against rule requirements
    2. Credential matrix (action + role -> operator)
    3. Delegation depth limits
    4. Field-level constraints (stored but evaluated externally)

    Usage:
        checker = ConstraintChecker(framework)

        # Check an edge traversal
        result = checker.check_edge("iss", EdgeOperator.I2I)
        if not result.allowed:
            raise GovernanceViolation(result.violations)

        # Check an action
        result = checker.check_action("issue", "QVI", EdgeOperator.DI2I)
    """

    def __init__(self, framework: GovernanceFramework):
        """
        Initialize checker with a resolved governance framework.

        Args:
            framework: Parsed GovernanceFramework from resolver
        """
        self._framework = framework

    @property
    def framework(self) -> GovernanceFramework:
        """The governance framework being enforced."""
        return self._framework

    @property
    def framework_said(self) -> str:
        return self._framework.said

    def check_edge(
        self,
        edge_type: str,
        actual_operator: EdgeOperator,
    ) -> CheckResult:
        """
        Check if an edge traversal satisfies framework rules.

        Finds all rules that apply to this edge type and checks
        the actual operator against each rule's requirement.

        Args:
            edge_type: The edge being traversed (e.g., "iss", "acdc")
            actual_operator: The operator present on the edge

        Returns:
            CheckResult with violations/warnings
        """
        result = CheckResult(framework_said=self._framework.said)
        rules = self._framework.get_rules_for(edge_type)

        for rule in rules:
            if not operator_satisfies(actual_operator, rule.required_operator):
                violation = ConstraintViolation(
                    rule_name=rule.name,
                    message=(
                        f"Edge '{edge_type}' requires @{rule.required_operator.value} "
                        f"but has @{actual_operator.value}"
                    ),
                    enforcement=rule.enforcement,
                    edge_type=edge_type,
                    actual_operator=actual_operator,
                    required_operator=rule.required_operator,
                )
                if rule.enforcement == RuleEnforcement.STRICT:
                    result.violations.append(violation)
                    result.allowed = False
                else:
                    result.warnings.append(violation)

        return result

    def check_action(
        self,
        action: str,
        role: str,
        actual_operator: EdgeOperator = EdgeOperator.ANY,
    ) -> CheckResult:
        """
        Check if an action is allowed for a role per the credential matrix.

        Args:
            action: The operation (e.g., "issue", "revoke", "query")
            role: The role performing the action (e.g., "QVI", "LE")
            actual_operator: The operator on the edge performing the action

        Returns:
            CheckResult with violations/warnings
        """
        result = CheckResult(framework_said=self._framework.said)

        entry = self._framework.get_matrix_entry(action, role)
        if entry is None:
            # Not in matrix = not governed = allowed
            return result

        if not entry.allowed:
            result.allowed = False
            result.violations.append(ConstraintViolation(
                rule_name=f"matrix:{action}:{role}",
                message=f"Action '{action}' is not allowed for role '{role}'",
                enforcement=RuleEnforcement.STRICT,
            ))
            return result

        if not operator_satisfies(actual_operator, entry.required_operator):
            result.allowed = False
            result.violations.append(ConstraintViolation(
                rule_name=f"matrix:{action}:{role}",
                message=(
                    f"Action '{action}' by '{role}' requires "
                    f"@{entry.required_operator.value} but has "
                    f"@{actual_operator.value}"
                ),
                enforcement=RuleEnforcement.STRICT,
                actual_operator=actual_operator,
                required_operator=entry.required_operator,
            ))

        return result

    def check_delegation_depth(
        self,
        edge_type: str,
        actual_depth: int,
    ) -> CheckResult:
        """
        Check if a delegation chain depth is within framework limits.

        Args:
            edge_type: The edge type being checked
            actual_depth: The actual delegation chain depth

        Returns:
            CheckResult with violations if depth exceeded
        """
        result = CheckResult(framework_said=self._framework.said)
        rules = self._framework.get_rules_for(edge_type)

        for rule in rules:
            if (
                rule.max_delegation_depth is not None
                and actual_depth > rule.max_delegation_depth
            ):
                violation = ConstraintViolation(
                    rule_name=rule.name,
                    message=(
                        f"Delegation depth {actual_depth} exceeds maximum "
                        f"{rule.max_delegation_depth} for '{edge_type}'"
                    ),
                    enforcement=rule.enforcement,
                    edge_type=edge_type,
                )
                if rule.enforcement == RuleEnforcement.STRICT:
                    result.violations.append(violation)
                    result.allowed = False
                else:
                    result.warnings.append(violation)

        return result

    def get_field_constraints(self, edge_type: str) -> dict[str, str]:
        """
        Get field-level constraint expressions for an edge type.

        Field constraints are string expressions like:
            "$issuer.jurisdiction == $subject.country"

        These are returned as-is for the executor to evaluate,
        since they require access to credential attribute data.

        Args:
            edge_type: The edge type to get constraints for

        Returns:
            Dict mapping field names to constraint expressions
        """
        constraints: dict[str, str] = {}
        rules = self._framework.get_rules_for(edge_type)
        for rule in rules:
            constraints.update(rule.field_constraints)
        return constraints
