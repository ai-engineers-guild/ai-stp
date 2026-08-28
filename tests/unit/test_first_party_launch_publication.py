"""First-party launch publication reuses the ordinary authenticated pipeline."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from ai_stp_cli.cloud import session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.first_party import OWNER_ID
from ai_stp_contracts.first_party import versions as first_party_versions
from ai_stp_foundation.digests import digest_bytes

TOOL_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "cli"
    / "tools"
    / "first_party_launch_publication.py"
)
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
BASE = "https://platform.example"
ACCOUNT_OTHER = "account_01JQZK7B8N4M6P2R9T5V0X3YA0"
ARTIFACT_DOMAIN = "ai-stp:artifact:v1"


def _nop(_seconds: float) -> None:
    return None


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("first_party_launch_publication", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def _session(account_id: str = OWNER_ID) -> session.Session:
    return session.Session(
        account_id=account_id,
        device_id=DEVICE,
        access_token="secret-token",
        refresh_token="refresh-token",
        expires_at="2099-01-01T00:00:00.000Z",
    )


def _error(status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"schema_version": 1, "error": {"code": code, "message": message, "retryable": False}},
    )


class PublicationPipeline:
    """In-process authenticated publication routes used by the operator batch."""

    def __init__(self) -> None:
        self.plans: dict[str, dict[str, Any]] = {}
        self.by_create_key: dict[str, str] = {}
        self.bound: dict[str, bytes] = {}
        self.calls: list[tuple[str, str]] = []
        self.create_bodies: list[dict[str, Any]] = []
        self.confirm_order: list[str] = []
        self.status_ticks: dict[str, int] = {}
        self.fail_confirm_once: str | None = None
        self._failed_once: set[str] = set()

    def endpoint(self) -> Endpoint:
        return Endpoint(BASE, transport=httpx.MockTransport(self.route))

    def route(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        if path.startswith("/v1/catalog/"):
            return _error(404, "AI_STP_NOT_FOUND", "catalog object not found")
        if request.headers.get("Authorization") != "Bearer secret-token":
            return _error(401, "AI_STP_AUTH_REQUIRED", "authentication required")
        if request.method == "POST" and path == "/v1/publications/plans":
            return self._create(json.loads(request.content))
        parts = path.split("/")
        if len(parts) < 5 or parts[1:4] != ["v1", "publications", "plans"]:
            return _error(404, "AI_STP_NOT_FOUND", "unknown route")
        plan_id = parts[4]
        if request.method == "GET" and len(parts) == 5:
            return self._status(plan_id)
        if request.method == "PUT" and parts[-1] == "artifact":
            return self._bind(plan_id, request.content)
        if request.method == "POST" and parts[-1] == "confirm":
            return self._confirm(plan_id, json.loads(request.content))
        return _error(404, "AI_STP_NOT_FOUND", "unknown route")

    def _plan_payload(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "state": plan["state"],
            "object_kind": plan["object_kind"],
            "stable_id": plan["stable_id"],
            "version": plan["version"],
            "content_digest": plan["content_digest"],
            "policy_version": "1",
            "actor_id": OWNER_ID,
            "device_id": DEVICE,
            "expires_at": "2099-01-01T00:00:00.000Z",
            "component_verified": plan["state"] == "published",
            "evidence": [],
            "effects": ["validate", "publish_catalog_version"],
        }

    def _create(self, body: dict[str, Any]) -> httpx.Response:
        self.create_bodies.append(body)
        key = str(body["idempotency_key"])
        if key in self.by_create_key:
            return httpx.Response(201, json=self._plan_payload(self.plans[self.by_create_key[key]]))
        if body.get("device_id") != DEVICE:
            return _error(400, "AI_STP_VALIDATION_ERROR", "device_id must match session device")
        plan_id = f"plan_{len(self.plans) + 1:02d}_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
        digest = str(body["content_digest"])
        plan_hash = "plan_" + hashlib.sha256(f"{body['stable_id']}:{digest}".encode()).hexdigest()
        plan = {
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "state": "ready",
            "object_kind": body["object_kind"],
            "stable_id": body["stable_id"],
            "version": body["version"],
            "content_digest": digest,
            "passport": body["passport"],
            "create_key": key,
            "confirm_key": None,
        }
        self.plans[plan_id] = plan
        self.by_create_key[key] = plan_id
        return httpx.Response(201, json=self._plan_payload(plan))

    def _status(self, plan_id: str) -> httpx.Response:
        plan = self.plans.get(plan_id)
        if plan is None:
            return _error(404, "AI_STP_NOT_FOUND", "plan not found")
        if plan["state"] == "validating":
            self.status_ticks[plan_id] = self.status_ticks.get(plan_id, 0) + 1
            plan["state"] = "publish_planned" if self.status_ticks[plan_id] == 1 else "published"
        elif plan["state"] == "publish_planned":
            plan["state"] = "published"
        return httpx.Response(200, json=self._plan_payload(plan))

    def _bind(self, plan_id: str, payload: bytes) -> httpx.Response:
        plan = self.plans.get(plan_id)
        if plan is None:
            return _error(404, "AI_STP_NOT_FOUND", "plan not found")
        observed = digest_bytes(ARTIFACT_DOMAIN, payload)
        if observed != plan["content_digest"]:
            return _error(
                400,
                "AI_STP_VALIDATION_ERROR",
                "artifact digest or size does not match the plan",
            )
        held = self.bound.get(plan_id)
        if held is not None and held != payload:
            return _error(409, "AI_STP_CONFLICT", "different bytes already occupy this digest")
        self.bound[plan_id] = payload
        return httpx.Response(200, json=self._plan_payload(plan))

    def _has_required_evidence(self, passport: dict[str, Any]) -> bool:
        if passport.get("kind") == "setup":
            return bool(passport.get("install_evidence_ref"))
        refs = passport.get("compatibility_evidence_refs")
        return isinstance(refs, list) and len(cast(list[object], refs)) > 0

    def _confirm(self, plan_id: str, body: dict[str, Any]) -> httpx.Response:
        plan = self.plans.get(plan_id)
        if plan is None:
            return _error(404, "AI_STP_NOT_FOUND", "plan not found")
        if plan["confirm_key"] == body.get("idempotency_key"):
            return httpx.Response(200, json=self._plan_payload(plan))
        if plan["state"] in {"validating", "publish_planned", "published"}:
            if plan["plan_hash"] != body.get("plan_hash"):
                return _error(409, "AI_STP_CONFLICT", "plan already confirmed with different hash")
            plan["confirm_key"] = body.get("idempotency_key")
            return httpx.Response(200, json=self._plan_payload(plan))
        if plan_id not in self.bound:
            return _error(
                400,
                "AI_STP_VALIDATION_ERROR",
                "publication artifact bytes are not bound",
            )
        if body.get("plan_hash") != plan["plan_hash"]:
            return _error(400, "AI_STP_VALIDATION_ERROR", "plan_hash mismatch")
        if not self._has_required_evidence(cast(dict[str, Any], plan["passport"])):
            return _error(
                400,
                "AI_STP_VALIDATION_ERROR",
                "required publication evidence is missing",
            )
        if (
            self.fail_confirm_once == plan["stable_id"]
            and plan["stable_id"] not in self._failed_once
        ):
            self._failed_once.add(plan["stable_id"])
            return _error(409, "AI_STP_CONFLICT", "temporary confirm failure")
        plan["state"] = "validating"
        plan["confirm_key"] = body.get("idempotency_key")
        self.confirm_order.append(plan["object_kind"])
        return httpx.Response(200, json=self._plan_payload(plan))


def _unpublished(*_args: object) -> None:
    return None


def _review_apply(
    pipeline: PublicationPipeline,
    tmp_path: Path,
    objects: tuple[Any, ...] | None = None,
) -> Any:
    state_path = tmp_path / "batch.json"
    held = _session()
    endpoint = pipeline.endpoint()
    reviewed = tool.review(state_path=state_path, endpoint=endpoint, held=held, objects=objects)
    applied = tool.apply(
        state_path=state_path,
        endpoint=endpoint,
        held=held,
        corpus_digest_value=reviewed.corpus_digest,
        confirm=True,
        objects=objects,
        pause=_nop,
        published_digest=_unpublished,
    )
    return applied


def test_process_full_first_party_corpus_plan_bind_confirm_publish_components_before_setups(
    tmp_path: Path,
) -> None:
    pipeline = PublicationPipeline()
    applied = _review_apply(pipeline, tmp_path)
    corpus = first_party_versions()
    components = [item for item in corpus if item.kind == "component"]
    setups = [item for item in corpus if item.kind == "setup"]

    assert len(applied.objects) == len(corpus) == 126
    assert [item.kind for item in applied.objects[: len(components)]] == ["component"] * len(
        components
    )
    assert [item.kind for item in applied.objects[len(components) :]] == ["setup"] * len(setups)
    assert all(item.state == "published" and item.blocker is None for item in applied.objects)
    assert pipeline.confirm_order == ["component"] * len(components) + ["setup"] * len(setups)
    assert {method for method, _path in pipeline.calls} <= {"POST", "GET", "PUT"}
    assert all(path.startswith("/v1/publications/plans") for _method, path in pipeline.calls)
    assert not any("catalog" in path or "seed" in path for _method, path in pipeline.calls)
    source = TOOL_PATH.read_text(encoding="utf-8")
    assert "catalog_seed" not in source
    assert "load_first_party_seed" not in source
    assert "component_verified = True" not in source

    creates = sum(
        1
        for method, path in pipeline.calls
        if method == "POST" and path == "/v1/publications/plans"
    )
    first_ids = [item.plan_id for item in applied.objects]
    repeated = tool.apply(
        state_path=tmp_path / "batch.json",
        endpoint=pipeline.endpoint(),
        held=_session(),
        corpus_digest_value=applied.corpus_digest,
        confirm=True,
        pause=_nop,
        published_digest=_unpublished,
    )
    creates_after = sum(
        1
        for method, path in pipeline.calls
        if method == "POST" and path == "/v1/publications/plans"
    )
    assert creates_after == creates
    assert [item.plan_id for item in repeated.objects] == first_ids
    assert all(item.state == "published" for item in repeated.objects)
    assert pipeline.confirm_order == ["component"] * len(components) + ["setup"] * len(setups)


def test_apply_requires_exact_reviewed_digest_and_explicit_confirm(tmp_path: Path) -> None:
    pipeline = PublicationPipeline()
    state_path = tmp_path / "batch.json"
    reviewed = tool.review(state_path=state_path, endpoint=pipeline.endpoint(), held=_session())
    with pytest.raises(CliFailure) as missing_confirm:
        tool.apply(
            state_path=state_path,
            endpoint=pipeline.endpoint(),
            held=_session(),
            corpus_digest_value=reviewed.corpus_digest,
            confirm=False,
            pause=_nop,
            published_digest=_unpublished,
        )
    assert missing_confirm.value.code == "AI_STP_USER_DECISION_REQUIRED"
    with pytest.raises(CliFailure) as wrong_digest:
        tool.apply(
            state_path=state_path,
            endpoint=pipeline.endpoint(),
            held=_session(),
            corpus_digest_value="sha256:" + "0" * 64,
            confirm=True,
            pause=_nop,
            published_digest=_unpublished,
        )
    assert wrong_digest.value.code == "AI_STP_PRECONDITION_FAILED"


def test_resume_reuses_saved_keys_after_an_interrupted_confirm(tmp_path: Path) -> None:
    objects = tool.launch_objects(
        [item for item in first_party_versions() if item.passport.harness_id == "grok-build"]
    )
    component = next(item for item in objects if item.kind == "component")
    pipeline = PublicationPipeline()
    pipeline.fail_confirm_once = component.stable_id
    state_path = tmp_path / "batch.json"
    reviewed = tool.review(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        objects=objects,
    )
    first = tool.apply(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        corpus_digest_value=reviewed.corpus_digest,
        confirm=True,
        objects=objects,
        pause=_nop,
        published_digest=_unpublished,
    )
    assert first.objects[0].blocker is not None
    assert first.objects[1].state == "blocked"
    create_keys = [item.create_idempotency_key for item in first.objects]
    confirm_keys = [item.confirm_idempotency_key for item in first.objects]
    plan_ids = [item.plan_id for item in first.objects]
    resumed = tool.apply(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        corpus_digest_value=reviewed.corpus_digest,
        confirm=True,
        objects=objects,
        pause=_nop,
        published_digest=_unpublished,
    )
    assert [item.create_idempotency_key for item in resumed.objects] == create_keys
    assert [item.confirm_idempotency_key for item in resumed.objects] == confirm_keys
    assert [item.plan_id for item in resumed.objects] == plan_ids
    assert all(item.state == "published" for item in resumed.objects)
    assert len(pipeline.by_create_key) == 2


def test_missing_required_evidence_blocks_dependent_setup_without_exemption(
    tmp_path: Path,
) -> None:
    objects = tool.launch_objects(
        [item for item in first_party_versions() if item.passport.harness_id == "grok-build"]
    )
    component = next(item for item in objects if item.kind == "component")
    setup = next(item for item in objects if item.kind == "setup")
    passport = dict(component.passport)
    passport["compatibility_evidence_refs"] = []
    stripped = tool.LaunchObject(
        kind=component.kind,
        stable_id=component.stable_id,
        version=component.version,
        content_digest=component.content_digest,
        passport_digest=component.passport_digest,
        passport=passport,
        artifact=component.artifact,
        component_pins=component.component_pins,
    )
    applied = _review_apply(PublicationPipeline(), tmp_path, objects=(stripped, setup))
    assert applied.objects[0].state == "blocked"
    assert applied.objects[0].blocker == "required publication evidence is missing"
    assert applied.objects[1].state == "blocked"
    assert applied.objects[1].blocker == "exact component pins are not published"
    assert applied.objects[1].plan_id is not None


def test_apply_skips_an_already_published_matching_digest(tmp_path: Path) -> None:
    objects = tool.launch_objects(
        [item for item in first_party_versions() if item.passport.harness_id == "grok-build"]
    )
    component = next(item for item in objects if item.kind == "component")
    pipeline = PublicationPipeline()
    state_path = tmp_path / "batch.json"
    reviewed = tool.review(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        objects=objects,
    )

    def live(_kind: str, stable_id: str, _version: str) -> str | None:
        if stable_id == component.stable_id:
            return component.passport_digest
        return None

    applied = tool.apply(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        corpus_digest_value=reviewed.corpus_digest,
        confirm=True,
        objects=objects,
        pause=_nop,
        published_digest=live,
    )
    published_component = next(
        item for item in applied.objects if item.stable_id == component.stable_id
    )
    published_setup = next(item for item in applied.objects if item.kind == "setup")
    assert published_component.state == "published"
    assert published_component.blocker is None
    assert published_setup.state == "published"
    assert pipeline.confirm_order == ["setup"]


def test_published_digest_treats_catalog_not_found_as_unpublished() -> None:
    pipeline = PublicationPipeline()
    assert (
        tool._published_passport_digest(
            pipeline.endpoint(),
            "component",
            "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "1.0",
        )
        is None
    )


def test_apply_blocks_lookup_failures_without_confirming(tmp_path: Path) -> None:
    objects = tool.launch_objects(
        [item for item in first_party_versions() if item.passport.harness_id == "grok-build"]
    )
    pipeline = PublicationPipeline()
    state_path = tmp_path / "batch.json"
    reviewed = tool.review(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        objects=objects,
    )

    def boom(_kind: str, _stable_id: str, _version: str) -> str | None:
        raise CliFailure("AI_STP_DEPENDENCY_UNAVAILABLE", "the catalogue could not be reached")

    applied = tool.apply(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        corpus_digest_value=reviewed.corpus_digest,
        confirm=True,
        objects=objects,
        pause=_nop,
        published_digest=boom,
    )
    assert all(item.state == "blocked" for item in applied.objects)
    assert pipeline.confirm_order == []


def test_apply_blocks_an_already_published_different_digest(tmp_path: Path) -> None:
    objects = tool.launch_objects(
        [item for item in first_party_versions() if item.passport.harness_id == "grok-build"]
    )
    component = next(item for item in objects if item.kind == "component")
    pipeline = PublicationPipeline()
    state_path = tmp_path / "batch.json"
    reviewed = tool.review(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        objects=objects,
    )

    def live(_kind: str, stable_id: str, _version: str) -> str | None:
        if stable_id == component.stable_id:
            return "sha256:" + "0" * 64
        return None

    applied = tool.apply(
        state_path=state_path,
        endpoint=pipeline.endpoint(),
        held=_session(),
        corpus_digest_value=reviewed.corpus_digest,
        confirm=True,
        objects=objects,
        pause=_nop,
        published_digest=live,
    )
    blocked_component = next(
        item for item in applied.objects if item.stable_id == component.stable_id
    )
    blocked_setup = next(item for item in applied.objects if item.kind == "setup")
    assert blocked_component.state == "blocked"
    assert blocked_component.blocker == "version already published with different digest"
    assert blocked_setup.state == "blocked"
    assert blocked_setup.blocker == "exact component pins are not published"
    assert pipeline.confirm_order == []


def test_review_refuses_a_non_owner_account(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        tool.review(
            state_path=tmp_path / "batch.json",
            endpoint=PublicationPipeline().endpoint(),
            held=_session(ACCOUNT_OTHER),
        )
    assert raised.value.code == "AI_STP_PERMISSION_DENIED"


def test_main_requires_an_authenticated_session() -> None:
    assert tool.main(["review", "--state", "batch.json"]) == 3


def _plan_response(evidence: list[dict[str, Any]], state: str = "failed") -> Any:
    from ai_stp_contracts.publication import PublicationPlanResponse

    return PublicationPlanResponse(
        plan_id="plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        plan_hash="plan_" + "0" * 64,
        state=cast(Any, state),
        object_kind="component",
        stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        version="1.0",
        content_digest="sha256:" + "0" * 64,
        policy_version="2026-01-01",
        actor_id=OWNER_ID,
        device_id=DEVICE,
        expires_at="2099-01-01T00:00:00.000Z",
        evidence=cast(Any, evidence),
        effects=[],
    )


def test_a_refusal_names_the_check_and_repeats_what_the_platform_said() -> None:
    # The whole point. `state` says a plan failed; it never says why, and the
    # tool used to record only that. A corpus refusal then read "the platform
    # reported a failure" while the cause sat on the wire, unread.
    plan = _plan_response(
        [
            {"check_id": "gitleaks", "result": "passed", "source": "platform_safety_scan"},
            {
                "check_id": "skill_static_gate",
                "result": "failed",
                "source": "platform_safety_scan",
                "reason": "2 finding(s): reported skill risks",
            },
        ]
    )

    assert tool._refusals(plan) == [
        "skill_static_gate: failed — 2 finding(s): reported skill risks"
    ]


def test_a_check_that_could_not_run_is_kept_apart_from_one_that_passed() -> None:
    # `degraded` is what a scanner returns when it never reached a verdict. It
    # is not a pass, and dropping it would hide exactly the failure mode that
    # `reason` was added for. A `warning` is the opposite case: the policy
    # accepted it, so it refused nothing and does not belong in the list.
    plan = _plan_response(
        [
            {
                "check_id": "opengrep",
                "result": "degraded",
                "source": "platform_safety_scan",
                "reason": "did not finish within 25s: skillspector",
            },
            {"check_id": "licence", "result": "warning", "source": "platform_safety_scan"},
        ]
    )

    assert tool._refusals(plan) == ["opengrep: degraded — did not finish within 25s: skillspector"]


def test_a_plan_that_passed_everything_records_no_refusal() -> None:
    plan = _plan_response(
        [{"check_id": "gitleaks", "result": "passed", "source": "platform_safety_scan"}],
        state="published",
    )

    assert tool._refusals(plan) == []


def test_the_reason_travels_onto_the_record_and_into_the_report() -> None:
    record = tool.ObjectRecord(
        kind="component",
        stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        version="1.0",
        content_digest="sha256:" + "0" * 64,
        passport_digest="sha256:" + "1" * 64,
        component_pins=[],
        create_idempotency_key="a",
        confirm_idempotency_key="b",
    )
    plan = _plan_response(
        [
            {
                "check_id": "skill_static_gate",
                "result": "failed",
                "source": "platform_safety_scan",
                "reason": "ran without producing a report: skill-scanner",
            }
        ]
    )
    tool._apply_plan(record, plan)
    record.blocker = "publication plan is failed"

    state = tool.BatchState(
        corpus_digest="sha256:" + "2" * 64,
        account_id=OWNER_ID,
        device_id=DEVICE,
        objects=[record],
    )
    reported = cast(list[dict[str, Any]], tool.report(state)["blockers"])

    assert reported[0]["refused_by"] == [
        "skill_static_gate: failed — ran without producing a report: skill-scanner"
    ]
