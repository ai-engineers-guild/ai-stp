# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false
"""Publication scans write one assessment per exact projection (SPEC-064 REQ-6426)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from tests.support.component_passports import adaptation_fields

from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import seal_adaptation
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.catalog_assessments import (
    record_component_scan_assessments,
    stored_state_from_scan,
)
from ai_stp_platform.models import TargetAssessment, TargetAssessmentLatest
from ai_stp_platform.safety.types import CheckOutcome, SafetyScanResult

pytestmark = pytest.mark.platform

COMPONENT_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
ACCOUNT_ID = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _scan(digest: str, *results: str) -> SafetyScanResult:
    outcomes = [
        CheckOutcome(check_id=f"check_{index}", family="path", result=result, mandatory=True)
        for index, result in enumerate(results)
    ]
    return SafetyScanResult(
        content_digest=digest,
        policy_version="safety-3",
        profile="standard",
        outcomes=outcomes,
    )


def test_stored_state_from_scan_maps_suite_results() -> None:
    assert stored_state_from_scan(None) == ("not_verified", "projection_artifact_unavailable")
    assert stored_state_from_scan(_scan(DIGEST_A, "passed", "passed")) == ("verified", None)
    assert stored_state_from_scan(_scan(DIGEST_A, "passed", "failed")) == (
        "failed",
        "safety_failed",
    )
    assert stored_state_from_scan(_scan(DIGEST_A, "passed", "warning")) == (
        "not_verified",
        "safety_incomplete",
    )
    assert stored_state_from_scan(_scan(DIGEST_A, "not_run")) == (
        "not_verified",
        "safety_incomplete",
    )


def _two_adaptation_passport() -> ComponentVersionPassport:
    first = adaptation_fields(digest=DIGEST_A, size=12, harness_id="claude-code")
    second = seal_adaptation(
        cast(
            dict[str, JsonValue],
            {
                "harness_id": "pi",
                "implementation_mode": "native",
                "source_artifact": None,
                "transform": None,
                "logical_component_type": "skill",
                "scope_adaptations": [
                    {
                        "scope": "global",
                        "projection_format": "ai-stp-adaptation-projection/1",
                        "projection_artifact": {"digest": DIGEST_B, "size_bytes": 12},
                        "provider_component_kind": "skill",
                        "projection_kind": "native_files",
                        "required_surface": {
                            "profile_id": "pi/test/1",
                            "profile_digest": DIGEST_B,
                            "bundle_format": "ai-stp-bundle/1",
                        },
                        "members": [
                            {
                                "path": "skills/pi/SKILL.md",
                                "object_type": "file",
                                "mode": 420,
                                "content_artifact": {"digest": DIGEST_B, "size_bytes": 12},
                                "native_ids": ["demo"],
                                "content_format": "application/octet-stream",
                                "ownership": "whole",
                                "write_semantics": "replace",
                                "withdrawal_semantics": "remove_path",
                            }
                        ],
                        "technical_support": "experimental",
                        "technical_support_reason": "test fixture",
                    }
                ],
            },
        )
    )
    document: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": COMPONENT_ID,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": ACCOUNT_ID,
        "created_at": "2026-09-06T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": "two-projections",
        "description": "Two exact harness projections.",
        "version": "1.0",
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "tags": ["test", "safety"],
        "source": {
            "repository": "https://github.com/example/demo",
            "commit": "a" * 40,
            "path": "skills/demo",
        },
        "artifact": {"digest": DIGEST_A, "size_bytes": 12},
        **first,
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "component_type": "skill",
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
    }
    adaptations = list(cast(list[object], first["adaptations"]))
    adaptations.append(second.model_dump(mode="json"))
    document["adaptations"] = adaptations
    document["revision_id"] = derive_revision_id(document)  # type: ignore[arg-type]
    return ComponentVersionPassport.model_validate(document)


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def execute(self, _stmt: object) -> SimpleNamespace:
        return SimpleNamespace(scalar_one_or_none=lambda: None)


@pytest.mark.asyncio
async def test_record_writes_independent_states_per_projection() -> None:
    passport = _two_adaptation_passport()
    session = _RecordingSession()
    await record_component_scan_assessments(
        cast(Any, session),
        plan_id="plan_two_projections_01",
        passport=passport,
        passport_digest="sha256:" + "c" * 64,
        policy_version="safety-3",
        scans_by_digest={
            DIGEST_A: _scan(DIGEST_A, "passed", "passed"),
            DIGEST_B: _scan(DIGEST_B, "failed"),
        },
        expires_at=datetime.now(UTC) + timedelta(days=90),
    )
    assessments = [item for item in session.added if isinstance(item, TargetAssessment)]
    latest = [item for item in session.added if isinstance(item, TargetAssessmentLatest)]
    assert len(assessments) == 2
    assert len(latest) == 2
    by_harness = {row.identity["harness_id"]: row.stored_state for row in assessments}
    assert by_harness == {"claude-code": "verified", "pi": "failed"}
    assert {row.harness_id: row.stored_state for row in latest} == by_harness


@pytest.mark.asyncio
async def test_missing_projection_bytes_stay_not_verified() -> None:
    passport = _two_adaptation_passport()
    session = _RecordingSession()
    await record_component_scan_assessments(
        cast(Any, session),
        plan_id="plan_missing_projection_01",
        passport=passport,
        passport_digest="sha256:" + "c" * 64,
        policy_version="safety-3",
        scans_by_digest={DIGEST_A: _scan(DIGEST_A, "passed")},
        expires_at=datetime.now(UTC) + timedelta(days=90),
    )
    by_harness = {
        row.identity["harness_id"]: (row.stored_state, row.reason_code)
        for row in session.added
        if isinstance(row, TargetAssessment)
    }
    assert by_harness["claude-code"] == ("verified", None)
    assert by_harness["pi"] == ("not_verified", "projection_artifact_unavailable")


@pytest.mark.asyncio
async def test_execute_validate_records_a_row_per_exact_adaptation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_platform.publication_logic import execute_validate
    from ai_stp_platform.safety.orchestrator import clear_safety_cache

    clear_safety_cache()
    passport = _two_adaptation_passport()
    plan = SimpleNamespace(
        id="plan_validate_projections",
        object_kind="component",
        stable_id=COMPONENT_ID,
        version="1.0",
        content_digest=DIGEST_A,
        policy_version="safety-3",
        state="validating",
        component_verified=False,
        actor_account_id=ACCOUNT_ID,
        device_id="device_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        passport=passport.model_dump(mode="json"),
        attestations=[],
        effects=[],
    )
    added: list[object] = []
    session = AsyncMock()
    session.get = AsyncMock(return_value=plan)
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    session.add = added.append
    session.flush = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    session.commit = AsyncMock()

    async def fake_suite(**kwargs: object) -> SafetyScanResult:
        digest = str(kwargs["content_digest"])
        result = "passed" if digest == DIGEST_A else "failed"
        return _scan(digest, result)

    monkeypatch.setattr("ai_stp_platform.publication_logic.run_safety_suite", fake_suite)
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic._persist_safety_run",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("ai_stp_platform.publication_logic.enqueue", AsyncMock())
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.new_id",
        lambda prefix: f"{prefix}_proj",
    )
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.open_env_object_store",
        AsyncMock(return_value=None),
    )

    class _Source:
        async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None:
            del size_bytes
            if content_digest == DIGEST_A:
                return b"clean-source"
            if content_digest == DIGEST_B:
                return b"dirty-projection"
            return None

    await execute_validate(
        session,
        plan_id=plan.id,
        artifact_source=_Source(),
        skip_safety=False,
    )
    assessments = [item for item in added if isinstance(item, TargetAssessment)]
    assert len(assessments) == 2
    by_harness = {row.identity["harness_id"]: row.stored_state for row in assessments}
    assert by_harness["claude-code"] == "verified"
    assert by_harness["pi"] == "failed"
