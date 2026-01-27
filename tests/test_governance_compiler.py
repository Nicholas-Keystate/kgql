# -*- encoding: utf-8 -*-
"""
Tests for KGQL Constraint Compiler - Phase 4.3

Tests the compilation pipeline from field constraint expressions
to executable CompiledFieldConstraint and CompiledFramework objects.
"""

import pytest

from kgql.parser.ast import EdgeOperator
from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
    CredentialMatrixEntry,
    FrameworkVersion,
)
from kgql.governance.compiler import (
    compile_field_expression,
    CompiledFieldConstraint,
    CompiledFramework,
    ConstraintCompiler,
)
from kgql.governance.checker import ConstraintChecker


# ── compile_field_expression Tests ───────────────────────────────────


class TestCompileFieldExpression:
    """Parsing field constraint expression strings."""

    def test_field_to_field_equality(self):
        result = compile_field_expression("$issuer.jurisdiction == $subject.country")
        assert result is not None
        assert result.left_role == "issuer"
        assert result.left_field == "jurisdiction"
        assert result.op_str == "=="
        assert result.right_role == "subject"
        assert result.right_field == "country"
        assert result.right_literal is None

    def test_field_to_field_inequality(self):
        result = compile_field_expression("$issuer.level != $subject.min_level")
        assert result is not None
        assert result.op_str == "!="
        assert result.left_role == "issuer"
        assert result.right_role == "subject"

    def test_field_to_field_greater_than(self):
        result = compile_field_expression("$issuer.level > $subject.min_level")
        assert result is not None
        assert result.op_str == ">"

    def test_field_to_field_less_than(self):
        result = compile_field_expression("$issuer.level < $subject.max_level")
        assert result is not None
        assert result.op_str == "<"

    def test_field_to_field_gte(self):
        result = compile_field_expression("$issuer.level >= $subject.min_level")
        assert result is not None
        assert result.op_str == ">="

    def test_field_to_field_lte(self):
        result = compile_field_expression("$issuer.level <= $subject.max_level")
        assert result is not None
        assert result.op_str == "<="

    def test_field_to_literal(self):
        result = compile_field_expression('$subject.name != "forbidden"')
        assert result is not None
        assert result.left_role == "subject"
        assert result.left_field == "name"
        assert result.op_str == "!="
        assert result.right_role is None
        assert result.right_field is None
        assert result.right_literal == "forbidden"

    def test_field_to_literal_equality(self):
        result = compile_field_expression('$issuer.jurisdiction == "US"')
        assert result is not None
        assert result.right_literal == "US"

    def test_whitespace_tolerance(self):
        result = compile_field_expression("  $issuer.jurisdiction == $subject.country  ")
        assert result is not None
        assert result.left_role == "issuer"

    def test_invalid_expression_no_dollar(self):
        result = compile_field_expression("issuer.jurisdiction == subject.country")
        assert result is None

    def test_invalid_expression_no_dot(self):
        result = compile_field_expression("$issuer == $subject")
        assert result is None

    def test_invalid_expression_bad_operator(self):
        result = compile_field_expression("$issuer.field ~= $subject.field")
        assert result is None

    def test_invalid_expression_empty(self):
        result = compile_field_expression("")
        assert result is None

    def test_invalid_expression_garbage(self):
        result = compile_field_expression("not a constraint at all")
        assert result is None

    def test_preserves_original_expression(self):
        expr = "$issuer.jurisdiction == $subject.country"
        result = compile_field_expression(expr)
        assert result.expression == expr


# ── CompiledFieldConstraint.evaluate Tests ───────────────────────────


class TestCompiledFieldConstraintEvaluate:
    """Evaluating compiled field constraints against context."""

    def test_equal_fields_match(self):
        fc = compile_field_expression("$issuer.jurisdiction == $subject.country")
        ctx = {
            "issuer": {"jurisdiction": "US"},
            "subject": {"country": "US"},
        }
        assert fc.evaluate(ctx) is True

    def test_equal_fields_mismatch(self):
        fc = compile_field_expression("$issuer.jurisdiction == $subject.country")
        ctx = {
            "issuer": {"jurisdiction": "US"},
            "subject": {"country": "DE"},
        }
        assert fc.evaluate(ctx) is False

    def test_not_equal_constraint(self):
        fc = compile_field_expression('$subject.name != "forbidden"')
        ctx = {"subject": {"name": "allowed"}}
        assert fc.evaluate(ctx) is True

    def test_not_equal_constraint_fails(self):
        fc = compile_field_expression('$subject.name != "forbidden"')
        ctx = {"subject": {"name": "forbidden"}}
        assert fc.evaluate(ctx) is False

    def test_greater_than(self):
        fc = compile_field_expression("$issuer.level > $subject.min_level")
        ctx = {
            "issuer": {"level": 3},
            "subject": {"min_level": 2},
        }
        assert fc.evaluate(ctx) is True

    def test_greater_than_fails(self):
        fc = compile_field_expression("$issuer.level > $subject.min_level")
        ctx = {
            "issuer": {"level": 2},
            "subject": {"min_level": 2},
        }
        assert fc.evaluate(ctx) is False

    def test_gte_equal_values(self):
        fc = compile_field_expression("$issuer.level >= $subject.min_level")
        ctx = {
            "issuer": {"level": 2},
            "subject": {"min_level": 2},
        }
        assert fc.evaluate(ctx) is True

    def test_missing_left_role(self):
        fc = compile_field_expression("$issuer.jurisdiction == $subject.country")
        ctx = {"subject": {"country": "US"}}
        assert fc.evaluate(ctx) is False

    def test_missing_left_field(self):
        fc = compile_field_expression("$issuer.jurisdiction == $subject.country")
        ctx = {
            "issuer": {"other_field": "US"},
            "subject": {"country": "US"},
        }
        assert fc.evaluate(ctx) is False

    def test_missing_right_role(self):
        fc = compile_field_expression("$issuer.jurisdiction == $subject.country")
        ctx = {"issuer": {"jurisdiction": "US"}}
        assert fc.evaluate(ctx) is False

    def test_missing_right_field(self):
        fc = compile_field_expression("$issuer.jurisdiction == $subject.country")
        ctx = {
            "issuer": {"jurisdiction": "US"},
            "subject": {"other_field": "DE"},
        }
        assert fc.evaluate(ctx) is False

    def test_type_mismatch_returns_false(self):
        fc = compile_field_expression("$issuer.level > $subject.min_level")
        ctx = {
            "issuer": {"level": "not_a_number"},
            "subject": {"min_level": 2},
        }
        assert fc.evaluate(ctx) is False

    def test_empty_context(self):
        fc = compile_field_expression("$issuer.jurisdiction == $subject.country")
        assert fc.evaluate({}) is False


# ── ConstraintCompiler Tests ─────────────────────────────────────────


class TestConstraintCompiler:
    """Compilation pipeline and caching."""

    @pytest.fixture
    def framework_with_fields(self):
        return GovernanceFramework(
            said="ECompilerTest123",
            name="Compiler Test Framework",
            version_info=FrameworkVersion(said="ECompilerTest123", version="1.0.0"),
            rules=[
                ConstraintRule(
                    name="jurisdiction-match",
                    applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                    enforcement=RuleEnforcement.STRICT,
                    field_constraints={
                        "jurisdiction": "$issuer.jurisdiction == $subject.country",
                    },
                ),
                ConstraintRule(
                    name="level-check",
                    applies_to="delegation",
                    required_operator=EdgeOperator.DI2I,
                    enforcement=RuleEnforcement.ADVISORY,
                    field_constraints={
                        "level": "$issuer.level >= $subject.min_level",
                    },
                ),
            ],
        )

    @pytest.fixture
    def framework_no_fields(self):
        return GovernanceFramework(
            said="ENoFields456",
            name="No Fields Framework",
            rules=[
                ConstraintRule(
                    name="simple-op",
                    applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                ),
            ],
        )

    def test_compile_produces_compiled_framework(self, framework_with_fields):
        compiler = ConstraintCompiler()
        compiled = compiler.compile(framework_with_fields)
        assert isinstance(compiled, CompiledFramework)
        assert compiled.framework_said == "ECompilerTest123"

    def test_compile_has_checker(self, framework_with_fields):
        compiler = ConstraintCompiler()
        compiled = compiler.compile(framework_with_fields)
        assert isinstance(compiled.checker, ConstraintChecker)

    def test_compile_field_constraints_populated(self, framework_with_fields):
        compiler = ConstraintCompiler()
        compiled = compiler.compile(framework_with_fields)
        assert "iss" in compiled.field_constraints
        assert "delegation" in compiled.field_constraints
        assert len(compiled.field_constraints["iss"]) == 1
        assert len(compiled.field_constraints["delegation"]) == 1

    def test_compile_no_fields_empty_constraints(self, framework_no_fields):
        compiler = ConstraintCompiler()
        compiled = compiler.compile(framework_no_fields)
        assert len(compiled.field_constraints) == 0

    def test_compile_caching(self, framework_with_fields):
        compiler = ConstraintCompiler()
        first = compiler.compile(framework_with_fields)
        second = compiler.compile(framework_with_fields)
        assert first is second

    def test_is_compiled(self, framework_with_fields):
        compiler = ConstraintCompiler()
        assert not compiler.is_compiled("ECompilerTest123")
        compiler.compile(framework_with_fields)
        assert compiler.is_compiled("ECompilerTest123")

    def test_clear_cache(self, framework_with_fields):
        compiler = ConstraintCompiler()
        compiler.compile(framework_with_fields)
        assert compiler.is_compiled("ECompilerTest123")
        compiler.clear_cache()
        assert not compiler.is_compiled("ECompilerTest123")

    def test_framework_property(self, framework_with_fields):
        compiler = ConstraintCompiler()
        compiled = compiler.compile(framework_with_fields)
        assert compiled.framework is framework_with_fields


# ── CompiledFramework.check_edge_with_context Tests ──────────────────


class TestCompiledFrameworkCheckEdgeWithContext:
    """End-to-end: operator + field constraint evaluation."""

    @pytest.fixture
    def compiled(self):
        fw = GovernanceFramework(
            said="EContextTest789",
            name="Context Test",
            rules=[
                ConstraintRule(
                    name="jurisdiction-match",
                    applies_to="iss",
                    required_operator=EdgeOperator.I2I,
                    enforcement=RuleEnforcement.STRICT,
                    field_constraints={
                        "jurisdiction": "$issuer.jurisdiction == $subject.country",
                    },
                ),
            ],
        )
        compiler = ConstraintCompiler()
        return compiler.compile(fw)

    def test_operator_pass_field_pass(self, compiled):
        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.I2I,
            context={
                "issuer": {"jurisdiction": "US"},
                "subject": {"country": "US"},
            },
        )
        assert result.allowed is True
        assert len(result.warnings) == 0

    def test_operator_pass_field_fail_adds_warning(self, compiled):
        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.I2I,
            context={
                "issuer": {"jurisdiction": "US"},
                "subject": {"country": "DE"},
            },
        )
        # Operator passes, field constraint adds warning (not blocking)
        assert result.allowed is True
        assert len(result.warnings) == 1
        assert "jurisdiction" in result.warnings[0].message

    def test_operator_fail_short_circuits(self, compiled):
        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.NI2I,
        )
        assert result.allowed is False

    def test_no_context_skips_field_check(self, compiled):
        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.I2I,
        )
        assert result.allowed is True
        assert len(result.warnings) == 0

    def test_unmatched_edge_type_no_field_check(self, compiled):
        result = compiled.check_edge_with_context(
            "delegation", EdgeOperator.I2I,
        )
        # No rule for "delegation" in this framework, so allowed
        assert result.allowed is True
