"""
KGQL Temporal - Key state-scoped query execution.

Implements KGQL Phase 5.1: AT KEYSTATE temporal queries. Enables queries like:

    AT KEYSTATE(aid='EAID...', seq=3)
    VERIFY 'ESaid...'

This module provides:
- KeyStateResolver: Resolves AID key state at specific sequence numbers
- KeyStateSnapshot: Captured key state at a point in the KEL
- TemporalVerifier: Verifies credentials against historical key states
"""

from kgql.temporal.resolver import KeyStateResolver, KeyStateSnapshot
from kgql.temporal.verifier import TemporalVerifier

__all__ = [
    "KeyStateResolver",
    "KeyStateSnapshot",
    "TemporalVerifier",
]
