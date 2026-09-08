"""Offline estate-release record (`REL-001`, `ADR-0146`, `ADR-0160`)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError
from release_scripts.build_estate_record import policy_provider_repositories
from release_scripts.validate_estate_record import validate

from ai_stp_contracts.estate_release import (
    REQUIRED_LEGS,
    REQUIRED_PROVIDERS,
    EstateRelease,
    computed_verdict,
)

_COMMIT = "a" * 40
_DIGEST = "sha256:" + "b" * 64


_ATTESTED = (
    "github.com/NDDev-OpenNetwork/antigravity-setup-system",
    "github.com/NDDev-OpenNetwork/claude-setup-system",
    "github.com/NDDev-OpenNetwork/codex-setup-system",
    "github.com/NDDev-OpenNetwork/cursor-setup-system",
    "github.com/NDDev-OpenNetwork/grok-setup-system",
    "github.com/NDDev-OpenNetwork/opencode-setup-system",
    "github.com/NDDev-OpenNetwork/pi-setup-system",
)
_ANTIGRAVITY = "github.com/NDDev-OpenNetwork/antigravity-setup-system"


def _row(
    slice_name: str,
    os_name: str,
    arch: str,
    *,
    result: str = "passed",
    commit: str = _COMMIT,
    tag: str = "0.0.61",
    provider: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "slice": slice_name,
        "os": os_name,
        "arch": arch,
        "run_id": "1",
        "consumer_commit": commit,
        "provider_tag": tag,
        "result": result,
    }
    if provider:
        payload["provider"] = provider
    return payload


def _attested_providers() -> list[dict[str, object]]:
    return [
        {"repository": repository, "commit": "c" * 40, "tag": "0.0.61"} for repository in _ATTESTED
    ]


def _launch_rows(
    *,
    omit: frozenset[str] = frozenset(),
    result_for: dict[str, str] | None = None,
    include_empty_provider: bool = False,
) -> list[dict[str, object]]:
    outcomes = result_for or {}
    rows: list[dict[str, object]] = []
    for repository in _ATTESTED:
        if repository in omit:
            continue
        result = outcomes.get(repository, "passed")
        for os_name, arch in REQUIRED_LEGS:
            provider = "" if include_empty_provider else repository
            rows.append(_row("launch", os_name, arch, result=result, provider=provider))
    return rows


def _qualified_record(**changes: object) -> dict[str, object]:
    payload = _record(
        providers=_attested_providers(),
        required_slices=["software", "launch"],
        evidence=[
            *[_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS],
            *_launch_rows(),
        ],
    )
    payload.update(changes)
    return payload


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
    payload = _qualified_record()
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


def test_builder_writes_an_honest_incomplete_one_wheel_record(tmp_path: Path) -> None:
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(f"{'b' * 64}  ai_stp_cli-0.0.17-py3-none-any.whl\n", encoding="utf-8")
    output = tmp_path / "estate.json"
    from release_scripts.build_estate_record import main

    assert (
        main(
            [
                "--version",
                "0.0.17",
                "--commit",
                _COMMIT,
                "--tag",
                "v0.0.17",
                "--checksums",
                str(checksums),
                "--output",
                str(output),
                "--required-slice",
                "software",
                "--limitation",
                "six-leg matrix was not run on this consumer SHA",
                "--created-at",
                "2026-09-04T00:00:00.000Z",
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["verdict"] == "incomplete"
    assert payload["distributions"][0]["name"] == "ai-stp-cli"
    assert validate(output) == []


def test_software_legs_alone_cannot_be_complete() -> None:
    """A consumer wheel matrix is not a system qualification (A22)."""
    record = EstateRelease.model_validate(_record())
    assert computed_verdict(record) == "incomplete"


def test_omitting_antigravity_launch_cells_cannot_be_complete() -> None:
    payload = _qualified_record(
        evidence=[
            *[_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS],
            *_launch_rows(omit=frozenset({_ANTIGRAVITY})),
        ]
    )
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_skipping_antigravity_launch_cannot_be_complete() -> None:
    payload = _qualified_record(
        evidence=[
            *[_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS],
            *_launch_rows(result_for={_ANTIGRAVITY: "skipped"}),
        ]
    )
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_failed_antigravity_launch_stays_failed_with_a_known_limitation() -> None:
    payload = _qualified_record(
        evidence=[
            *[_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS],
            *_launch_rows(result_for={_ANTIGRAVITY: "failed"}),
        ],
        known_limitations=["antigravity launch is undeclared: empty config_home_env"],
        verdict="failed",
    )
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "failed"


def test_a_known_limitation_does_not_fill_a_missing_launch_cell() -> None:
    payload = _qualified_record(
        evidence=[
            *[_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS],
            *_launch_rows(omit=frozenset({_ANTIGRAVITY})),
        ],
        known_limitations=["antigravity launch is undeclared: empty config_home_env"],
        verdict="complete",
    )
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_a_launch_row_without_provider_does_not_fill_a_harness_cell() -> None:
    payload = _qualified_record(
        evidence=[
            *[_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS],
            *_launch_rows(include_empty_provider=True),
        ]
    )
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_a_launch_tag_mismatch_does_not_fill_that_provider_cell() -> None:
    rows = _launch_rows()
    for row in rows:
        if row.get("provider") == _ANTIGRAVITY:
            row["provider_tag"] = "0.0.00"
    payload = _qualified_record(
        evidence=[
            *[_row("software", os_name, arch) for os_name, arch in REQUIRED_LEGS],
            *rows,
        ]
    )
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_fewer_than_seven_attested_providers_cannot_be_complete() -> None:
    payload = _qualified_record(providers=_attested_providers()[:-1])
    record = EstateRelease.model_validate(payload)
    assert computed_verdict(record) == "incomplete"


def test_seven_by_six_passed_launch_cells_can_be_complete() -> None:
    record = EstateRelease.model_validate(_qualified_record())
    assert computed_verdict(record) == "complete"


def test_required_providers_match_the_attested_policy() -> None:
    assert frozenset(REQUIRED_PROVIDERS) == frozenset(policy_provider_repositories())


def test_artifacts_must_match_the_recorded_digest(tmp_path: Path) -> None:
    payload = _record()
    payload["verdict"] = "incomplete"
    payload["required_slices"] = []
    filename = "ai_stp_cli-0.0.17-py3-none-any.whl"
    body = b"wheel-bytes"
    digest = "sha256:" + sha256(body).hexdigest()
    payload["distributions"] = [
        {
            "name": "ai-stp-cli",
            "version": "0.0.17",
            "filename": filename,
            "digest": digest,
        }
    ]
    place = tmp_path / "estate.json"
    place.write_text(json.dumps(payload), encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / filename).write_bytes(body)
    assert validate(place, artifacts=artifacts) == []
    (artifacts / filename).write_bytes(b"tampered")
    problems = validate(place, artifacts=artifacts)
    assert problems
    assert "digest" in problems[0]


def test_a_missing_artifacts_file_is_refused(tmp_path: Path) -> None:
    payload = _record()
    payload["verdict"] = "incomplete"
    payload["required_slices"] = []
    place = tmp_path / "estate.json"
    place.write_text(json.dumps(payload), encoding="utf-8")
    artifacts = tmp_path / "empty"
    artifacts.mkdir()
    problems = validate(place, artifacts=artifacts)
    assert problems
    assert "missing artifact" in problems[0]
