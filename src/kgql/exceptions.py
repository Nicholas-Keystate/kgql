# -*- encoding: utf-8 -*-
"""
KGQL Exceptions.

Custom exceptions for KGQL query execution and governance enforcement.
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from keri_governance.checker import ConstraintViolation, CheckResult
    from keri_governance.primitives import EdgeOperator


class KGQLError(Exception):
    """Base exception for all KGQL errors."""
    pass


class QueryParseError(KGQLError):
    """Raised when a KGQL query cannot be parsed."""
    pass


class QueryExecutionError(KGQLError):
    """Raised when query execution fails."""
    pass


@dataclass
class GovernanceViolationDetail:
    """
    Details of a single governance rule violation.

    Captures all information needed to understand what rule was
    violated and how.
    """
    rule_name: str
    message: str
    edge_type: str = ""
    operator_found: str = ""
    operator_required: str = ""
    source_said: str = ""
    target_said: str = ""
    framework_said: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "rule_name": self.rule_name,
            "message": self.message,
            "edge_type": self.edge_type,
            "operator_found": self.operator_found,
            "operator_required": self.operator_required,
            "source_said": self.source_said,
            "target_said": self.target_said,
            "framework_said": self.framework_said,
        }


class GovernanceViolation(KGQLError):
    """
    Raised when a query violates governance framework constraints.

    This exception is raised during query execution when enforce_governance=True
    and an edge traversal violates a rule defined in the active governance framework.

    Attributes:
        violations: List of GovernanceViolationDetail describing each violation
        framework_said: SAID of the governance framework that was violated
        query_context: Optional string describing where in the query the violation occurred

    Usage:
        try:
            result = kgql.query(
                "WITHIN FRAMEWORK $fw MATCH (c:Credential)-[:iss]->(i)",
                variables={"fw": "EFRAMEWORK_SAID"},
                enforce_governance=True
            )
        except GovernanceViolation as e:
            print(f"Governance violation: {e}")
            for v in e.violations:
                print(f"  - {v.rule_name}: {v.message}")
    """

    def __init__(
        self,
        message: str,
        violations: Optional[list[GovernanceViolationDetail]] = None,
        framework_said: str = "",
        query_context: str = "",
    ):
        """
        Initialize a GovernanceViolation exception.

        Args:
            message: Human-readable summary of the violation
            violations: List of detailed violation information
            framework_said: SAID of the governance framework
            query_context: Where in the query the violation occurred
        """
        super().__init__(message)
        self.violations = violations or []
        self.framework_said = framework_said
        self.query_context = query_context

    @classmethod
    def from_check_result(
        cls,
        check_result: "CheckResult",
        source_said: str = "",
        target_said: str = "",
        query_context: str = "",
    ) -> "GovernanceViolation":
        """
        Create a GovernanceViolation from a ConstraintChecker's CheckResult.

        Args:
            check_result: CheckResult from ConstraintChecker.check_edge()
            source_said: SAID of the source credential in the edge
            target_said: SAID of the target credential in the edge
            query_context: Optional context about where violation occurred

        Returns:
            GovernanceViolation exception ready to raise
        """
        violations = []
        for cv in check_result.violations:
            violations.append(GovernanceViolationDetail(
                rule_name=cv.rule_name,
                message=cv.message,
                edge_type=cv.edge_type,
                operator_found=cv.actual_operator.value if cv.actual_operator else "",
                operator_required=cv.required_operator.value if cv.required_operator else "",
                source_said=source_said,
                target_said=target_said,
                framework_said=check_result.framework_said,
            ))

        # Build summary message
        if len(violations) == 1:
            summary = f"Governance violation: {violations[0].message}"
        else:
            summary = f"Governance violations ({len(violations)} rules violated)"

        return cls(
            message=summary,
            violations=violations,
            framework_said=check_result.framework_said,
            query_context=query_context,
        )

    def to_dict(self) -> dict:
        """Convert exception to dictionary representation."""
        return {
            "error": "GovernanceViolation",
            "message": str(self),
            "framework_said": self.framework_said,
            "query_context": self.query_context,
            "violations": [v.to_dict() for v in self.violations],
        }


class LoAInsufficientError(GovernanceViolation):
    """
    Raised when a credential's LoA level is insufficient for an operation.

    This is a specialization of GovernanceViolation for Hardman's
    Level of Assurance constraints.
    """

    def __init__(
        self,
        message: str,
        actual_loa: int,
        required_loa: int,
        credential_said: str = "",
        **kwargs,
    ):
        """
        Initialize an LoAInsufficientError.

        Args:
            message: Human-readable description
            actual_loa: The LoA level the credential has
            required_loa: The LoA level that was required
            credential_said: SAID of the credential that failed the check
            **kwargs: Additional arguments passed to GovernanceViolation
        """
        super().__init__(message, **kwargs)
        self.actual_loa = actual_loa
        self.required_loa = required_loa
        self.credential_said = credential_said

    def to_dict(self) -> dict:
        """Convert exception to dictionary representation."""
        d = super().to_dict()
        d.update({
            "error": "LoAInsufficientError",
            "actual_loa": self.actual_loa,
            "required_loa": self.required_loa,
            "credential_said": self.credential_said,
        })
        return d
