# -*- encoding: utf-8 -*-
"""
Tests for KGQL Governance Integration - Phase 4.5

End-to-end integration tests covering the full governance workflow:
  Framework credential → Schema parsing → Constraint compilation →
  Query execution with governance context → Versioning/supersession

These tests verify that all Phase 4 components work together.
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
from kgql.governance.resolver import FrameworkResolver, VersionChain
from kgql.governance.checker import ConstraintChecker, operator_satisfies
from kgql.governance.compiler import (
    ConstraintCompiler,
    CompiledFramework,
    compile_field_expression,
)


# ── vLEI-like Framework Credential Fixture ───────────────────────────


def _vlei_credential_v1() -> dict:
    """Raw ACDC credential dict for vLEI framework v1."""
    return {
        "v": "ACDC10JSON000000_",
        "d": "EvLEI_Framework_V1",
        "i": "ESteward_AID_123",
        "s": "EGovernanceSchema_SAID",
        "a": {
            "d": "EAttrs_V1_SAID",
            "name": "vLEI Governance Framework",
            "version": "1.0.0",
            "rules": [
                {
                    "name": "qvi-issuance",
                    "applies_to": "iss",
                    "required_operator": "I2I",
                    "enforcement": "strict",
                    "field_constraints": {
                        "jurisdiction": '$issuer.jurisdiction == $subject.country',
                    },
                },
                {
                    "name": "delegation-depth",
                    "applies_to": "delegation",
                    "required_operator": "DI2I",
                    "enforcement": "strict",
                    "max_delegation_depth": 3,
                },
                {
                    "name": "naming-convention",
                    "applies_to": "iss",
                    "required_operator": "ANY",
                    "enforcement": "advisory",
                    "field_constraints": {
                        "org_name": '$subject.name != "BLOCKED_ORG"',
                    },
                },
            ],
            "credential_matrix": [
                {"action": "issue", "role": "QVI", "required_operator": "I2I", "allowed": True},
                {"action": "issue", "role": "LE", "required_operator": "DI2I", "allowed": True},
                {"action": "issue", "role": "Agent", "required_operator": "ANY", "allowed": False},
                {"action": "revoke", "role": "QVI", "required_operator": "I2I", "allowed": True},
            ],
            "authorities": {
                "stewards": ["ESteward_AID_123"],
                "qvis": ["EQVI_AID_1", "EQVI_AID_2"],
            },
        },
        "e": {},
        "r": {
            "d": "ERules_SAID",
            "human_readable": "vLEI Governance Framework v1.0",
        },
    }


def _vlei_credential_v2() -> dict:
    """Raw ACDC credential dict for vLEI framework v2 (supersedes v1)."""
    cred = _vlei_credential_v1()
    cred["d"] = "EvLEI_Framework_V2"
    cred["a"]["d"] = "EAttrs_V2_SAID"
    cred["a"]["version"] = "2.0.0"
    # v2 tightens delegation depth to 2
    cred["a"]["rules"][1]["max_delegation_depth"] = 2
    # v2 supersedes v1
    cred["e"] = {
        "supersedes": {
            "d": "EvLEI_Framework_V1",
        },
    }
    return cred


# ── Full Pipeline Integration Tests ──────────────────────────────────


class TestFullPipeline:
    """End-to-end: credential → parse → compile → check."""

    def test_credential_to_compiled_framework(self):
        """Parse raw ACDC → GovernanceFramework → CompiledFramework."""
        cred = _vlei_credential_v1()
        fw = GovernanceFramework.from_credential(cred)
        assert fw.said == "EvLEI_Framework_V1"
        assert fw.name == "vLEI Governance Framework"
        assert fw.version == "1.0.0"
        assert len(fw.rules) == 3
        assert len(fw.credential_matrix) == 4

        compiler = ConstraintCompiler()
        compiled = compiler.compile(fw)
        assert isinstance(compiled, CompiledFramework)
        assert compiled.framework_said == "EvLEI_Framework_V1"
        assert "iss" in compiled.field_constraints
        assert len(compiled.field_constraints["iss"]) == 2  # jurisdiction + org_name

    def test_compiled_edge_check_with_field_context(self):
        """Edge check + field constraints in one call."""
        fw = GovernanceFramework.from_credential(_vlei_credential_v1())
        compiled = ConstraintCompiler().compile(fw)

        # I2I edge with matching jurisdiction → fully passes
        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.I2I,
            context={
                "issuer": {"jurisdiction": "US"},
                "subject": {"country": "US", "name": "LegalCorp"},
            },
        )
        assert result.allowed is True
        assert len(result.warnings) == 0

    def test_compiled_edge_check_field_mismatch(self):
        """I2I passes but jurisdiction mismatch → warning."""
        fw = GovernanceFramework.from_credential(_vlei_credential_v1())
        compiled = ConstraintCompiler().compile(fw)

        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.I2I,
            context={
                "issuer": {"jurisdiction": "US"},
                "subject": {"country": "DE", "name": "GermanCorp"},
            },
        )
        assert result.allowed is True  # operator passes
        assert len(result.warnings) >= 1  # field mismatch warning

    def test_compiled_edge_check_operator_fails(self):
        """NI2I on I2I-required edge → blocked."""
        fw = GovernanceFramework.from_credential(_vlei_credential_v1())
        compiled = ConstraintCompiler().compile(fw)

        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.NI2I,
            context={
                "issuer": {"jurisdiction": "US"},
                "subject": {"country": "US", "name": "Corp"},
            },
        )
        assert result.allowed is False

    def test_advisory_naming_warning(self):
        """Advisory rule for blocked org name produces warning."""
        fw = GovernanceFramework.from_credential(_vlei_credential_v1())
        compiled = ConstraintCompiler().compile(fw)

        result = compiled.check_edge_with_context(
            "iss", EdgeOperator.I2I,
            context={
                "issuer": {"jurisdiction": "US"},
                "subject": {"country": "US", "name": "BLOCKED_ORG"},
            },
        )
        assert result.allowed is True  # advisory, not blocking
        # The naming constraint should produce a warning
        assert any("BLOCKED_ORG" in w.message or "name" in w.message
                    for w in result.warnings)


# ── Resolver + Compiler Integration ──────────────────────────────────


class TestResolverCompilerIntegration:
    """FrameworkResolver → ConstraintCompiler pipeline."""

    def test_resolve_and_compile(self):
        """Resolver returns framework, compiler compiles it."""
        cred = _vlei_credential_v1()
        resolver = FrameworkResolver(
            credential_resolver=lambda said: cred if said == cred["d"] else None
        )
        fw = resolver.resolve("EvLEI_Framework_V1")
        assert fw is not None

        compiled = ConstraintCompiler().compile(fw)
        result = compiled.checker.check_edge("iss", EdgeOperator.I2I)
        assert result.allowed is True

    def test_resolve_compile_check_action(self):
        """Full pipeline: resolve → compile → check action."""
        cred = _vlei_credential_v1()
        resolver = FrameworkResolver(
            credential_resolver=lambda said: cred if said == cred["d"] else None
        )
        fw = resolver.resolve("EvLEI_Framework_V1")
        compiler = ConstraintCompiler()
        compiled = compiler.compile(fw)

        # QVI can issue with I2I
        result = compiled.checker.check_action("issue", "QVI", EdgeOperator.I2I)
        assert result.allowed is True

        # Agent cannot issue at all
        result = compiled.checker.check_action("issue", "Agent", EdgeOperator.I2I)
        assert result.allowed is False

        # LE can issue with DI2I
        result = compiled.checker.check_action("issue", "LE", EdgeOperator.DI2I)
        assert result.allowed is True

        # LE cannot issue with NI2I (too weak)
        result = compiled.checker.check_action("issue", "LE", EdgeOperator.NI2I)
        assert result.allowed is False


# ── Versioning + Compilation Integration ─────────────────────────────


class TestVersioningCompilationIntegration:
    """Versioned frameworks compile independently."""

    def test_two_versions_different_constraints(self):
        """v1 and v2 have different delegation depth limits."""
        cred_v1 = _vlei_credential_v1()
        cred_v2 = _vlei_credential_v2()

        fw_v1 = GovernanceFramework.from_credential(cred_v1)
        fw_v2 = GovernanceFramework.from_credential(cred_v2)

        assert fw_v2.supersedes == "EvLEI_Framework_V1"

        compiler = ConstraintCompiler()
        compiled_v1 = compiler.compile(fw_v1)
        compiled_v2 = compiler.compile(fw_v2)

        # v1 allows depth 3
        result = compiled_v1.checker.check_delegation_depth("delegation", 3)
        assert result.allowed is True

        # v2 tightened to depth 2 — depth 3 now fails
        result = compiled_v2.checker.check_delegation_depth("delegation", 3)
        assert result.allowed is False

        # Both allow depth 2
        result = compiled_v1.checker.check_delegation_depth("delegation", 2)
        assert result.allowed is True
        result = compiled_v2.checker.check_delegation_depth("delegation", 2)
        assert result.allowed is True

    def test_version_chain_with_compilation(self):
        """Resolve chain, compile active version."""
        cred_v1 = _vlei_credential_v1()
        cred_v2 = _vlei_credential_v2()

        resolver = FrameworkResolver()
        resolver.register(GovernanceFramework.from_credential(cred_v1))
        resolver.register(GovernanceFramework.from_credential(cred_v2))

        # Active version is v2
        active = resolver.resolve_active("EvLEI_Framework_V1")
        assert active.said == "EvLEI_Framework_V2"

        # Compile the active version
        compiled = ConstraintCompiler().compile(active)
        assert compiled.framework_said == "EvLEI_Framework_V2"

        # v2 depth limit is 2
        result = compiled.checker.check_delegation_depth("delegation", 3)
        assert result.allowed is False

    def test_pinned_vs_active_compilation(self):
        """Pinned (old) version compiles with old rules."""
        cred_v1 = _vlei_credential_v1()
        cred_v2 = _vlei_credential_v2()

        resolver = FrameworkResolver()
        resolver.register(GovernanceFramework.from_credential(cred_v1))
        resolver.register(GovernanceFramework.from_credential(cred_v2))

        compiler = ConstraintCompiler()

        # Pin to v1 — depth 3 allowed
        pinned = resolver.resolve("EvLEI_Framework_V1")
        compiled_pinned = compiler.compile(pinned)
        result = compiled_pinned.checker.check_delegation_depth("delegation", 3)
        assert result.allowed is True

        # Active (v2) — depth 3 not allowed
        active = resolver.resolve_active("EvLEI_Framework_V1")
        compiled_active = compiler.compile(active)
        result = compiled_active.checker.check_delegation_depth("delegation", 3)
        assert result.allowed is False


# ── Operator Algebra Edge Cases ──────────────────────────────────────


class TestOperatorAlgebraEdgeCases:
    """Edge cases in the constraint algebra partial order."""

    @pytest.mark.parametrize("actual,required,expected", [
        (EdgeOperator.I2I, EdgeOperator.I2I, True),
        (EdgeOperator.I2I, EdgeOperator.DI2I, True),
        (EdgeOperator.I2I, EdgeOperator.NI2I, True),
        (EdgeOperator.I2I, EdgeOperator.ANY, True),
        (EdgeOperator.DI2I, EdgeOperator.I2I, False),
        (EdgeOperator.DI2I, EdgeOperator.DI2I, True),
        (EdgeOperator.DI2I, EdgeOperator.NI2I, True),
        (EdgeOperator.DI2I, EdgeOperator.ANY, True),
        (EdgeOperator.NI2I, EdgeOperator.I2I, False),
        (EdgeOperator.NI2I, EdgeOperator.DI2I, False),
        (EdgeOperator.NI2I, EdgeOperator.NI2I, True),
        (EdgeOperator.NI2I, EdgeOperator.ANY, True),
        (EdgeOperator.ANY, EdgeOperator.I2I, False),
        (EdgeOperator.ANY, EdgeOperator.DI2I, False),
        (EdgeOperator.ANY, EdgeOperator.NI2I, False),
        (EdgeOperator.ANY, EdgeOperator.ANY, True),
    ])
    def test_full_algebra_matrix(self, actual, required, expected):
        """Complete 4x4 matrix of operator_satisfies."""
        assert operator_satisfies(actual, required) is expected
