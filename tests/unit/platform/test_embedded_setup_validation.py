# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false
"""Server setup-definition v2 validation (SPEC-057 REQ-5708-REQ-5710, REQ-5718)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from ai_stp_foundation.canonical import JsonValue, from_json_bytes
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentType, SetupVersionPassport
from ai_stp_platform.embedded_validation import (
    _pin_from_scan,  # pyright: ignore[reportPrivateUsage]
    resolve_embedded_setup,
    setup_trust_lane,
)
from ai_stp_platform.publication_logic import execute_publish, execute_validate
from ai_stp_platform.safety.policy import POLICY_VERSION
from ai_stp_platform.safety.types import CheckOutcome, Finding, SafetyScanResult
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN, ImmutableObjectStore
from ai_stp_sources import (
    CATALOG_COLLISION,
    DEFINITION_V1,
    DEFINITION_V2,
    MISSING_EMBEDDED_REF,
    PROHIBITED_REDISTRIBUTION,
    EmbeddedDraft,
    NpmEvidence,
    SourceSnapshot,
    freeze_setup_definition,
    unpack_component_tree,
)
from ai_stp_sources.definition import decode_embedded_artifact, pack_component_tree

pytestmark = pytest.mark.platform

OWNER = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER = "account_01ARZ3NDEKTSV4RRFFQ69G5FAW"
SETUP = "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV"
CATALOG_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
EMBEDDED_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAW"
PATH_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAX"
PACKAGE_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAY"
DIGEST = "sha256:" + "b" * 64
AT = "2026-09-01T00:00:00.000Z"
COMMIT = "a" * 40


def test_exact_registry_snapshot_does_not_rewrite_safety_policy() -> None:
    safety = SafetyScanResult(
        content_digest=DIGEST,
        policy_version=POLICY_VERSION,
        profile="standard",
        outcomes=[
            CheckOutcome(
                check_id="agentic_behavior",
                family="agentic_behavior",
                result="failed",
                findings=[
                    Finding(
                        check_id="agentic_behavior",
                        family="agentic_behavior",
                        rule_id="dependency_floating",
                        severity="high",
                        title="dependency_floating",
                    )
                ],
            )
        ],
    )
    pin = _pin_from_scan(
        stable_id=PACKAGE_ID,
        version="1.0",
        digest=DIGEST,
        safety=safety,
        name="package",
        source_coordinate="pkg:npm/package@1.0",
    )
    assert pin["failed_mandatory"] is True
    assert pin["checks_summary"]["checks"][0]["result"] == "failed"
    assert pin["checks_summary"]["checks"][0]["mandatory"] is True


def _catalog_ref() -> ComponentRef:
    return ComponentRef(stable_id=CATALOG_ID, version="1.0", passport_digest=DIGEST)


def _git_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="git",
        canonical_coordinate=f"git:https://github.com/acme/tool@{COMMIT}:skills/demo",
        exact_identity=COMMIT,
        archive_digest=DIGEST,
        component_digest=DIGEST,
        subpath="skills/demo",
        repository_url="https://github.com/acme/tool",
        github_owner="acme",
        github_name="tool",
        files={"SKILL.md": b"# Demo\n"},
    )


def _path_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="path",
        canonical_coordinate="path:skills/demo",
        exact_identity="skills/demo",
        component_digest=DIGEST,
        files={"SKILL.md": b"# Local\n"},
    )


def _package_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="package",
        canonical_coordinate="package:npm:demo@1.2.3",
        exact_identity="1.2.3",
        archive_digest=DIGEST,
        component_digest=DIGEST,
        files={"package.json": b'{"name":"demo"}\n'},
        package_evidence=NpmEvidence(lockfile_name="package-lock.json"),
    )


def _draft(
    snapshot: SourceSnapshot,
    *,
    stable_id: str,
    name: str = "demo",
    license_spdx: str = "MIT",
    redistribution_allowed: bool = True,
    component_type: ComponentType = "skill",
) -> EmbeddedDraft:
    return EmbeddedDraft(
        snapshot=snapshot,
        component_type=component_type,
        name=name,
        description="Embedded component used in a mixed setup.",
        license_spdx=license_spdx,
        harness_id="claude-code",
        target_scope="global",
        redistribution_allowed=redistribution_allowed,
        stable_id=stable_id,
        managed_paths=(f"skills/{name}/SKILL.md",),
        upstream_project="acme/tool",
        upstream_maintainers=("acme",),
    )


def _freeze(
    *,
    catalog: tuple[ComponentRef, ...] = (),
    embedded: tuple[EmbeddedDraft, ...] = (),
    publisher_id: str = OWNER,
):
    return freeze_setup_definition(
        setup_id=SETUP,
        version="1.0",
        harness_id="claude-code",
        input_digest=DIGEST,
        publisher_id=publisher_id,
        created_at=AT,
        catalog_members=catalog,
        embedded_members=embedded,
        catalog_ids=frozenset(item.stable_id for item in catalog),
    )


async def _passed_scan(**kwargs: Any) -> SafetyScanResult:
    return SafetyScanResult(
        content_digest=str(kwargs.get("content_digest") or DIGEST),
        policy_version=str(kwargs.get("policy_version") or POLICY_VERSION),
        profile="standard",
        outcomes=[
            CheckOutcome(
                check_id="path_denylist",
                family="path",
                result="passed",
                mandatory=True,
            )
        ],
        object_kind="component",
    )


def _session_with_catalog(*rows: Any) -> AsyncMock:
    session = AsyncMock()
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: list(rows)))
    return session


@pytest.mark.asyncio
async def test_unpack_roundtrip_and_v1_definition_is_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packed = pack_component_tree({"SKILL.md": b"# Demo\n"})
    assert unpack_component_tree(packed) == {"SKILL.md": b"# Demo\n"}
    frozen = _freeze(catalog=(_catalog_ref(),))
    assert frozen.format == DEFINITION_V1
    row = SimpleNamespace(
        stable_id=CATALOG_ID,
        version="1.0",
        passport_digest=DIGEST,
        passport_document={"requires_components": [], "managed_paths": []},
        checks_summary={
            "status": "available",
            "checks": [{"check_id": "path_denylist", "result": "passed", "mandatory": True}],
        },
    )
    session = _session_with_catalog(row)
    monkeypatch.setattr(
        "ai_stp_platform.embedded_validation.run_safety_suite",
        _passed_scan,
    )
    resolution = await resolve_embedded_setup(
        session,
        definition_bytes=frozen.payload,
        publisher_id=OWNER,
        public=True,
    )
    assert resolution is not None
    assert resolution.has_embedded is False
    assert resolution.pins[0]["digest_matches"] is True
    assert resolution.scans == []


@pytest.mark.asyncio
async def test_non_definition_artifact_keeps_catalog_only_path() -> None:
    session = _session_with_catalog()
    resolution = await resolve_embedded_setup(
        session,
        definition_bytes=b"PK\x03\x04not-a-definition",
        publisher_id=OWNER,
        public=True,
    )
    assert resolution is None


@pytest.mark.asyncio
async def test_private_mixed_git_package_path_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    scanned: list[bytes] = []

    async def _scan(**kwargs: Any) -> SafetyScanResult:
        payload = kwargs.get("artifact_bytes")
        if isinstance(payload, bytes):
            scanned.append(payload)
        return await _passed_scan(**kwargs)

    monkeypatch.setattr("ai_stp_platform.embedded_validation.run_safety_suite", _scan)
    frozen = _freeze(
        catalog=(_catalog_ref(),),
        embedded=(
            _draft(_git_snapshot(), stable_id=EMBEDDED_ID, name="git-demo"),
            _draft(_path_snapshot(), stable_id=PATH_ID, name="local-demo"),
            _draft(_package_snapshot(), stable_id=PACKAGE_ID, name="pkg-demo"),
        ),
    )
    assert frozen.format == DEFINITION_V2
    row = SimpleNamespace(
        stable_id=CATALOG_ID,
        version="1.0",
        passport_digest=DIGEST,
        passport_document={"requires_components": [], "managed_paths": []},
        checks_summary={
            "status": "available",
            "checks": [{"check_id": "path_denylist", "result": "passed", "mandatory": True}],
        },
    )
    resolution = await resolve_embedded_setup(
        _session_with_catalog(row),
        definition_bytes=frozen.payload,
        publisher_id=OWNER,
        public=False,
    )
    assert resolution is not None
    assert resolution.has_embedded is True
    assert {pin["stable_id"] for pin in resolution.pins} == {
        CATALOG_ID,
        EMBEDDED_ID,
        PATH_ID,
        PACKAGE_ID,
    }
    assert len(scanned) == 3
    assert all(item["result"] == "passed" for item in resolution.bindings)
    assert not any(item["check_id"] == "embedded_redistribution" for item in resolution.bindings)


@pytest.mark.asyncio
async def test_public_mixed_owned_redistributable_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_stp_platform.embedded_validation.run_safety_suite",
        _passed_scan,
    )
    frozen = _freeze(
        catalog=(_catalog_ref(),),
        embedded=(
            _draft(_git_snapshot(), stable_id=EMBEDDED_ID),
            _draft(_path_snapshot(), stable_id=PATH_ID, name="local-demo"),
        ),
    )
    row = SimpleNamespace(
        stable_id=CATALOG_ID,
        version="1.0",
        passport_digest=DIGEST,
        passport_document={"requires_components": [], "managed_paths": []},
        checks_summary={
            "status": "available",
            "checks": [{"check_id": "path_denylist", "result": "passed", "mandatory": True}],
        },
    )
    resolution = await resolve_embedded_setup(
        _session_with_catalog(row),
        definition_bytes=frozen.payload,
        publisher_id=OWNER,
        public=True,
    )
    assert resolution is not None
    assert {item["check_id"]: item["result"] for item in resolution.bindings}[
        "embedded_redistribution"
    ] == "passed"


@pytest.mark.asyncio
async def test_public_unknown_license_and_prohibited_redistribution_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_stp_platform.embedded_validation.run_safety_suite",
        _passed_scan,
    )
    unknown = _freeze(
        embedded=(_draft(_git_snapshot(), stable_id=EMBEDDED_ID, license_spdx="NOASSERTION"),)
    )
    unknown_result = await resolve_embedded_setup(
        _session_with_catalog(),
        definition_bytes=unknown.payload,
        publisher_id=OWNER,
        public=True,
    )
    assert unknown_result is not None
    assert any(
        item["check_id"] == "embedded_redistribution"
        and item["reason"] == PROHIBITED_REDISTRIBUTION
        for item in unknown_result.bindings
    )
    prohibited = _freeze(
        embedded=(
            _draft(
                _git_snapshot(),
                stable_id=EMBEDDED_ID,
                redistribution_allowed=False,
            ),
        )
    )
    prohibited_result = await resolve_embedded_setup(
        _session_with_catalog(),
        definition_bytes=prohibited.payload,
        publisher_id=OWNER,
        public=True,
    )
    assert prohibited_result is not None
    assert any(
        item["check_id"] == "embedded_redistribution"
        and item["reason"] == PROHIBITED_REDISTRIBUTION
        for item in prohibited_result.bindings
    )


@pytest.mark.asyncio
async def test_public_foreign_local_bytes_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai_stp_platform.embedded_validation.run_safety_suite",
        _passed_scan,
    )
    frozen = _freeze(embedded=(_draft(_path_snapshot(), stable_id=PATH_ID, name="local-demo"),))
    resolution = await resolve_embedded_setup(
        _session_with_catalog(),
        definition_bytes=frozen.payload,
        publisher_id=OTHER,
        public=True,
    )
    assert resolution is not None
    assert any(
        item["check_id"] == "embedded_redistribution"
        and item["reason"] == PROHIBITED_REDISTRIBUTION
        for item in resolution.bindings
    )


@pytest.mark.asyncio
async def test_missing_collision_and_mismatch_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_stp_platform.embedded_validation.run_safety_suite",
        _passed_scan,
    )
    mixed = _freeze(
        catalog=(_catalog_ref(),),
        embedded=(_draft(_git_snapshot(), stable_id=EMBEDDED_ID),),
    )
    missing = await resolve_embedded_setup(
        _session_with_catalog(),
        definition_bytes=mixed.payload,
        publisher_id=OWNER,
        public=False,
    )
    assert missing is not None
    assert any(item["reason"] == MISSING_EMBEDDED_REF for item in missing.bindings)

    collision_row = SimpleNamespace(
        stable_id=EMBEDDED_ID,
        version="9.0",
        passport_digest=DIGEST,
        passport_document={},
        checks_summary={"status": "available", "checks": []},
    )
    collision = await resolve_embedded_setup(
        _session_with_catalog(collision_row),
        definition_bytes=_freeze(
            embedded=(_draft(_git_snapshot(), stable_id=EMBEDDED_ID),)
        ).payload,
        publisher_id=OWNER,
        public=False,
    )
    assert collision is not None
    assert any(item["reason"] == CATALOG_COLLISION for item in collision.bindings)

    mismatch_row = SimpleNamespace(
        stable_id=CATALOG_ID,
        version="1.0",
        passport_digest="sha256:" + "c" * 64,
        passport_document={},
        checks_summary={
            "status": "available",
            "checks": [{"check_id": "path_denylist", "result": "passed", "mandatory": True}],
        },
    )
    mismatch = await resolve_embedded_setup(
        _session_with_catalog(mismatch_row),
        definition_bytes=_freeze(catalog=(_catalog_ref(),)).payload,
        publisher_id=OWNER,
        public=True,
    )
    assert mismatch is not None
    assert mismatch.pins[0]["digest_matches"] is False
    assert mismatch.pins[0]["checks_summary"] is None


def test_embedded_member_caps_setup_at_experimental() -> None:
    assert (
        setup_trust_lane(has_embedded=True, author_verified=True, component_verified=True)
        == "experimental"
    )
    assert (
        setup_trust_lane(has_embedded=False, author_verified=True, component_verified=True)
        == "authoritative"
    )
    assert (
        setup_trust_lane(has_embedded=False, author_verified=True, component_verified=False)
        == "experimental"
    )


@pytest.mark.asyncio
async def test_execute_validate_scans_actual_embedded_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned: list[bytes] = []

    async def _scan(**kwargs: Any) -> SafetyScanResult:
        payload = kwargs.get("artifact_bytes")
        if isinstance(payload, bytes):
            scanned.append(payload)
        return await _passed_scan(**kwargs)

    monkeypatch.setattr("ai_stp_platform.embedded_validation.run_safety_suite", _scan)
    frozen = _freeze(embedded=(_draft(_git_snapshot(), stable_id=EMBEDDED_ID),))
    document = from_json_bytes(frozen.payload)
    assert isinstance(document, dict)
    embedded = document["embedded"]
    assert isinstance(embedded, list)
    record = cast(dict[str, JsonValue], embedded[0])
    expected = decode_embedded_artifact(str(record["artifact_b64"]))
    digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, frozen.payload)

    plan = SimpleNamespace(
        id="plan_embedded",
        object_kind="setup",
        stable_id=SETUP,
        version="1.0",
        content_digest=digest,
        policy_version=POLICY_VERSION,
        state="validating",
        component_verified=False,
        actor_account_id=OWNER,
        device_id="device_1",
        passport={
            "name": "s",
            "version": "1.0",
            "visibility": "private",
            "tags": ["t"],
            "license": {"spdx_id": "MIT"},
            "source": {
                "repository": "https://github.com/e/r",
                "commit": "a" * 40,
                "path": ".",
            },
            "artifact": {"digest": digest, "size_bytes": len(frozen.payload)},
            "components": [
                {
                    "stable_id": EMBEDDED_ID,
                    "version": "1.0",
                    "passport_digest": str(record["passport_digest"]),
                }
            ],
            "requires_credentials": False,
        },
        attestations=[],
        effects=[],
    )
    added: list[object] = []
    session = AsyncMock()
    session.get = AsyncMock(return_value=plan)
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    session.add = lambda obj: added.append(obj)
    session.flush = AsyncMock()
    monkeypatch.setattr("ai_stp_platform.publication_logic.enqueue", AsyncMock())
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic._persist_safety_run",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("ai_stp_platform.publication_logic.new_id", lambda prefix: f"{prefix}_t5")
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.open_env_object_store",
        AsyncMock(return_value=None),
    )
    await execute_validate(session, plan_id=plan.id, artifact_bytes=frozen.payload)
    assert expected in scanned
    assert plan.state == "publish_planned"
    assert any(getattr(item, "check_id", None) == "setup_pin_aggregate" for item in added)


def _public_setup_passport(
    *,
    components: list[dict[str, object]],
    artifact_digest: str,
    size_bytes: int,
) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": SETUP,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": OWNER,
        "created_at": AT,
        "visibility": "public",
        "facts": {},
        "name": "mixed-setup",
        "description": "Public mixed setup.",
        "version": "1.0",
        "tags": ["test"],
        "source": {
            "repository": "https://github.com/acme/setup",
            "commit": COMMIT,
            "path": ".",
        },
        "artifact": {"digest": artifact_digest, "size_bytes": size_bytes},
        "harness_id": "claude-code",
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "compatibility_evidence_refs": [],
        "purpose": "Validate embedded publication.",
        "target_role": None,
        "posture": None,
        "supported_tasks": [],
        "components": components,
        "ported_from": None,
        "related_setup_ids": [],
        "execution_profile": "full-auto",
        "supported_harness_versions": [],
        "supported_os": [],
        "supported_arch": [],
        "composition_report_ref": None,
        "conversion_report_ref": None,
        "install_evidence_ref": None,
        "launch_evidence_ref": None,
    }
    body["revision_id"] = derive_revision_id(cast(dict[str, JsonValue], body))
    dumped = cast(
        dict[str, JsonValue],
        SetupVersionPassport.model_validate(body).model_dump(mode="json"),
    )
    dumped["revision_id"] = derive_revision_id(dumped)
    return cast(
        dict[str, object],
        SetupVersionPassport.model_validate(dumped).model_dump(mode="json"),
    )


@pytest.mark.asyncio
async def test_execute_publish_keeps_axes_and_caps_embedded_at_experimental(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = _freeze(embedded=(_draft(_git_snapshot(), stable_id=EMBEDDED_ID),))
    document = from_json_bytes(frozen.payload)
    assert isinstance(document, dict)
    embedded = document["embedded"]
    assert isinstance(embedded, list)
    record = cast(dict[str, JsonValue], embedded[0])
    digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, frozen.payload)
    components: list[dict[str, object]] = [
        {
            "stable_id": EMBEDDED_ID,
            "version": "1.0",
            "passport_digest": str(record["passport_digest"]),
        }
    ]
    passport = _public_setup_passport(
        components=components,
        artifact_digest=digest,
        size_bytes=len(frozen.payload),
    )
    plan = SimpleNamespace(
        id="plan_pub",
        object_kind="setup",
        stable_id=SETUP,
        version="1.0",
        content_digest=digest,
        actor_account_id=OWNER,
        passport=passport,
        policy_version=POLICY_VERSION,
        component_verified=True,
        state="publish_planned",
    )
    snapshot = SimpleNamespace(id="snap_1", state="passed", component_verified=True)
    binding = SimpleNamespace(
        check_id="setup_pin_aggregate",
        result="passed",
        mandatory=True,
        source="platform_safety_scan",
        family="setup_aggregate",
        tool_name="setup_pin_aggregate",
        reason=None,
        finding_summary=None,
    )
    author = SimpleNamespace(verified=True)
    added: list[object] = []
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[plan, author])
    session.scalar = AsyncMock(side_effect=[None, snapshot])
    session.execute = AsyncMock(
        return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [binding]))
    )
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    session.add = lambda obj: added.append(obj)
    session.flush = AsyncMock()
    monkeypatch.setattr("ai_stp_platform.publication_logic.enqueue", AsyncMock())
    monkeypatch.setattr("ai_stp_platform.seo.enqueue.enqueue_seo_build", AsyncMock())
    store = SimpleNamespace(
        read_by_digest=AsyncMock(return_value=frozen.payload),
        key_for_digest=lambda value: f"objects/{value}",
    )
    published = await execute_publish(
        session, plan_id=plan.id, store=cast(ImmutableObjectStore, store)
    )
    metadata = next(item for item in added if getattr(item, "trust_lane", None) is not None)
    assert metadata.trust_lane == "experimental"
    assert metadata.author_verified is True
    assert metadata.component_verified is True
    assert published is metadata
