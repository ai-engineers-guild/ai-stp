"""Bounded Nori and askill/Vercel metadata import ports (SPEC-005 REQ-529)."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.local import component_passports, components, interop_sources
from ai_stp_cli.local.database import configured_path, open_registry


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_nori_manifest_discovers_declared_components_as_observed_metadata(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    marker = tmp_path / "executed"
    script = skill / "pwn.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    script.chmod(0o700)
    command = tmp_path / "slashcommands" / "inspect.md"
    command.parent.mkdir()
    command.write_text("Inspect.\n", encoding="utf-8")
    agent = tmp_path / "subagents" / "reviewer.md"
    agent.parent.mkdir()
    agent.write_text("Review.\n", encoding="utf-8")
    _json(
        tmp_path / "nori.json",
        {
            "name": "review-kit",
            "version": "1.2.0",
            "repository": "https://github.com/acme/review-kit",
            "skills": [
                {"id": "review", "name": "Review", "description": "Review", "scripts": ["pwn.sh"]}
            ],
            "subagents": [{"id": "reviewer", "name": "Reviewer", "description": "Review"}],
            "slashcommands": [{"command": "inspect", "description": "Inspect"}],
        },
    )

    result = components.discover_report(project=tmp_path)
    imported = [
        item for item in result.components if item.layout_source == interop_sources.NORI_SOURCE
    ]

    assert [(item.component_type, item.absolute) for item in imported] == [
        ("agent", agent),
        ("command", command),
        ("skill", skill),
    ]
    assert all(item.provenance.kind == "package" for item in imported)
    assert all(item.provenance.state == "observed" for item in imported)
    assert all(item.provenance.repository is None for item in imported)
    assert all(item.provenance.revision is None for item in imported)
    assert not marker.exists()


def test_skill_lock_preserves_exact_folder_digest_without_claiming_commit(
    tmp_path: Path, registry: sqlite3.Connection
) -> None:
    skill = tmp_path / ".agents" / "skills" / "review-kit"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    digest = "a" * 40
    _json(
        tmp_path / ".agents" / ".skill-lock.json",
        {
            "version": 3,
            "skills": {
                "Review Kit": {
                    "source": "acme/review-kit",
                    "sourceType": "github",
                    "sourceUrl": "https://github.com/acme/review-kit",
                    "skillFolderHash": digest,
                    "installedAt": "2026-01-01T00:00:00Z",
                    "updatedAt": "2026-01-01T00:00:00Z",
                }
            },
        },
    )

    candidate = next(
        item
        for item in components.discover(project=tmp_path)
        if item.layout_source == interop_sources.ASKILL_SOURCE
    )
    stored = components.adopt(registry, candidate, device_id="device_test")
    facts = stored.envelope.model_dump(mode="json")["facts"]

    assert candidate.provenance.digest == f"sha1:{digest}"
    assert candidate.provenance.repository is None
    assert candidate.provenance.revision is None
    assert facts["source_digest"]["value"] == f"sha1:{digest}"
    assert facts["source_revision"]["value"] is None
    assert facts["evidence_refs"]["value"] == [".agents/.skill-lock.json"]
    readiness = component_passports.validate_for_publication(registry, stored.stable_id)
    assert readiness.ready is False
    assert "source" in readiness.missing_fields


def test_global_skill_lock_enriches_the_shared_skill_candidate(tmp_path: Path) -> None:
    skill = tmp_path / ".agents" / "skills" / "global-review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    _json(
        tmp_path / ".agents" / ".skill-lock.json",
        {
            "version": 3,
            "skills": {
                "global-review": {
                    "source": "acme/global-review",
                    "skillFolderHash": "b" * 64,
                }
            },
        },
    )

    candidates = components.discover(environment={"HOME": str(tmp_path)})
    matched = [item for item in candidates if item.absolute == skill]

    assert len(matched) == 1
    assert matched[0].scope == "global"
    assert matched[0].layout_source == interop_sources.ASKILL_SOURCE
    assert matched[0].provenance.digest == f"sha256:{'b' * 64}"


@pytest.mark.parametrize(
    "document",
    [
        {"version": 2, "skills": {}},
        {"version": 3, "skills": {"bad": {"source": "x", "skillFolderHash": "latest"}}},
    ],
)
def test_skill_lock_fails_closed_on_unsupported_or_inexact_records(
    tmp_path: Path, document: object
) -> None:
    _json(tmp_path / ".agents" / ".skill-lock.json", document)

    result = interop_sources.discover(tmp_path)

    assert result.candidates == ()
    assert result.diagnostics
    assert all(item.code == "invalid_record" for item in result.diagnostics)


def test_interop_manifests_reject_links_duplicate_keys_and_bounds(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"name":"x","version":"1"}', encoding="utf-8")
    (tmp_path / "nori.json").symlink_to(target)
    linked = interop_sources.discover(tmp_path)
    assert linked.diagnostics[0].reason == "the interop manifest could not be read safely"

    (tmp_path / "nori.json").unlink()
    (tmp_path / "nori.json").write_text('{"name":"a","name":"b","version":"1"}', encoding="utf-8")
    duplicate = interop_sources.discover(tmp_path)
    assert duplicate.candidates == ()
    assert "unambiguous" in duplicate.diagnostics[0].reason

    (tmp_path / "nori.json").write_bytes(b"x" * (interop_sources.MAX_MANIFEST_BYTES + 1))
    oversized = interop_sources.discover(tmp_path)
    assert oversized.candidates == ()
    assert oversized.diagnostics[0].code == "bounded_limit"
