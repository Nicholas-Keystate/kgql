"""
KGQL Governance - Framework credential schema and constraint evaluation.

Implements KGQL Phase 4: Governance Frameworks. Enables queries like:

    WITHIN FRAMEWORK 'EFrameworkSAID...'
    MATCH (qvi:QVI)-[:authorized @DI2I]->(agent:Agent)
    WHERE qvi.jurisdiction = agent.country

This module provides:
- GovernanceFramework: Parsed governance framework credential
- ConstraintRule: Individual rule within a framework
- FrameworkResolver: Resolves framework SAIDs to GovernanceFramework objects
- ConstraintChecker: Evaluates constraints during query execution
"""

from kgql.governance.schema import (
    GovernanceFramework,
    ConstraintRule,
    RuleEnforcement,
    CredentialMatrixEntry,
    FrameworkVersion,
)
from kgql.governance.resolver import FrameworkResolver
from kgql.governance.checker import ConstraintChecker

__all__ = [
    "GovernanceFramework",
    "ConstraintRule",
    "RuleEnforcement",
    "CredentialMatrixEntry",
    "FrameworkVersion",
    "FrameworkResolver",
    "ConstraintChecker",
]
