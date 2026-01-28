# -*- encoding: utf-8 -*-
"""
Tests for KGQL governance enforcement.

Tests:
- GovernanceViolation exception
- enforce_governance flag
- LoA constraint checking
- Edge operator enforcement
"""

import pytest
from unittest.mock import Mock, MagicMock

from kgql.exceptions import (
    GovernanceViolation,
    GovernanceViolationDetail,
    LoAInsufficientError,
)


class TestGovernanceViolationDetail:
    """Tests for GovernanceViolationDetail dataclass."""

    def test_creation(self):
        """Test creating a violation detail."""
        detail = GovernanceViolationDetail(
            rule_name="test_rule",
            message="Test violation message",
            edge_type="iss",
            operator_found="NI2I",
            operator_required="DI2I",
            source_said="ESOURCE123",
            target_said="ETARGET456",
            framework_said="EFRAMEWORK789",
        )
        assert detail.rule_name == "test_rule"
        assert detail.edge_type == "iss"
        assert detail.operator_found == "NI2I"
        assert detail.operator_required == "DI2I"

    def test_to_dict(self):
        """Test serialization to dict."""
        detail = GovernanceViolationDetail(
            rule_name="rule1",
            message="Violation occurred",
        )
        d = detail.to_dict()
        assert d["rule_name"] == "rule1"
        assert d["message"] == "Violation occurred"


class TestGovernanceViolation:
    """Tests for GovernanceViolation exception."""

    def test_basic_creation(self):
        """Test basic exception creation."""
        exc = GovernanceViolation("Test violation")
        assert str(exc) == "Test violation"
        assert exc.violations == []
        assert exc.framework_said == ""

    def test_with_violations(self):
        """Test exception with violation details."""
        details = [
            GovernanceViolationDetail(
                rule_name="rule1",
                message="First violation",
            ),
            GovernanceViolationDetail(
                rule_name="rule2",
                message="Second violation",
            ),
        ]
        exc = GovernanceViolation(
            message="Multiple violations",
            violations=details,
            framework_said="EFRAMEWORK123",
        )
        assert len(exc.violations) == 2
        assert exc.framework_said == "EFRAMEWORK123"

    def test_from_check_result(self):
        """Test creating from a CheckResult."""
        # Mock a CheckResult
        mock_violation = Mock()
        mock_violation.rule_name = "operator_floor"
        mock_violation.message = "Edge requires @DI2I but has @NI2I"
        mock_violation.edge_type = "iss"
        mock_violation.actual_operator = Mock(value="NI2I")
        mock_violation.required_operator = Mock(value="DI2I")

        mock_result = Mock()
        mock_result.framework_said = "EFRAMEWORK456"
        mock_result.violations = [mock_violation]

        exc = GovernanceViolation.from_check_result(
            mock_result,
            source_said="ESOURCE",
            target_said="ETARGET",
            query_context="TRAVERSE iss",
        )

        assert exc.framework_said == "EFRAMEWORK456"
        assert len(exc.violations) == 1
        assert exc.violations[0].rule_name == "operator_floor"
        assert exc.query_context == "TRAVERSE iss"

    def test_to_dict(self):
        """Test serialization to dict."""
        exc = GovernanceViolation(
            message="Violation",
            violations=[
                GovernanceViolationDetail(rule_name="r1", message="v1"),
            ],
            framework_said="EFW123",
        )
        d = exc.to_dict()
        assert d["error"] == "GovernanceViolation"
        assert d["framework_said"] == "EFW123"
        assert len(d["violations"]) == 1


class TestLoAInsufficientError:
    """Tests for LoAInsufficientError exception."""

    def test_creation(self):
        """Test creating LoA insufficient error."""
        exc = LoAInsufficientError(
            message="LoA 1 does not satisfy required LoA 2",
            actual_loa=1,
            required_loa=2,
            credential_said="ECRED123",
        )
        assert exc.actual_loa == 1
        assert exc.required_loa == 2
        assert exc.credential_said == "ECRED123"

    def test_to_dict(self):
        """Test serialization to dict."""
        exc = LoAInsufficientError(
            message="Insufficient LoA",
            actual_loa=0,
            required_loa=3,
        )
        d = exc.to_dict()
        assert d["error"] == "LoAInsufficientError"
        assert d["actual_loa"] == 0
        assert d["required_loa"] == 3


class TestLoAPrimitives:
    """Tests for LoA primitives in keri-governance."""

    def test_loa_satisfies(self):
        """Test LoA satisfaction checking."""
        from keri_governance.primitives import LoALevel, loa_satisfies

        # Equal satisfies
        assert loa_satisfies(LoALevel.LOA_2, LoALevel.LOA_2)

        # Higher satisfies lower
        assert loa_satisfies(LoALevel.VLEI, LoALevel.LOA_0)
        assert loa_satisfies(LoALevel.LOA_3, LoALevel.LOA_1)

        # Lower does not satisfy higher
        assert not loa_satisfies(LoALevel.LOA_0, LoALevel.LOA_1)
        assert not loa_satisfies(LoALevel.LOA_2, LoALevel.VLEI)

    def test_loa_from_credential(self):
        """Test extracting LoA from credential."""
        from keri_governance.primitives import LoALevel, loa_from_credential

        # Credential with LoA
        cred_with_loa = {
            "d": "ESAID123",
            "a": {
                "d": "EATTR123",
                "loa": 2,
            }
        }
        assert loa_from_credential(cred_with_loa) == LoALevel.LOA_2

        # Credential without LoA
        cred_no_loa = {
            "d": "ESAID456",
            "a": {
                "name": "Test",
            }
        }
        assert loa_from_credential(cred_no_loa) == LoALevel.LOA_0

        # Empty credential
        assert loa_from_credential({}) == LoALevel.LOA_0

    def test_loa_to_strength(self):
        """Test LoA to strength level mapping."""
        from keri_governance.primitives import (
            LoALevel,
            StrengthLevel,
            loa_to_strength,
        )

        assert loa_to_strength(LoALevel.LOA_0) == StrengthLevel.ANY
        assert loa_to_strength(LoALevel.LOA_1) == StrengthLevel.SAID_ONLY
        assert loa_to_strength(LoALevel.LOA_2) == StrengthLevel.KEL_ANCHORED
        assert loa_to_strength(LoALevel.LOA_3) == StrengthLevel.TEL_ANCHORED
        assert loa_to_strength(LoALevel.VLEI) == StrengthLevel.TEL_ANCHORED


class TestConstraintCheckerLoA:
    """Tests for LoA checking in ConstraintChecker."""

    @pytest.fixture
    def mock_framework(self):
        """Create a mock governance framework."""
        framework = Mock()
        framework.said = "EFRAMEWORK_TEST"
        framework.name = "Test Framework"
        framework.get_rules_for = Mock(return_value=[])
        framework.get_matrix_entry = Mock(return_value=None)
        return framework

    def test_check_loa_pass(self, mock_framework):
        """Test check_loa passes when LoA is sufficient."""
        from keri_governance.checker import ConstraintChecker
        from keri_governance.primitives import LoALevel

        checker = ConstraintChecker(mock_framework)
        cred = {"d": "ECRED", "a": {"loa": 2}}

        result = checker.check_loa(cred, LoALevel.LOA_2)
        assert result.allowed
        assert len(result.violations) == 0

    def test_check_loa_fail(self, mock_framework):
        """Test check_loa fails when LoA is insufficient."""
        from keri_governance.checker import ConstraintChecker
        from keri_governance.primitives import LoALevel

        checker = ConstraintChecker(mock_framework)
        cred = {"d": "ECRED", "a": {"loa": 1}}

        result = checker.check_loa(cred, LoALevel.LOA_3)
        assert not result.allowed
        assert len(result.violations) == 1
        assert "does not satisfy" in result.violations[0].message

    def test_check_loa_chain_all_pass(self, mock_framework):
        """Test check_loa_chain passes when all credentials meet requirement."""
        from keri_governance.checker import ConstraintChecker
        from keri_governance.primitives import LoALevel

        checker = ConstraintChecker(mock_framework)
        creds = [
            {"d": "ECRED1", "a": {"loa": 3}},
            {"d": "ECRED2", "a": {"loa": 3}},
            {"d": "ECRED3", "a": {"loa": 4}},  # vLEI
        ]

        result = checker.check_loa_chain(creds, LoALevel.LOA_3)
        assert result.allowed
        assert len(result.violations) == 0

    def test_check_loa_chain_some_fail(self, mock_framework):
        """Test check_loa_chain fails when some credentials don't meet requirement."""
        from keri_governance.checker import ConstraintChecker
        from keri_governance.primitives import LoALevel

        checker = ConstraintChecker(mock_framework)
        creds = [
            {"d": "ECRED1", "a": {"loa": 3}},
            {"d": "ECRED2", "a": {"loa": 1}},  # Too low
            {"d": "ECRED3", "a": {"loa": 2}},
        ]

        result = checker.check_loa_chain(creds, LoALevel.LOA_2)
        assert not result.allowed
        assert len(result.violations) == 1  # Only ECRED2 fails
        assert "position 1" in result.violations[0].message


class TestOperatorSatisfaction:
    """Tests for edge operator satisfaction."""

    def test_operator_partial_order(self):
        """Test operator partial order: I2I > DI2I > NI2I > ANY."""
        from keri_governance.primitives import EdgeOperator, operator_satisfies

        # I2I satisfies everything
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.I2I)
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.DI2I)
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.NI2I)
        assert operator_satisfies(EdgeOperator.I2I, EdgeOperator.ANY)

        # DI2I doesn't satisfy I2I
        assert not operator_satisfies(EdgeOperator.DI2I, EdgeOperator.I2I)
        assert operator_satisfies(EdgeOperator.DI2I, EdgeOperator.DI2I)
        assert operator_satisfies(EdgeOperator.DI2I, EdgeOperator.NI2I)

        # NI2I doesn't satisfy DI2I or I2I
        assert not operator_satisfies(EdgeOperator.NI2I, EdgeOperator.I2I)
        assert not operator_satisfies(EdgeOperator.NI2I, EdgeOperator.DI2I)
        assert operator_satisfies(EdgeOperator.NI2I, EdgeOperator.NI2I)

        # ANY only satisfies ANY
        assert not operator_satisfies(EdgeOperator.ANY, EdgeOperator.NI2I)
        assert operator_satisfies(EdgeOperator.ANY, EdgeOperator.ANY)
