"""The native evidence oracle preserves both isolation and explicit trust paths."""

import pytest
from release_scripts.verify_network_evidence import (
    NetworkEvidenceError,
    verify_network_evidence,
)


def _report(
    os_name: str,
    enforcement: str,
    phase: str,
    reasons: list[str],
    *,
    available: bool,
) -> dict[str, object]:
    return {
        "ok": True,
        "data": {
            "os_name": os_name,
            "network_enforcement": enforcement,
            "local_actions_available": available,
            "v3_local_phase": phase,
            "v3_local_phase_reasons": reasons,
        },
    }


def test_enforced_launcher_denies_the_v3_local_phase_network() -> None:
    verify_network_evidence(
        _report("linux", "enforced", "network_denied", [], available=True), "linux"
    )


def test_missing_linux_launcher_refuses_instead_of_weakening_isolation() -> None:
    verify_network_evidence(
        _report("linux", "unavailable", "refused", [], available=False), "linux"
    )


def test_windows_without_a_launcher_names_both_trust_paths() -> None:
    verify_network_evidence(
        _report(
            "windows",
            "unavailable",
            "unisolated_by_trust",
            ["explicit_unverified_provider", "trusted_release"],
            available=False,
        ),
        "windows",
    )


def test_macos_without_a_proved_launcher_refuses() -> None:
    verify_network_evidence(
        _report("darwin", "unavailable", "refused", [], available=False), "darwin"
    )


def test_unisolated_phase_without_every_trust_reason_is_refused() -> None:
    with pytest.raises(NetworkEvidenceError, match="exact trust reasons"):
        verify_network_evidence(
            _report(
                "windows",
                "unavailable",
                "unisolated_by_trust",
                ["trusted_release"],
                available=False,
            ),
            "windows",
        )


def test_report_for_a_different_operating_system_is_refused() -> None:
    with pytest.raises(NetworkEvidenceError, match="native operating system"):
        verify_network_evidence(
            _report("windows", "enforced", "network_denied", [], available=True), "linux"
        )
