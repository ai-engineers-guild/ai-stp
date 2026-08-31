"""Verify that native provider-network evidence states the exact trust boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

TRUSTED_UNISOLATED_PLATFORMS = frozenset({"darwin", "windows"})
TRUST_REASONS = frozenset({"explicit_unverified_provider", "trusted_release"})


class NetworkEvidenceError(RuntimeError):
    """The report does not describe a supported network/trust boundary."""


def verify_network_evidence(document: object, expected_os: str) -> None:
    """Require enforced isolation or the one explicitly trusted exception."""
    if not isinstance(document, dict) or document.get("ok") is not True:
        raise NetworkEvidenceError("provider network did not return a successful envelope")
    data = document.get("data")
    if not isinstance(data, dict) or data.get("os_name") != expected_os:
        raise NetworkEvidenceError("provider network did not report the native operating system")

    report = cast(dict[str, object], data)
    enforcement = report.get("network_enforcement")
    phase = report.get("v3_local_phase")
    reasons = report.get("v3_local_phase_reasons")
    if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
        raise NetworkEvidenceError("provider network returned invalid v3 trust reasons")
    reason_set = frozenset(cast(list[str], reasons))

    if enforcement == "enforced":
        if report.get("local_actions_available") is not True:
            raise NetworkEvidenceError("enforced launcher is not available to local actions")
        if phase != "network_denied" or reason_set:
            raise NetworkEvidenceError("enforced launcher did not deny the v3 local phase network")
        return

    if enforcement != "unavailable" or report.get("local_actions_available") is not False:
        raise NetworkEvidenceError("provider network reported an unknown enforcement state")
    if expected_os in TRUSTED_UNISOLATED_PLATFORMS:
        if phase != "unisolated_by_trust" or reason_set != TRUST_REASONS:
            raise NetworkEvidenceError("unisolated v3 phase lacks the exact trust reasons")
        return
    if phase != "refused" or reason_set:
        raise NetworkEvidenceError("missing Linux launcher did not refuse the v3 local phase")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-os", required=True, choices=("darwin", "linux", "windows"))
    arguments = parser.parse_args()
    try:
        document = json.loads(arguments.report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise NetworkEvidenceError("provider network evidence is unreadable") from error
    verify_network_evidence(document, arguments.expected_os)


if __name__ == "__main__":
    main()
