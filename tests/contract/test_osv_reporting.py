"""Dependency checks keep informational notices visible without accepting incomplete scans."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from scripts.safety.report_osv import assess


def notice() -> dict[str, Any]:
    return {
        "id": "RUSTSEC-2026-0370",
        "summary": "`zvariant` is unmaintained",
        "affected": [
            {
                "package": {"name": "zvariant", "ecosystem": "crates.io"},
                "database_specific": {
                    "informational": "unmaintained",
                    "cvss": None,
                    "categories": [],
                },
            }
        ],
    }


def report(advisories: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "results": [
            {
                "source": {"path": "/private/checkout/Cargo.lock", "type": "lockfile"},
                "packages": [
                    {
                        "package": {
                            "name": "zvariant",
                            "version": "5.15.0",
                            "ecosystem": "crates.io",
                        },
                        "vulnerabilities": advisories,
                    }
                ],
            }
        ],
    }


def test_reports_the_complete_maintenance_advisory_without_an_ignore_or_machine_path() -> None:
    advisory = notice()
    status, output = assess(report([advisory]), 1, "apps/desktop/src-tauri/Cargo.lock")
    assert status == 0
    assert output["maintenance_notices"] == 1
    assert output["vulnerabilities"] == 0
    assert output["osv"]["results"][0]["packages"][0]["vulnerabilities"] == [advisory]
    assert output["osv"]["results"][0]["source"]["path"] == "apps/desktop/src-tauri/Cargo.lock"


@pytest.mark.parametrize(
    "change",
    [
        "title_only",
        "score",
        "cve",
        "category",
        "wrong_package",
        "wrong_database",
        "wrong_ecosystem",
    ],
)
def test_never_treats_unknown_or_security_findings_as_maintenance(change: str) -> None:
    advisory = notice()
    metadata = advisory["affected"][0]["database_specific"]
    if change == "title_only":
        del metadata["informational"]
    elif change == "score":
        advisory["severity"] = [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}
        ]
    elif change == "cve":
        advisory["aliases"] = ["CVE-2026-12345"]
    elif change == "category":
        metadata["categories"] = ["code-execution"]
    elif change == "wrong_package":
        advisory["affected"][0]["package"]["name"] = "another-package"
    elif change == "wrong_database":
        advisory["id"] = "GHSA-abcd-abcd-abcd"
    else:
        advisory["affected"][0]["package"]["ecosystem"] = "npm"
    status, output = assess(report([advisory]), 1, "Cargo.lock")
    assert status == 1
    assert output["vulnerabilities"] == 1
    assert output["maintenance_notices"] == 0


def test_an_actual_vulnerability_after_a_maintenance_notice_still_fails() -> None:
    vulnerability = {
        "id": "GHSA-abcd-abcd-abcd",
        "summary": "A vulnerability with no severity or fix",
    }
    status, output = assess(report([notice(), vulnerability]), 1, "Cargo.lock")
    assert status == 1
    assert output["maintenance_notices"] == output["vulnerabilities"] == 1


@pytest.mark.parametrize("scanner_status", [2, 127, 128, -9])
def test_a_failed_scanner_never_passes_even_with_a_maintenance_payload(scanner_status: int) -> None:
    with pytest.raises(ValueError, match="scanner failed"):
        assess(report([notice()]), scanner_status, "Cargo.lock")


@pytest.mark.parametrize("results", [None, []])
def test_accepts_a_successful_empty_scan(results: Any) -> None:
    assert assess({"results": results}, 0, "Cargo.lock")[0] == 0


MALFORMED_REPORTS: list[dict[str, Any]] = [
    {},
    {"results": "invalid"},
    {"results": [{"source": {}}]},
]


@pytest.mark.parametrize("payload", MALFORMED_REPORTS)
def test_rejects_incomplete_or_malformed_results(payload: Any) -> None:
    with pytest.raises((ValueError, KeyError)):
        assess(copy.deepcopy(payload), 0, "Cargo.lock")


def test_findings_exit_without_advisories_is_a_failed_scan() -> None:
    with pytest.raises(ValueError, match="without inspectable advisories"):
        assess({"results": []}, 1, "Cargo.lock")


def test_a_scanner_success_cannot_hide_a_vulnerability_in_the_report() -> None:
    assert assess(report([{"id": "GHSA-abcd-abcd-abcd"}]), 0, "Cargo.lock")[0] == 1
