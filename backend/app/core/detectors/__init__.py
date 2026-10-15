"""Deterministic issue detectors (Phase 2/3).

Importing this package registers all seven detectors in
``detectors.base.REGISTRY`` as a side effect; the pipeline runs every
registered one.
"""

from . import (  # noqa: F401
    circular,
    error_values,
    hardcoded_constant,
    orphan_input,
    pattern_break,
    range_gap,
    unit_mismatch,
)
from .base import REGISTRY, Detector, register, run_all  # noqa: F401

__all__ = ["REGISTRY", "Detector", "register", "run_all"]
