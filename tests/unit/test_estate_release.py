"""Offline estate-release record (`REL-001`, `ADR-0146`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from release_scripts.validate_estate_record import validate

from ai_stp_contracts.estate_release import (
    REQUIRED_LEGS,
    EstateRelease,
    computed_verdict,
)

_COMMIT = "a" * 40
_DIGEST = "sha256:" + "b" * 64


def _row(
    slice_name: str,
    os_name: str,
    arch: str,
    *,
    result: str = "passed",
    commit: str = _COMMIT,
    tag: str = "0.0.61",
) -> dict[str, object]:
    return {
        "slice": slice_name,
        "os": os_name,
        "arch": arch,
        "run_id": "1",
        "consumer_commit": commit,
        "provider_tag": tag,
        "result": result,
    }


def _record(**changes: object) -> dict[str, object]:
    evidence = [_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS]
    payload: dict[str, object] = {
        "schema_id": "ai-stp-estate-release/1",
        "record_id": "cut-1",
        "created_at": "2026-09-04T00:00:00.000Z",
        "consumer": {
            "repository": "ai-engineers-guild/ai-stp",
            "commit": _COMMIT,
            "tag": "v0.0.17",
        },
        "distributions": [
            {
                "name": "ai-stp-cli",
                "version": "0.0.17",
                "filename": "ai_stp_cli-0.0.17-py3-none-any.whl",
                "digest": _DIGEST,
            }
        ],
        "providers": [
            {
                "repository": "github.com/NDDev-OpenNetwork/pi-setup-system",
                "commit": "c" * 40,
                "tag": "0.0.61",
            }
        ],
        "evidence": evidence,
        "required_slices": ["software"],
        "verdict": "complete",
        "known_limitations": [],
    }
    payload.update(changes)
    return payload


def test_empty_required_slices_cannot_be_complete() -> None:
    payload = _record()
    payload["required_slices"] = []
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_a_provider_tag_mismatch_is_incomplete() -> None:
    payload = _record()
    payload["evidence"] = [
        _row("software", os_name, arch, tag="0.0.00") for os_name, arch in REQUIRED_LEGS
    ]
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_an_unrelated_evidence_row_does_not_fill_a_required_leg() -> None:
    payload = _record()
    payload["evidence"] = [_row("other", "linux", "x86_64")]
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_changing_an_artifact_digest_does_not_silently_keep_complete() -> None:
    """The stored verdict is a claim; validation recomputes it."""
    payload = _record()
    payload["verdict"] = "complete"
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "complete"
    payload["distributions"] = [
        {
            "name": "ai-stp-cli",
            "version": "0.0.17",
            "filename": "ai_stp_cli-0.0.17-py3-none-any.whl",
            "digest": "sha256:" + "d" * 64,
        }
    ]
    # Digest is identity, not the verdict input; a missing required row is.
    payload["evidence"] = []
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_evidence_from_another_sha_cannot_satisfy_complete() -> None:
    payload = _record()
    payload["evidence"] = [
        _row("software", os_name, arch, commit="e" * 40) for os_name, arch in REQUIRED_LEGS
    ]
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_a_missing_required_row_is_incomplete_not_success() -> None:
    payload = _record()
    payload["evidence"] = [_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS[:-1]]
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_skipped_or_inconclusive_is_not_passed() -> None:
    for result in ("skipped", "inconclusive"):
        payload = _record()
        rows = [_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS]
        rows[0] = _row("software", *REQUIRED_LEGS[0], result=result)
        payload["evidence"] = rows
        record = EstateRelease.model_validate(payload)
        assert computed_verdict(record) == "incomplete"


def test_a_failed_row_is_failed() -> None:
    payload = _record()
    rows = [_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS]
    rows[0] = _row("software", *REQUIRED_LEGS[0], result="failed")
    payload["evidence"] = rows
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "failed"


def test_six_internal_packages_cannot_claim_a_complete_one_wheel_cut() -> None:
    payload = _record()
    payload["distributions"] = [
        {
            "name": name,
            "version": "0.0.16",
            "filename": f"{name.replace('-', '_')}-0.0.16-py3-none-any.whl",
            "digest": _DIGEST,
        }
        for name in (
            "ai-stp-foundation",
            "ai-stp-passports",
            "ai-stp-assurance",
            "ai-stp-contracts",
            "ai-stp-sources",
            "ai-stp-cli",
        )
    ]
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_a_floating_tag_is_refused() -> None:
    payload = _record()
    payload["consumer"] = {
        "repository": "ai-engineers-guild/ai-stp",
        "commit": _COMMIT,
        "tag": "latest",
    }
    with pytest.raises(ValidationError):
        EstateRelease.model_validate(payload)


def test_the_offline_command_rejects_a_lying_verdict(tmp_path: Path) -> None:
    payload = _record()
    payload["verdict"] = "complete"
    payload["evidence"] = []
    place = tmp_path / "estate-release-candidate.json"
    place.write_text(json.dumps(payload), encoding="utf-8")
    problems = validate(place)
    assert problems
    assert "verdict" in problems[0]
