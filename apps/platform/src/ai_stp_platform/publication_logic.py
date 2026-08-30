"""Publication plan hashing, validation policy MVP and publish helpers (SPEC-026)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.ids import new_id
from ai_stp_passports.envelope import verify_revision_id
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport
from ai_stp_platform.models import (
    AccountAuthorVerification,
    CatalogMetadata,
    Device,
    EvidenceBinding,
    ObjectLocation,
    PublicationPlan,
    SafetyFinding,
    SafetyScanRun,
    ValidationSnapshot,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.safety.artifact_fetch import (
    ArtifactBytesSource,
    BytesArtifactBytesSource,
    StoreArtifactBytesSource,
    close_env_object_store,
    open_env_object_store,
    passport_artifact_size,
)
from ai_stp_platform.safety.orchestrator import run_safety_suite
from ai_stp_platform.safety.percent import build_checks_summary
from ai_stp_platform.safety.policy import POLICY_VERSION, SafetyProfile
from ai_stp_platform.storage.object_store import ImmutableObjectStore, ObjectIntegrityError

#: Minimal mandatory credential-free checks for the server barrier.
MANDATORY_PLATFORM_CHECKS: tuple[str, ...] = (
    "structure",
    "digest",
    "license",
    "tags",
    "source_repo",
)

#: Optional credential-dependent check accepted only via author attestation.
CREDENTIAL_CHECK = "credentials"

PLAN_TTL = timedelta(hours=24)
EVIDENCE_TTL = timedelta(days=90)
PASSPORT_DIGEST_DOMAIN = "ai-stp:passport:v1"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def compute_plan_hash(
    *,
    actor_account_id: str,
    device_id: str,
    object_kind: str,
    stable_id: str,
    version: str,
    content_digest: str,
    policy_version: str,
    passport: dict[str, object],
    attestations: list[dict[str, object]],
) -> str:
    """Content hash of the immutable plan surface."""
    body = {
        "actor_account_id": actor_account_id,
        "device_id": device_id,
        "object_kind": object_kind,
        "stable_id": stable_id,
        "version": version,
        "content_digest": content_digest,
        "policy_version": policy_version,
        "passport": passport,
        "attestations": attestations,
    }
    digest = hashlib.sha256(_canonical_json(body)).hexdigest()
    return f"plan_{digest}"


def validate_passport_completeness(passport: dict[str, object]) -> list[str]:
    """Return missing field names for SPEC-007 REQ-706 minimums."""
    required = ("name", "version", "license", "tags", "source", "artifact")
    missing = [
        key for key in required if key not in passport or passport[key] in (None, "", [], {})
    ]
    source_raw = passport.get("source")
    if isinstance(source_raw, dict):
        source_map = cast(dict[str, object], source_raw)
        for key in ("repository", "commit", "path"):
            if key not in source_map or not source_map[key]:
                missing.append(f"source.{key}")
    else:
        missing.append("source")
    license_raw = passport.get("license")
    if isinstance(license_raw, dict):
        license_map = cast(dict[str, object], license_raw)
        if "spdx_id" not in license_map or not license_map["spdx_id"]:
            missing.append("license.spdx_id")
    else:
        missing.append("license")
    tags_raw = passport.get("tags")
    if not isinstance(tags_raw, list) or not cast(list[object], tags_raw):
        missing.append("tags")
    return missing


def validate_publication_passport(
    passport: dict[str, object],
    *,
    object_kind: str,
    stable_id: str,
    version: str,
    content_digest: str,
    owner_account_id: str | None = None,
) -> tuple[ComponentVersionPassport | SetupVersionPassport | None, list[str]]:
    """Validate the exact immutable passport accepted by the public catalog."""
    model_type = ComponentVersionPassport if object_kind == "component" else SetupVersionPassport
    try:
        model = model_type.model_validate(passport)
    except ValidationError as exc:
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return None, sorted(set(fields))

    invalid: list[str] = []
    if model.kind != object_kind:
        invalid.append("kind")
    if model.stable_id != stable_id:
        invalid.append("stable_id")
    if model.version != version:
        invalid.append("version")
    if model.visibility != "public":
        invalid.append("visibility")
    if owner_account_id is not None and model.owner_id != owner_account_id:
        invalid.append("owner_id")
    if model.source is None:
        invalid.append("source")
    if model.artifact.digest != content_digest:
        invalid.append("artifact.digest")
    if not verify_revision_id(model):
        invalid.append("revision_id")
    return (model if not invalid else None), sorted(set(invalid))


def passport_digest(passport: ComponentVersionPassport | SetupVersionPassport) -> str:
    """Return the canonical digest used by anonymous catalog reads."""
    payload = cast(JsonValue, passport.model_dump(mode="json"))
    return digest_bytes(PASSPORT_DIGEST_DOMAIN, canonize(payload))


def run_platform_checks(
    *,
    passport: dict[str, object],
    content_digest: str,
) -> list[dict[str, Any]]:
    """Execute credential-free mandatory checks; return binding dicts."""
    bindings: list[dict[str, Any]] = []
    missing = validate_passport_completeness(passport)
    structure_ok = not missing
    bindings.append(
        {
            "check_id": "structure",
            "result": "passed" if structure_ok else "failed",
            "source": "platform_structure_verified",
            "mandatory": True,
        }
    )
    art_digest: object | None = None
    artifact_raw = passport.get("artifact")
    if isinstance(artifact_raw, dict):
        artifact_map = cast(dict[str, object], artifact_raw)
        art_digest = artifact_map.get("digest")
    digest_ok = art_digest == content_digest and bool(content_digest)
    bindings.append(
        {
            "check_id": "digest",
            "result": "passed" if digest_ok else "failed",
            "source": "platform_digest_verified",
            "mandatory": True,
        }
    )
    license_ok = False
    license_raw = passport.get("license")
    if isinstance(license_raw, dict):
        license_map = cast(dict[str, object], license_raw)
        license_ok = bool(license_map.get("spdx_id"))
    bindings.append(
        {
            "check_id": "license",
            "result": "passed" if license_ok else "failed",
            "source": "platform_structure_verified",
            "mandatory": True,
        }
    )
    tags_raw = passport.get("tags")
    tags_ok = isinstance(tags_raw, list) and len(cast(list[object], tags_raw)) > 0
    bindings.append(
        {
            "check_id": "tags",
            "result": "passed" if tags_ok else "failed",
            "source": "platform_structure_verified",
            "mandatory": True,
        }
    )
    source_ok = False
    source_raw = passport.get("source")
    if isinstance(source_raw, dict):
        source_map = cast(dict[str, object], source_raw)
        source_ok = all(bool(source_map.get(key)) for key in ("repository", "commit", "path"))
    bindings.append(
        {
            "check_id": "source_repo",
            "result": "passed" if source_ok else "failed",
            "source": "platform_structure_verified",
            "mandatory": True,
        }
    )
    return bindings


@dataclass(frozen=True)
class AttestationBindingContext:
    """Publication coordinates and the active device key for one bind pass."""

    content_digest: str
    policy_version: str
    account_id: str
    device_id: str
    subject_stable_id: str
    subject_version: str
    passport_digest: str
    public_key: str
    device_revoked: bool


def _decode_key_material(value: str) -> bytes:
    cleaned = value.strip().replace("-", "+").replace("_", "/")
    pad = "=" * (-len(cleaned) % 4)
    return base64.b64decode(cleaned + pad, validate=False)


def verify_author_attestation(*, public_key: str, record: AuthorAttestation) -> bool:
    """Return whether ``record`` is an Ed25519 signature over attestation_digest."""
    try:
        pk_bytes = _decode_key_material(public_key)
        sig_bytes = _decode_key_material(record.signature)
    except (binascii.Error, ValueError):
        return False
    if len(pk_bytes) != 32 or len(sig_bytes) != 64:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(pk_bytes).verify(
            sig_bytes,
            attestation_digest(record).encode("utf-8"),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def bind_author_attestations(
    attestations: list[dict[str, object]],
    *,
    context: AttestationBindingContext,
) -> list[dict[str, Any]]:
    """Accept only device-signed attestations bound to this publication."""
    if context.device_revoked or not context.public_key:
        return []
    bindings: list[dict[str, Any]] = []
    for item in attestations:
        try:
            record = AuthorAttestation.model_validate(item)
        except ValidationError:
            continue
        if record.check_id != CREDENTIAL_CHECK or record.result != "passed":
            continue
        if (
            record.object_digest != context.content_digest
            or record.policy_version != context.policy_version
            or record.account_id != context.account_id
            or record.device_id != context.device_id
            or record.subject.stable_id != context.subject_stable_id
            or record.subject.version != context.subject_version
            or record.subject.passport_digest != context.passport_digest
        ):
            continue
        if any(
            any(word in key.lower() for word in ("secret", "token", "password"))
            for key in record.tool_versions
        ):
            continue
        if not verify_author_attestation(public_key=context.public_key, record=record):
            continue
        bindings.append(
            {
                "check_id": CREDENTIAL_CHECK,
                "result": "passed",
                "source": "author_attested",
                "mandatory": True,
            }
        )
    return bindings


def snapshot_outcome(bindings: list[dict[str, Any]]) -> tuple[str, bool]:
    """Return (snapshot_state, component_verified).

    ``component_verified`` is true only when every mandatory binding is
    ``passed``. A completed ``warning`` allows publish without the badge.
    """
    mandatory = [b for b in bindings if b.get("mandatory")]
    if not mandatory:
        return "failed", False
    results = [str(b.get("result")) for b in mandatory]
    if any(r in {"failed", "degraded", "not_run", "expired"} for r in results):
        return "failed", False
    if any(r == "warning" for r in results):
        return "warning", False
    if all(r == "passed" for r in results):
        return "passed", True
    return "failed", False


async def execute_validate(
    session: AsyncSession,
    *,
    plan_id: str,
    artifact_bytes: bytes | None = None,
    object_store: ImmutableObjectStore | None = None,
    artifact_source: ArtifactBytesSource | None = None,
    safety_profile: str | SafetyProfile = SafetyProfile.STANDARD,
    skip_safety: bool = False,
    release_read_transaction: bool = False,
) -> ValidationSnapshot:
    """Run validation for a plan and write snapshot + bindings (idempotent).

    Safety suite runs after passport checks when ``skip_safety`` is false.

    Artifact resolution order:
    1. ``artifact_bytes`` (tests / pre-fetched)
    2. ``artifact_source`` protocol
    3. ``object_store`` content-addressed fetch + rehash
    4. default ``AI_STP_STORAGE_*`` S3/RustFS store when configured
    """
    plan = await session.get(PublicationPlan, plan_id)
    if plan is None:
        msg = f"unknown plan {plan_id}"
        raise ValueError(msg)
    existing = await session.scalar(
        select(ValidationSnapshot).where(ValidationSnapshot.plan_id == plan_id)
    )
    if existing is not None:
        return existing

    bindings = run_platform_checks(passport=plan.passport, content_digest=plan.content_digest)
    requires_creds = bool(plan.passport.get("requires_credentials"))
    device = await session.get(Device, plan.device_id)
    public_key = getattr(device, "public_key", "") if device is not None else ""
    device_state = getattr(device, "state", "active") if device is not None else "revoked"
    try:
        if plan.object_kind == "setup":
            stored_passport: ComponentVersionPassport | SetupVersionPassport = (
                SetupVersionPassport.model_validate(plan.passport)
            )
        else:
            stored_passport = ComponentVersionPassport.model_validate(plan.passport)
        bound_passport_digest = passport_digest(stored_passport)
    except ValidationError:
        bound_passport_digest = ""
    att_bindings = bind_author_attestations(
        list(plan.attestations or []),
        context=AttestationBindingContext(
            content_digest=plan.content_digest,
            policy_version=plan.policy_version,
            account_id=plan.actor_account_id,
            device_id=plan.device_id,
            subject_stable_id=plan.stable_id,
            subject_version=plan.version,
            passport_digest=bound_passport_digest,
            public_key=public_key if isinstance(public_key, str) else "",
            device_revoked=device is None or device_state != "active",
        ),
    )
    if requires_creds:
        if att_bindings:
            bindings.extend(att_bindings)
        else:
            bindings.append(
                {
                    "check_id": CREDENTIAL_CHECK,
                    "result": "not_run",
                    "source": "author_attested",
                    "mandatory": True,
                }
            )

    # The inputs above are immutable coordinates. Release the read transaction
    # before object-store I/O and external scanners; persistence below starts a
    # fresh short transaction which the worker commits after this function.
    if release_read_transaction:
        await session.commit()

    owned_store: ImmutableObjectStore | None = None
    try:
        if not skip_safety:
            policy_ver = plan.policy_version or POLICY_VERSION
            passport_dict = dict(plan.passport or {})
            size = passport_artifact_size(passport_dict)
            source: ArtifactBytesSource | None = artifact_source
            if artifact_bytes is not None:
                source = BytesArtifactBytesSource(artifact_bytes)
            elif source is None and object_store is not None:
                source = StoreArtifactBytesSource(object_store)
            elif source is None:
                owned_store = await open_env_object_store()
                if owned_store is not None:
                    source = StoreArtifactBytesSource(owned_store)

            resolved_bytes: bytes | None = None
            fetch_failed = False
            if source is not None:
                try:
                    resolved_bytes = await source.fetch_bytes(plan.content_digest, size)
                    if resolved_bytes is None:
                        fetch_failed = True
                except ObjectIntegrityError as exc:
                    fetch_failed = True
                    bindings.append(
                        {
                            "check_id": "artifact_unpack",
                            "family": "unpack",
                            "result": "failed",
                            "source": "platform_safety_scan",
                            "mandatory": True,
                            "tool_name": "artifact_fetch",
                            "detail": {"error": str(exc)},
                        }
                    )

            # Setup first, and deliberately ahead of the bytes case. A setup is
            # judged on what its pins already proved, and the only path that
            # loads those pins is this one — so testing for bytes first made it
            # unreachable for every setup that has an artifact. `setup_pin_
            # aggregate` is mandatory and answers `not_run` without a pin
            # context, so such a setup could never be published at all, however
            # sound its components were.
            if plan.object_kind == "setup":
                from ai_stp_platform.safety.adapters import setup_aggregate as setup_agg

                pin_ctx = await _load_setup_pin_context(session, passport_dict)
                setup_agg.set_pin_context(pin_ctx)
                try:
                    safety = await run_safety_suite(
                        passport=passport_dict,
                        content_digest=plan.content_digest,
                        policy_version=policy_ver,
                        object_kind="setup",
                        profile=safety_profile,
                        # Whatever the setup carries; `None` when nothing
                        # resolved, which is the case this branch used to serve.
                        artifact_bytes=resolved_bytes,
                        use_cache=False,  # pin context is request-scoped
                    )
                finally:
                    setup_agg.clear_pin_context()
                await _persist_safety_run(session, safety)
                bindings.extend(safety.bindings())
            elif resolved_bytes is not None:
                # Digested bytes path: suite re-hashes again inside orchestrator.
                safety = await run_safety_suite(
                    passport=passport_dict,
                    content_digest=plan.content_digest,
                    policy_version=policy_ver,
                    object_kind=plan.object_kind,
                    profile=safety_profile,
                    artifact_bytes=resolved_bytes,
                    use_cache=True,
                )
                await _persist_safety_run(session, safety)
                bindings.extend(safety.bindings())
            elif not fetch_failed:
                # Component without resolvable artifact: mandatory not_run (never pass).
                safety = await run_safety_suite(
                    passport=passport_dict,
                    content_digest=plan.content_digest,
                    policy_version=policy_ver,
                    object_kind=plan.object_kind,
                    profile=safety_profile,
                    artifact_bytes=None,
                    use_cache=True,
                )
                await _persist_safety_run(session, safety)
                bindings.extend(safety.bindings())
            else:
                # Integrity failed already recorded; still mark remaining always-on
                # gates as not_run so snapshot is complete and never auto-passed.
                safety = await run_safety_suite(
                    passport=passport_dict,
                    content_digest=plan.content_digest,
                    policy_version=policy_ver,
                    object_kind=plan.object_kind,
                    profile=safety_profile,
                    artifact_bytes=None,
                    use_cache=False,
                )
                # Drop duplicate artifact_unpack from empty suite if we already failed it
                extra = [
                    b
                    for b in safety.bindings()
                    if not (
                        b.get("check_id") == "artifact_unpack"
                        and any(x.get("check_id") == "artifact_unpack" for x in bindings)
                    )
                ]
                bindings.extend(extra)
    finally:
        await close_env_object_store(owned_store)

    state, component_verified = snapshot_outcome(bindings)
    summary = build_checks_summary(bindings)

    snapshot = ValidationSnapshot(
        id=new_id("snapshot"),
        plan_id=plan.id,
        content_digest=plan.content_digest,
        policy_version=plan.policy_version,
        state=state,
        component_verified=component_verified,
    )
    session.add(snapshot)
    await session.flush()
    expires = datetime.now(UTC) + EVIDENCE_TTL
    for binding in bindings:
        session.add(
            EvidenceBinding(
                snapshot_id=snapshot.id,
                check_id=str(binding["check_id"]),
                result=str(binding["result"]),
                source=str(binding["source"]),
                mandatory=bool(binding.get("mandatory", True)),
                family=str(binding["family"]) if binding.get("family") else None,
                tool_name=str(binding["tool_name"]) if binding.get("tool_name") else None,
                tool_version=str(binding["tool_version"]) if binding.get("tool_version") else None,
                duration_ms=int(binding["duration_ms"])
                if isinstance(binding.get("duration_ms"), int)
                else None,
                severity_max=str(binding["severity_max"]) if binding.get("severity_max") else None,
                reason=str(binding["reason"])[:200] if binding.get("reason") else None,
                finding_summary=cast(dict[str, object], binding["finding_summary"])
                if isinstance(binding.get("finding_summary"), dict)
                else None,
                expires_at=expires,
            )
        )
    plan.effects = list(plan.effects or [])
    if state in {"passed", "warning"}:
        plan.state = "publish_planned"
        plan.component_verified = component_verified
        # Ephemeral attach for in-process callers/tests (not a mapped column).
        cast(Any, plan).checks_summary_last = summary
        await enqueue(
            session,
            job_type=JobType.PUBLISH,
            payload={"plan_id": plan.id, "checks_summary": summary},
            idempotency_key=f"publish:{plan.id}",
        )
    else:
        plan.state = "failed"
        cast(Any, plan).checks_summary_last = summary
    await session.flush()
    return snapshot


async def _load_setup_pin_context(
    session: AsyncSession, passport: dict[str, object]
) -> list[dict[str, Any]]:
    """Load catalog checks_summary for each pinned component (no tree re-scan)."""
    raw = passport.get("components")
    if not isinstance(raw, list):
        return []
    requested: list[tuple[str, str, str | None]] = []
    for raw_item in cast(list[Any], raw):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        sid = item.get("stable_id")
        ver = item.get("version")
        if not isinstance(sid, str) or not isinstance(ver, str):
            continue
        digest = item.get("passport_digest")
        requested.append((sid, ver, digest if isinstance(digest, str) else None))

    if not requested:
        return []
    result = await session.scalars(
        select(CatalogMetadata).where(
            CatalogMetadata.object_kind == "component",
            or_(
                *(
                    (CatalogMetadata.stable_id == sid) & (CatalogMetadata.version == ver)
                    for sid, ver, _digest in requested
                )
            ),
        )
    )
    rows = {(row.stable_id, row.version): row for row in result.all()}

    pins: list[dict[str, Any]] = []
    for sid, ver, expected_digest in requested:
        row = rows.get((sid, ver))
        summary: dict[str, Any] | None = None
        failed_mandatory = False
        digest_matches = (
            row is not None
            and expected_digest is not None
            and row.passport_digest == expected_digest
        )
        if digest_matches and row is not None and isinstance(row.checks_summary, dict):
            summary = cast(dict[str, Any], dict(row.checks_summary))
            checks_any = summary.get("checks")
            if isinstance(checks_any, list):
                for raw_c in cast(list[Any], checks_any):
                    if not isinstance(raw_c, dict):
                        continue
                    c = cast(dict[str, Any], raw_c)
                    if c.get("mandatory") and c.get("result") in {
                        "failed",
                        "degraded",
                        "not_run",
                    }:
                        failed_mandatory = True
                        break
        pins.append(
            {
                "stable_id": sid,
                "version": ver,
                "digest": expected_digest,
                "digest_matches": digest_matches,
                "checks_summary": summary,
                "failed_mandatory": failed_mandatory,
            }
        )
    return pins


async def _persist_safety_run(session: AsyncSession, safety: Any) -> SafetyScanRun | None:
    """Upsert durable scan run + findings for audit (#268/#270)."""
    existing = await session.scalar(
        select(SafetyScanRun).where(
            SafetyScanRun.content_digest == safety.content_digest,
            SafetyScanRun.policy_version == safety.policy_version,
            SafetyScanRun.profile == safety.profile,
            SafetyScanRun.object_kind == safety.object_kind,
        )
    )
    if existing is not None:
        return existing
    run = SafetyScanRun(
        id=new_id("scan"),
        content_digest=safety.content_digest,
        policy_version=safety.policy_version,
        profile=safety.profile,
        object_kind=safety.object_kind,
        state="complete",
        cache_hit=bool(safety.cache_hit),
        wall_ms=int(safety.wall_ms),
        engine_status={
            "outcomes": [o.check_id for o in safety.outcomes],
            "profile": safety.profile,
        },
    )
    try:
        # Another worker may finish the same immutable identity after our
        # SELECT. The unique constraint is the cross-process lock; isolate its
        # conflict in a savepoint so the validation transaction stays usable.
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
        winner = await session.scalar(
            select(SafetyScanRun).where(
                SafetyScanRun.content_digest == safety.content_digest,
                SafetyScanRun.policy_version == safety.policy_version,
                SafetyScanRun.profile == safety.profile,
                SafetyScanRun.object_kind == safety.object_kind,
            )
        )
        if winner is None:
            raise
        return winner
    for finding in safety.all_findings():
        session.add(
            SafetyFinding(
                scan_run_id=run.id,
                check_id=finding.check_id,
                family=finding.family,
                rule_id=finding.rule_id,
                severity=finding.severity,
                # Persist identifiers, not untrusted scanner output or artifact
                # names. EvidenceBinding carries the client-safe summary.
                title=finding.rule_id[:240],
                path=None,
                message="",
                tool_name=(finding.tool_name or "")[:64],
                fingerprint=(finding.fingerprint or "")[:32],
            )
        )
    await session.flush()
    return run


async def execute_publish(
    session: AsyncSession,
    *,
    plan_id: str,
    store: ImmutableObjectStore | None = None,
) -> CatalogMetadata:
    """Materialize catalog version from a validated plan (idempotent)."""
    plan = await session.get(PublicationPlan, plan_id)
    if plan is None:
        msg = f"unknown plan {plan_id}"
        raise ValueError(msg)
    passport, invalid = validate_publication_passport(
        dict(plan.passport),
        object_kind=plan.object_kind,
        stable_id=plan.stable_id,
        version=plan.version,
        content_digest=plan.content_digest,
        owner_account_id=plan.actor_account_id,
    )
    if passport is None:
        msg = f"publish passport failed integrity validation: {', '.join(invalid)}"
        raise ValueError(msg)
    canonical_passport = passport.model_dump(mode="json")
    canonical_digest = passport_digest(passport)

    if store is None:
        msg = "publish requires an available artifact object store"
        raise ValueError(msg)
    artifact_size = int(passport.artifact.size_bytes)
    artifact_bytes = await store.read_by_digest(
        plan.content_digest,
        expected_size=artifact_size,
    )
    if artifact_bytes is None:
        msg = "publish requires durable verified artifact bytes"
        raise ValueError(msg)

    existing = await session.scalar(
        select(CatalogMetadata).where(
            CatalogMetadata.object_kind == plan.object_kind,
            CatalogMetadata.stable_id == plan.stable_id,
            CatalogMetadata.version == plan.version,
        )
    )
    if existing is not None:
        if existing.passport_digest and existing.passport_digest != canonical_digest:
            msg = "version already published with different digest"
            raise ValueError(msg)
        plan.state = "published"
        from ai_stp_platform.seo.enqueue import enqueue_seo_build

        await enqueue_seo_build(
            session,
            kind=plan.object_kind,  # type: ignore[arg-type]
            subject_id=plan.stable_id,
            source_digest=canonical_digest,
        )
        return existing

    snapshot = await session.scalar(
        select(ValidationSnapshot).where(ValidationSnapshot.plan_id == plan.id)
    )
    if snapshot is None or snapshot.state not in {"passed", "warning"}:
        msg = "publish requires successful validation snapshot"
        raise ValueError(msg)

    bindings = list(
        (
            await session.execute(
                select(EvidenceBinding).where(EvidenceBinding.snapshot_id == snapshot.id)
            )
        )
        .scalars()
        .all()
    )
    summary = build_checks_summary(
        [
            {
                "check_id": b.check_id,
                "result": b.result,
                "mandatory": b.mandatory,
                "source": b.source,
                "family": b.family or "",
                "reason": b.reason,
                "finding_summary": b.finding_summary,
            }
            for b in bindings
        ]
    )

    author_row = await session.get(AccountAuthorVerification, plan.actor_account_id)
    author_verified = bool(author_row and author_row.verified)
    component_verified = bool(snapshot.component_verified)
    trust_lane = "authoritative" if author_verified and component_verified else "experimental"
    name = plan.passport.get("name")
    metadata = CatalogMetadata(
        owner_account_id=plan.actor_account_id,
        object_kind=plan.object_kind,
        stable_id=plan.stable_id,
        version=plan.version,
        current_revision_id=passport.revision_id,
        visibility="public",
        lifecycle_state="active",
        name=str(name) if name is not None else None,
        published_at=datetime.now(UTC),
        trust_lane=trust_lane,
        author_verified=author_verified,
        component_verified=component_verified,
        passport_digest=canonical_digest,
        passport_document=canonical_passport,
        checks_summary=summary,
    )
    session.add(metadata)
    plan.state = "published"
    plan.component_verified = component_verified
    await session.flush()
    session.add(
        ObjectLocation(
            catalog_metadata_id=metadata.id,
            purpose="artifact",
            object_key=store.key_for_digest(plan.content_digest),
            digest=plan.content_digest,
            content_id=plan.content_digest,
            size_bytes=artifact_size,
        )
    )
    await session.flush()
    source = canonical_passport.get("source")
    repository = (
        cast(dict[str, object], source).get("repository") if isinstance(source, dict) else None
    )
    if isinstance(repository, str):
        await enqueue(
            session,
            job_type=JobType.REPOSITORY_METRICS,
            payload={"repository": repository},
            idempotency_key=f"repository-metrics:{repository}",
        )
    from ai_stp_platform.seo.enqueue import enqueue_seo_build

    await enqueue_seo_build(
        session,
        kind=plan.object_kind,  # type: ignore[arg-type]
        subject_id=plan.stable_id,
        source_digest=canonical_digest,
    )
    return metadata


async def execute_reevaluate_eligibility(
    session: AsyncSession,
    *,
    object_kind: str,
    stable_id: str,
    version: str,
) -> CatalogMetadata | None:
    """Drop component_verified when evidence expired (ADR-0032)."""
    row = await session.scalar(
        select(CatalogMetadata).where(
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
        )
    )
    if row is None:
        return None
    plan = await session.scalar(
        select(PublicationPlan).where(
            PublicationPlan.stable_id == stable_id,
            PublicationPlan.version == version,
            PublicationPlan.object_kind == object_kind,
            PublicationPlan.state == "published",
        )
    )
    if plan is None:
        return row
    snapshot = await session.scalar(
        select(ValidationSnapshot).where(ValidationSnapshot.plan_id == plan.id)
    )
    if snapshot is None:
        return row
    now = datetime.now(UTC)
    bindings = list(
        (
            await session.execute(
                select(EvidenceBinding).where(EvidenceBinding.snapshot_id == snapshot.id)
            )
        )
        .scalars()
        .all()
    )
    expired = any(
        b.mandatory and b.expires_at is not None and b.expires_at <= now for b in bindings
    )
    if expired or any(b.mandatory and b.result != "passed" for b in bindings):
        row.component_verified = False
        if row.trust_lane == "authoritative":
            row.trust_lane = "experimental"
        plan.component_verified = False
        await session.flush()
    return row


def plan_to_wire(
    plan: PublicationPlan,
    *,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    """Serialize plan for API JSON."""
    expires = plan.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return {
        "schema_version": 1,
        "plan_id": plan.id,
        "plan_hash": plan.plan_hash,
        "state": plan.state,
        "object_kind": plan.object_kind,
        "stable_id": plan.stable_id,
        "version": plan.version,
        "content_digest": plan.content_digest,
        "policy_version": plan.policy_version,
        "actor_id": plan.actor_account_id,
        "device_id": plan.device_id,
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "component_verified": plan.component_verified,
        "evidence": evidence or [],
        "effects": list(plan.effects or []),
    }
