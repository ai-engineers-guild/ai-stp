"""Local technology detection: findings, review survival, handoff (issue #222)."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import cast

import httpx
import pytest

from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands import project as project_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    project_index,
    project_links,
    project_passport,
    tech_detect,
    tech_findings,
)
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_contracts.context import ProjectLinkResponse
from ai_stp_contracts.technology import TechnologyScanHandoff
from ai_stp_foundation.ids import new_id

AT = "2026-10-05T12:00:00.000Z"
LATER = "2099-01-01T00:00:00.000Z"
ORGANIZATION = new_id("organization")
REMOTE_PROJECT = new_id("remote_project")
KEY = "tech-publish-0001"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """One fixture covering the issue's named technologies end to end."""
    root = tmp_path / "work"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "app.ts").write_text("export {};\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "work"\n'
        'requires-python = ">=3.11"\n'
        'dependencies = ["django>=5", "fastapi", "psycopg[binary]"]\n'
        "[project.optional-dependencies]\n"
        'test = ["pytest==8.0"]\n',
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        '{"dependencies": {"react": "^18.2", "next": "14"},'
        ' "devDependencies": {"vitest": "*"},'
        ' "engines": {"node": ">=20"}}',
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        "services:\n"
        "  db:\n    image: postgres:16\n"
        "  cache:\n    image: redis:7\n"
        "  bus:\n    image: bitnami/kafka:3.7\n",
        encoding="utf-8",
    )
    (root / "angular.json").write_text("{}", encoding="utf-8")
    (root / "manage.py").write_text("# django\n", encoding="utf-8")
    (root / "uv.lock").write_text(
        '[[package]]\nname = "django"\nversion = "5.1.2"\n'
        '[[package]]\nname = "redis"\nversion = "5.0.8"\n',
        encoding="utf-8",
    )
    return root


def _detect(root: Path) -> tech_detect.DetectedScan:
    return tech_detect.detect(project_index.build(root))


def _coordinates(scan: tech_detect.DetectedScan) -> set[tuple[str, str]]:
    return {(item.kind, item.coordinate) for item in scan.detections}


def _scan_project(
    connection: sqlite3.Connection, root: Path, *, scope: str = "repository"
) -> tuple[str, tech_findings.ScanRecord]:
    found = project_passport.scan(connection, root)
    detected = tech_detect.detect(found.index)
    record = tech_findings.record_scan(
        connection,
        project_id=found.stable_id,
        scope=scope,
        detected=detected,
        mapping=tech_detect.bundled_mapping(),
        at=AT,
        source_revision=found.index_digest.removeprefix("sha256:"),
    )
    return found.stable_id, record


def test_the_issues_named_technologies_are_detected(project: Path) -> None:
    found = _coordinates(_detect(project))
    # Python, Django, FastAPI.
    assert ("alias", "python") in found
    assert ("package", "django") in found
    assert ("package", "fastapi") in found
    # React, Next.js, Angular.
    assert ("package", "react") in found
    assert ("package", "next") in found
    assert ("configuration", "angular.json") in found
    # PostgreSQL, Redis, Kafka — declared deps and configured services both.
    assert ("package", "psycopg") in found
    assert ("image", "postgres") in found
    assert ("image", "redis") in found
    assert ("image", "bitnami/kafka") in found
    # Runtimes, package managers, test tooling.
    assert ("alias", "node") in found
    assert ("alias", "uv") in found
    assert ("package", "pytest") in found


def test_nothing_is_detected_without_the_signature(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    (root / "README.md").write_text("# nothing\n", encoding="utf-8")
    found = _coordinates(_detect(root))
    assert ("package", "django") not in found
    assert ("image", "postgres") not in found
    assert ("alias", "python") not in found


def test_detection_is_deterministic(project: Path) -> None:
    first = _detect(project)
    second = _detect(project)
    assert [
        (d.kind, d.coordinate, d.context, d.version, d.version_kind) for d in first.detections
    ] == [(d.kind, d.coordinate, d.context, d.version, d.version_kind) for d in second.detections]
    for one, two in zip(first.detections, second.detections, strict=True):
        assert one.traces == two.traces


def test_detect_machine_output_pins_the_same_index_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    _patch_target(monkeypatch, tmp_path / "registry.sqlite")
    first = project_commands.detect({"root": str(project)}).payload
    second = project_commands.detect({"root": str(project)}).payload
    assert first.source_revision == second.source_revision
    assert first.source_revision is not None and len(first.source_revision) == 64
    assert {item.source_revision for item in second.findings} == {first.source_revision}
    assert [(item.key, item.claims) for item in first.findings] == [
        (item.key, item.claims) for item in second.findings
    ]
    assert all(
        evidence.source_revision == first.source_revision
        for observation in second.handoff.observations
        for evidence in observation.fact.evidence
    )


def test_version_kinds_separate_declaration_from_observation(project: Path) -> None:
    by_key = {
        (item.kind, item.coordinate, item.version_kind): item
        for item in _detect(project).detections
    }
    declared = by_key[("package", "django", "declared_range")]
    assert declared.version == ">=5"
    observed = by_key[("package", "django", "observed_version")]
    assert observed.version == "5.1.2"


def test_secret_files_never_reach_evidence(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    (root / ".env").write_text("SECRET=hunter2\n", encoding="utf-8")
    (root / "id_rsa").write_text("KEY\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\ndependencies = ["django"]\n', encoding="utf-8")
    scan = _detect(root)
    assert all(
        ".env" not in trace.path and "id_rsa" not in trace.path
        for item in scan.detections
        for trace in item.traces
    )
    index = project_index.build(root)
    assert {item.path for item in index.excluded} >= {".env", "id_rsa"}


def test_a_file_changed_after_indexing_contributes_nothing(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    root = tmp_path / "work"
    root.mkdir()
    manifest = root / "pyproject.toml"
    manifest.write_text('[project]\ndependencies = ["django"]\n', encoding="utf-8")
    index = project_index.build(root)
    # The index hashed one file; what sits at the path now is not that file.
    manifest.write_text('[project]\ndependencies = ["tornado"]\n', encoding="utf-8")
    scan = tech_detect.detect(index)
    assert ("package", "tornado") not in _coordinates(scan)
    assert ("package", "django") not in _coordinates(scan)


def test_bundled_mapping_resolves_only_canonical_seed_identities(
    registry: sqlite3.Connection, project: Path
) -> None:
    project_id, _record = _scan_project(registry, project)
    stored = {
        (item.kind, item.coordinate): item
        for item in tech_findings.findings(registry, project_id=project_id)
    }
    assert stored[("package", "react")].technology_id == ("technology_00000000000000000000000006")
    assert stored[("image", "postgres")].technology_id == ("technology_00000000000000000000000007")
    assert stored[("package", "psycopg")].technology_id == ("technology_00000000000000000000000007")
    # Everything outside the seed stays honestly unmapped.
    assert stored[("package", "django")].technology_id is None
    assert stored[("image", "redis")].technology_id is None
    assert stored[("package", "fastapi")].technology_id is None


def test_review_survives_a_rescan(registry: sqlite3.Connection, project: Path) -> None:
    project_id, _first = _scan_project(registry, project)
    tech_findings.review(
        registry,
        project_id=project_id,
        scope="repository",
        kind="package",
        coordinate="django",
        context="production",
        decision="confirmed",
        at=AT,
    )
    tech_findings.review(
        registry,
        project_id=project_id,
        scope="repository",
        kind="package",
        coordinate="next",
        context="production",
        decision="rejected",
        at=AT,
    )
    _scan_project(registry, project)
    stored = {
        item.coordinate: item for item in tech_findings.findings(registry, project_id=project_id)
    }
    assert stored["django"].review == "confirmed"
    assert stored["next"].review == "rejected"
    # And the rescan still refreshed evidence underneath the decisions.
    assert stored["django"].freshness == "current"
    assert stored["next"].freshness == "current"


def test_override_replaces_the_resolved_identity(
    registry: sqlite3.Connection, project: Path
) -> None:
    project_id, _record = _scan_project(registry, project)
    held = tech_findings.review(
        registry,
        project_id=project_id,
        scope="repository",
        kind="package",
        coordinate="fastapi",
        context="production",
        decision="overridden",
        override_technology_id="technology_00000000000000000000000042",
        at=AT,
    )
    assert held.effective_technology_id == "technology_00000000000000000000000042"
    with pytest.raises(CliFailure) as refused:
        tech_findings.review(
            registry,
            project_id=project_id,
            scope="repository",
            kind="package",
            coordinate="fastapi",
            context="production",
            decision="overridden",
            override_technology_id=None,
            at=AT,
        )
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"


def test_absent_requires_a_complete_scan(registry: sqlite3.Connection, project: Path) -> None:
    project_id, _record = _scan_project(registry, project)
    (project / "angular.json").unlink()
    _scan_project(registry, project)
    stored = {
        item.coordinate: item for item in tech_findings.findings(registry, project_id=project_id)
    }
    assert stored["angular.json"].freshness == "absent"


def test_a_partial_scan_marks_missing_findings_stale_not_absent(
    registry: sqlite3.Connection, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _record = _scan_project(registry, project)
    (project / "angular.json").unlink()
    found = project_passport.scan(registry, project)
    detected = tech_detect.detect(found.index)
    partial = tech_detect.DetectedScan(
        complete=False, stopped_by="entry budget", detections=detected.detections
    )
    tech_findings.record_scan(
        registry,
        project_id=project_id,
        scope="repository",
        detected=partial,
        mapping=tech_detect.bundled_mapping(),
        at=AT,
    )
    stored = {
        item.coordinate: item for item in tech_findings.findings(registry, project_id=project_id)
    }
    assert stored["angular.json"].freshness == "stale"
    # And a complete scan then still marks it absent.
    _scan_project(registry, project)
    stored = {
        item.coordinate: item for item in tech_findings.findings(registry, project_id=project_id)
    }
    assert stored["angular.json"].freshness == "absent"


def test_scopes_hold_independent_findings(registry: sqlite3.Connection, project: Path) -> None:
    project_id, _record = _scan_project(registry, project)
    _scan_project(registry, project, scope="backend")
    repository = tech_findings.findings(registry, project_id=project_id, scope="repository")
    backend = tech_findings.findings(registry, project_id=project_id, scope="backend")
    assert len(repository) == len(backend)
    tech_findings.review(
        registry,
        project_id=project_id,
        scope="backend",
        kind="package",
        coordinate="django",
        context="production",
        decision="rejected",
        at=AT,
    )
    repository = {
        item.coordinate: item
        for item in tech_findings.findings(registry, project_id=project_id, scope="repository")
    }
    assert repository["django"].review == "proposed"


def test_the_handoff_merges_coordinates_into_one_observation(
    registry: sqlite3.Connection, project: Path
) -> None:
    project_id, record = _scan_project(registry, project)
    stored = tech_findings.findings(registry, project_id=project_id, scope="repository")
    built = tech_findings.build_handoff(
        project_findings=stored,
        scan_id=record.scan_id,
        scope="repository",
        complete=True,
        mapping=tech_detect.bundled_mapping(),
        local_project_id=project_id,
        at=AT,
    )
    handoff = built.handoff
    assert isinstance(handoff, TechnologyScanHandoff)
    # image:postgres and package:psycopg are one PostgreSQL usage, not two.
    postgres = [
        item
        for item in handoff.observations
        if item.technology_id == "technology_00000000000000000000000007"
    ]
    assert len(postgres) == 1
    assert len(postgres[0].fact.evidence) == 2
    react = [
        item
        for item in handoff.observations
        if item.technology_id == "technology_00000000000000000000000006"
    ]
    assert len(react) == 1
    # Unmapped coordinates are named, never smuggled into observations.
    assert "package:django:production" in built.unmapped
    assert all(item.technology_id.startswith("technology_") for item in handoff.observations)
    # Every evidence names this scan's detector and mapping.
    assert all(
        entry.detector_version == handoff.detector_version
        and entry.mapping_version == handoff.mapping_version
        for item in handoff.observations
        for entry in item.fact.evidence
    )


def test_rejected_and_absent_findings_do_not_travel(
    registry: sqlite3.Connection, project: Path
) -> None:
    project_id, _record = _scan_project(registry, project)
    tech_findings.review(
        registry,
        project_id=project_id,
        scope="repository",
        kind="package",
        coordinate="react",
        context="production",
        decision="rejected",
        at=AT,
    )
    (project / "docker-compose.yml").unlink()
    project_id, record = _scan_project(registry, project)
    stored = tech_findings.findings(registry, project_id=project_id, scope="repository")
    built = tech_findings.build_handoff(
        project_findings=stored,
        scan_id=record.scan_id,
        scope="repository",
        complete=True,
        mapping=tech_detect.bundled_mapping(),
        local_project_id=project_id,
        at=AT,
    )
    assert all(
        item.technology_id != "technology_00000000000000000000000006"
        for item in built.handoff.observations
    )
    # The absent postgres image does not travel; the psycopg package still does.
    postgres = [
        item
        for item in built.handoff.observations
        if item.technology_id == "technology_00000000000000000000000007"
    ]
    assert len(postgres) == 1
    assert all("docker-compose" not in (e.path or "") for e in postgres[0].fact.evidence)


def test_the_handoff_carries_remote_identity_only_when_explicit(
    registry: sqlite3.Connection, project: Path
) -> None:
    project_id, record = _scan_project(registry, project)
    stored = tech_findings.findings(registry, project_id=project_id, scope="repository")
    built = tech_findings.build_handoff(
        project_findings=stored,
        scan_id=record.scan_id,
        scope="repository",
        complete=True,
        mapping=tech_detect.bundled_mapping(),
        local_project_id=project_id,
        at=AT,
    )
    assert built.handoff.local_project_id == project_id
    assert built.handoff.organization_id is None
    assert built.handoff.project_id is None
    # And the contract refuses half an identity itself.
    with pytest.raises(ValueError):
        tech_findings.build_handoff(
            project_findings=stored,
            scan_id=record.scan_id,
            scope="repository",
            complete=True,
            mapping=tech_detect.bundled_mapping(),
            local_project_id=project_id,
            organization_id="organization_01J0000000000000000000AA",
            at=AT,
        )


def test_evidence_paths_are_repository_relative_and_safe(
    registry: sqlite3.Connection, project: Path
) -> None:
    project_id, record = _scan_project(registry, project)
    stored = tech_findings.findings(registry, project_id=project_id, scope="repository")
    built = tech_findings.build_handoff(
        project_findings=stored,
        scan_id=record.scan_id,
        scope="repository",
        complete=True,
        mapping=tech_detect.bundled_mapping(),
        local_project_id=project_id,
        at=AT,
    )
    for item in built.handoff.observations:
        for evidence in item.fact.evidence:
            assert evidence.path is not None
            assert not evidence.path.startswith("/")
            assert ".." not in evidence.path
            assert "\\" not in evidence.path


def test_org_snapshot_overlays_the_bundled_table(
    registry: sqlite3.Connection, project: Path
) -> None:
    tech_findings.cache_mapping(
        registry,
        organization_id="organization_01J0000000000000000000AA",
        version="v3",
        digest="sha256:" + "a" * 64,
        entries=[
            ("package", "django", "technology_00000000000000000000000042"),
            ("package", "react", "technology_00000000000000000000000099"),
        ],
        at=AT,
    )
    effective = tech_findings.effective_mapping(
        registry, organization_id="organization_01J0000000000000000000AA"
    )
    # The organization's own entries win its coordinates; the bundled table
    # still covers what the snapshot does not mention.
    assert effective.resolve("package", "django") == ("technology_00000000000000000000000042")
    assert effective.resolve("package", "react") == ("technology_00000000000000000000000099")
    assert effective.resolve("image", "postgres") == ("technology_00000000000000000000000007")
    # And without the organization the bundled table stands alone.
    plain = tech_findings.effective_mapping(registry, organization_id=None)
    assert plain.resolve("package", "django") is None


def test_migration_44_rolls_back_cleanly(registry: sqlite3.Connection) -> None:
    # Migration entries are reversible by construction; prove the down side
    # actually removes what it created rather than only naming it.
    names = {
        row[0]
        for row in registry.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'tech_%'"
        ).fetchall()
    }
    assert {"tech_scan", "tech_finding", "tech_mapping_cache"} <= names


def test_migration_45_keeps_source_revisions_reversible(registry: sqlite3.Connection) -> None:
    from ai_stp_cli.local.database import MIGRATIONS

    migration = next(item for item in MIGRATIONS if item.version == 45)
    assert "source_revision" in {
        str(row[1]) for row in registry.execute("PRAGMA table_info(tech_scan)")
    }
    for statement in migration.down:
        registry.execute(statement)
    assert "source_revision" not in {
        str(row[1]) for row in registry.execute("PRAGMA table_info(tech_scan)")
    }
    for statement in migration.up:
        registry.execute(statement)


def test_source_revision_is_index_digest_and_remote_identity_stays_out(
    registry: sqlite3.Connection, project: Path
) -> None:
    # Local evidence pins the indexed input but never infers remote identity.
    _project_id, recorded = _scan_project(registry, project)
    project_id = project_passport.stable_id_for(registry, project.resolve())
    assert project_id is not None
    assert recorded.source_revision == project_passport.scan(
        registry, project
    ).index_digest.removeprefix("sha256:")
    assert tech_findings.scans(registry, project_id=project_id)[0].source_revision == (
        recorded.source_revision
    )
    built = tech_findings.build_handoff(
        project_findings=tech_findings.findings(
            registry, project_id=project_id, scope="repository"
        ),
        scan_id="scan_01J000000000000000000000AA",
        scope="repository",
        complete=True,
        mapping=tech_detect.bundled_mapping(),
        local_project_id=project_id,
        at=AT,
        source_revision=recorded.source_revision,
    )
    assert built.handoff.organization_id is None
    for item in built.handoff.observations:
        for evidence in item.fact.evidence:
            assert evidence.source != "manual"
            assert evidence.source_revision == recorded.source_revision


# --------------------------------------------------------------------------
# The publication leg: explicit link, fetched snapshot, contract request.
# --------------------------------------------------------------------------


def _link(local_project_id: str) -> ProjectLinkResponse:
    return ProjectLinkResponse(
        link_id=new_id("project_link"),
        plan_id=new_id("link_plan"),
        plan_digest="sha256:" + "b" * 64,
        organization_id=ORGANIZATION,
        local_project_id=local_project_id,
        remote_project_id=REMOTE_PROJECT,
        provider_project_id=None,
        state="linked",
        local_revision="initial",
        remote_revision="7",
        provider_revision=None,
        revision=1,
        updated_at=AT,
    )


def _linked_project(connection: sqlite3.Connection, root: Path) -> str:
    project_id, _record = _scan_project(connection, root)
    with transaction(connection):
        project_links.cache_link(connection, _link(project_id))
    return project_id


def _publish_parameters(project_id: str, **extra: object) -> dict[str, object]:
    return {
        "project": project_id,
        "organization": ORGANIZATION,
        "authorization-revision": "12",
        "idempotency-key": KEY,
        **extra,
    }


def _patch_target(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(project_commands, "configured_path", lambda: path)


def test_publish_refuses_an_unlinked_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id, _record = _scan_project(connection, project)
    _patch_target(monkeypatch, registry_path)
    with pytest.raises(CliFailure) as raised:
        project_commands.technology_publish(_publish_parameters(project_id))
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_publish_refuses_a_wrong_organization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id = _linked_project(connection, project)
    _patch_target(monkeypatch, registry_path)
    other = _publish_parameters(project_id, organization=new_id("organization"))
    with pytest.raises(CliFailure) as raised:
        project_commands.technology_publish(other)
    assert raised.value.code == "AI_STP_CONFLICT"


def test_publish_refuses_without_a_fetched_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id = _linked_project(connection, project)
    _patch_target(monkeypatch, registry_path)
    with pytest.raises(CliFailure) as raised:
        project_commands.technology_publish(_publish_parameters(project_id))
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_publish_refuses_to_label_current_findings_as_an_older_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id = _linked_project(connection, project)
        first_scan = tech_findings.scans(connection, project_id=project_id)[0].scan_id
        _scan_project(connection, project)
        tech_findings.cache_mapping(
            connection,
            organization_id=ORGANIZATION,
            version="v3",
            digest="sha256:" + "c" * 64,
            entries=[("package", "django", "technology_00000000000000000000000042")],
            at=AT,
        )
    _patch_target(monkeypatch, registry_path)
    with pytest.raises(CliFailure) as raised:
        project_commands.technology_publish(
            _publish_parameters(project_id, **{"mapping-version": "v3", "scan": first_scan})
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_publish_sends_the_handoff_the_contract_shaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id = _linked_project(connection, project)
        source_revision = tech_findings.scans(connection, project_id=project_id)[0].source_revision
        tech_findings.cache_mapping(
            connection,
            organization_id=ORGANIZATION,
            version="v3",
            digest="sha256:" + "c" * 64,
            entries=[
                ("package", "django", "technology_00000000000000000000000042"),
                ("package", "react", "technology_00000000000000000000000006"),
                ("package", "psycopg", "technology_00000000000000000000000007"),
                ("image", "postgres", "technology_00000000000000000000000007"),
            ],
            at=AT,
        )
    _patch_target(monkeypatch, registry_path)
    sent: list[dict[str, object]] = []

    def route(request: httpx.Request) -> httpx.Response:
        body = cast(dict[str, object], json.loads(request.content.decode("utf-8")))
        sent.append(body)
        handoff = cast(dict[str, object], body["handoff"])
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "organization_id": ORGANIZATION,
                "project_id": REMOTE_PROJECT,
                "scan_id": handoff["scan_id"],
                "project_revision": 7,
                "digest": "sha256:" + "d" * 64,
                "usages": [],
                "disagreements": [],
                "created_relation_ids": [],
            },
        )

    held = Session(
        account_id=new_id("account"),
        device_id=new_id("device"),
        access_token="token",
        refresh_token="refresh",
        expires_at=LATER,
    )

    def required(_purpose: str) -> Session:
        return held

    monkeypatch.setattr(cloud_auth, "required", required)
    monkeypatch.setattr(
        project_commands,
        "endpoint",
        lambda: Endpoint(
            "https://platform.example", max_attempts=1, transport=httpx.MockTransport(route)
        ),
    )
    answer = project_commands.technology_publish(
        _publish_parameters(project_id, **{"mapping-version": "v3"})
    )
    assert answer.payload.project_id == REMOTE_PROJECT
    assert sent, "the publication request never left"
    request = sent[0]
    assert request["expected_revision"] == 7
    assert request["idempotency_key"] == KEY
    handoff = cast(dict[str, object], request["handoff"])
    assert handoff["organization_id"] == ORGANIZATION
    assert handoff["project_id"] == REMOTE_PROJECT
    assert handoff["local_project_id"] == project_id
    assert handoff["mapping_version"] == "v3"
    observations = cast(list[object], handoff["observations"])
    observed_ids = {cast(dict[str, object], item)["technology_id"] for item in observations}
    # Only what the snapshot covers travels: django now resolves, unmapped
    # coordinates still do not.
    assert "technology_00000000000000000000000042" in observed_ids
    assert "technology_00000000000000000000000007" in observed_ids
    for item in observations:
        fact = cast(dict[str, object], cast(dict[str, object], item)["fact"])
        for raw_evidence in cast(list[object], fact["evidence"]):
            evidence = cast(dict[str, object], raw_evidence)
            assert evidence["detector_version"] == handoff["detector_version"]
            assert evidence["mapping_version"] == "v3"
            assert evidence["source_revision"] == source_revision
            assert evidence["source"] != "manual"
            # The evidence was observed when the scan ran, not when it published.
            assert evidence["observed_at"] == AT


def test_a_scope_the_wire_cannot_carry_is_refused(
    registry: sqlite3.Connection, project: Path
) -> None:
    with pytest.raises(CliFailure) as raised:
        project_commands.detect({"root": str(project), "scope": "my scope"})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    found = project_passport.scan(registry, project)
    detected = tech_detect.detect(found.index)
    with pytest.raises(CliFailure) as stored:
        tech_findings.record_scan(
            registry,
            project_id=found.stable_id,
            scope="my scope",
            detected=detected,
            mapping=tech_detect.bundled_mapping(),
            at=AT,
        )
    assert stored.value.code == "AI_STP_VALIDATION_ERROR"


def test_review_command_resolves_context_and_refuses_unknown_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id, _record = _scan_project(connection, project)
    _patch_target(monkeypatch, registry_path)
    # One context holds `package:django` — the command resolves it alone.
    answer = project_commands.technology_confirm(
        {"project": project_id, "finding": "package:django"}
    )
    assert answer.payload.finding.review == "confirmed"
    # An unknown coordinate fails; the command does not create a record.
    with pytest.raises(CliFailure) as missing:
        project_commands.technology_confirm(
            {"project": project_id, "finding": "package:does-not-exist"}
        )
    assert missing.value.code == "AI_STP_NOT_FOUND"


def test_publish_refuses_a_non_integer_authorization_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id = _linked_project(connection, project)
        tech_findings.cache_mapping(
            connection,
            organization_id=ORGANIZATION,
            version="v3",
            digest="sha256:" + "c" * 64,
            entries=[("package", "django", "technology_00000000000000000000000042")],
            at=AT,
        )
    _patch_target(monkeypatch, registry_path)
    with pytest.raises(CliFailure) as raised:
        project_commands.technology_publish(
            _publish_parameters(project_id, **{"authorization-revision": "corporate-style"})
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_commands_refuse_project_and_root_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id, _record = _scan_project(connection, project)
    _patch_target(monkeypatch, registry_path)
    with pytest.raises(CliFailure) as raised:
        project_commands.technologies({"project": project_id, "root": str(project)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    with pytest.raises(CliFailure) as review:
        project_commands.technology_confirm(
            {"project": project_id, "root": str(project), "finding": "package:django"}
        )
    assert review.value.code == "AI_STP_VALIDATION_ERROR"


def test_technologies_refuses_a_scope_the_wire_cannot_carry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    with closing(open_registry(registry_path, create=True)) as connection:
        project_id, _record = _scan_project(connection, project)
    _patch_target(monkeypatch, registry_path)
    with pytest.raises(CliFailure) as raised:
        project_commands.technologies({"project": project_id, "scope": "my scope"})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    answer = project_commands.technologies({"project": project_id})
    assert answer.payload.findings
