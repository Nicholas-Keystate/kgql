"""
KGQL Governance - Re-exports from keri-governance.

All governance logic now lives in the standalone keri-governance package.
This module provides backwards-compatible imports for existing KGQL code.
"""

from keri_governance.schema import (  # noqa: F401
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
    CredentialMatrixEntry,
    FrameworkVersion,
)
from keri_governance.resolver import FrameworkResolver, VersionChain  # noqa: F401
from keri_governance.checker import ConstraintChecker, operator_satisfies  # noqa: F401
from keri_governance.compiler import (  # noqa: F401
    ConstraintCompiler,
    CompiledFramework,
    CompiledFieldConstraint,
    compile_field_expression,
)
from keri_governance.patterns import (  # noqa: F401
    jurisdiction_match,
    delegation_depth,
    operator_floor,
    role_action_matrix,
    temporal_validity,
    chain_integrity,
    vlei_standard_framework,
)
from keri_governance.evolution import GovernanceEvolution, EvolutionResult  # noqa: F401
from keri_governance.systems import (  # noqa: F401
    SYSTEM_CATALOG,
    build_framework,
    build_all_frameworks,
    register_all_frameworks,
)

__all__ = [
    "GovernanceFramework",
    "ConstraintRule",
    "RuleEnforcement",
    "CredentialMatrixEntry",
    "FrameworkVersion",
    "FrameworkResolver",
    "VersionChain",
    "ConstraintChecker",
    "operator_satisfies",
    "ConstraintCompiler",
    "CompiledFramework",
    "CompiledFieldConstraint",
    "compile_field_expression",
    "GovernanceEvolution",
    "EvolutionResult",
    "SYSTEM_CATALOG",
    "build_framework",
    "build_all_frameworks",
    "register_all_frameworks",
    "jurisdiction_match",
    "delegation_depth",
    "operator_floor",
    "role_action_matrix",
    "temporal_validity",
    "chain_integrity",
    "vlei_standard_framework",
]
