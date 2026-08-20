"""Platform safety-scan suite for publication validate (issues #268/#270/#281).

Pure planner/normalize/policy code is separated from engine adapters so tests
can drive the real path without host binaries.
"""

from __future__ import annotations

from ai_stp_platform.safety.orchestrator import doctor_tools, run_safety_suite, safety_diagnostics
from ai_stp_platform.safety.percent import checks_passed_percent, checks_status
from ai_stp_platform.safety.policy import POLICY_VERSION, SafetyProfile

__all__ = [
    "POLICY_VERSION",
    "SafetyProfile",
    "checks_passed_percent",
    "checks_status",
    "doctor_tools",
    "run_safety_suite",
    "safety_diagnostics",
]
