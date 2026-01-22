"""
KGQL Wrappers - Thin wrappers over existing keripy infrastructure.

These wrappers provide a consistent interface without duplicating any logic.
All actual work is delegated to existing keripy classes.
"""

from kgql.wrappers.reger_wrapper import RegerWrapper
from kgql.wrappers.verifier_wrapper import VerifierWrapper

__all__ = [
    "RegerWrapper",
    "VerifierWrapper",
]
