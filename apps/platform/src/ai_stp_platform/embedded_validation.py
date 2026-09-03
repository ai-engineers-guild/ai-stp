"""Server validation of setup-definition v1/v2 (SPEC-057 REQ-5708-REQ-5710)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.models import CatalogMetadata
from ai_stp_platform.safety.orchestrator import run_safety_suite
from ai_stp_platform.safety.percent import build_checks_summary
from ai_stp_platform.safety.policy import POLICY_VERSION, SafetyProfile
from ai_stp_platform.safety.types import SafetyScanResult
from ai_stp_sources.definition import (
    DEFINITION_V2,
    decode_embedded_artifact,
    try_parse_setup_definition,
    validate_setup_definition,
)
from ai_stp_sources.errors import (
    CATALOG_COLLISION,
    INTEGRITY_MISMATCH,
    INVALID_SOURCE,
    MISSING_EMBEDDED_REF,
    PROHIBITED_REDISTRIBUTION,
    SourceError,
)
from ai_stp_sources.models import SourceSnapshot
from ai_stp_sources.resolve import validate_frozen_snapshot

_UNKNOWN_SPDX = frozenset(
    {
        "",
        "NOASSERTION",
        "NONE",
        "UNKNOWN",
        "UNLICENSED",
        "PROPRIETARY",
        "ALL-RIGHTS-RESERVED",
        "NO-LICENSE",
    }
)


@dataclass
class EmbeddedSetupResolution:
    """Catalog-or-embedded pin context plus extra publication bindings."""

    pins: list[dict[str, Any]]
    bindings: list[dict[str, Any]]
    scans: list[SafetyScanResult] = field(default_factory=list[SafetyScanResult])
    has_embedded: bool = False


def setup_trust_lane(*, has_embedded: bool, author_verified: bool, component_verified: bool) -> str:
    """Any embedded member caps the setup at experimental (REQ-5709)."""
    if has_embedded:
        return "experimental"
    return "authoritative" if author_verified and component_verified else "experimental"


def _binding(check_id: str, result: str, *, reason: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "check_id": check_id,
        "family": "embedded_setup",
        "result": result,
        "source": "platform_structure_verified",
        "mandatory": True,
    }
    if reason is not None:
        row["reason"] = reason[:200]
    return row


def _redistribution_allowed(license_raw: object) -> bool:
    if not isinstance(license_raw, dict):
        return False
    license_map = cast(dict[str, object], license_raw)
    spdx = str(license_map.get("spdx_id") or "").strip()
    if not spdx or spdx.upper() in _UNKNOWN_SPDX:
        return False
    return license_map.get("redistribution_allowed") is True


def _snapshot_publisher(passport: dict[str, object]) -> str:
    facts_raw: object = passport.get("facts")
    if not isinstance(facts_raw, dict):
        return ""
    facts = cast(dict[str, object], facts_raw)
    raw: object = facts.get("snapshot_publisher")
    if not isinstance(raw, dict):
        return ""
    value: object = cast(dict[str, object], raw).get("value")
    return value if isinstance(value, str) else ""


def _foreign_local(
    snapshot: SourceSnapshot, passport: dict[str, object], publisher_id: str
) -> bool:
    if snapshot.kind != "path":
        return False
    owner = str(passport.get("owner_id") or "")
    observed = _snapshot_publisher(passport)
    return owner != publisher_id or (observed != "" and observed != publisher_id)


def _reject_secret_coordinate(snapshot: SourceSnapshot) -> None:
    coordinate = snapshot.canonical_coordinate
    if "://" in coordinate:
        host = coordinate.split("://", 1)[1].split("/", 1)[0]
        if "@" in host:
            raise SourceError(INVALID_SOURCE, "credential-bearing URLs are not accepted")
    if snapshot.kind != "path":
        return
    relative = snapshot.canonical_coordinate.removeprefix("path:")
    drive = len(relative) >= 2 and relative[1] == ":"
    if relative.startswith("/") or relative.startswith("\\") or drive:
        raise SourceError(INVALID_SOURCE, "local absolute paths are not accepted")


def _ref_key(stable_id: str, version: str) -> tuple[str, str]:
    return (stable_id, version)


def _graph_bindings(
    *,
    members: dict[tuple[str, str], dict[str, object]],
) -> list[dict[str, Any]]:
    known = set(members)
    managed: dict[str, str] = {}
    bindings: list[dict[str, Any]] = []
    for (sid, ver), passport in members.items():
        required_raw: object = passport.get("requires_components")
        if isinstance(required_raw, list):
            for item in cast(list[object], required_raw):
                if not isinstance(item, dict):
                    continue
                dep = cast(dict[str, object], item)
                dep_id = dep.get("stable_id")
                dep_ver = dep.get("version")
                if not isinstance(dep_id, str) or not isinstance(dep_ver, str):
                    continue
                if _ref_key(dep_id, dep_ver) not in known:
                    bindings.append(
                        _binding(
                            "embedded_graph",
                            "failed",
                            reason=MISSING_EMBEDDED_REF,
                        )
                    )
                    return bindings
        paths_raw: object = passport.get("managed_paths")
        if isinstance(paths_raw, list):
            for path_item in cast(list[object], paths_raw):
                if isinstance(path_item, str) and path_item:
                    owner = managed.get(path_item)
                    if owner is not None and owner != f"{sid}@{ver}":
                        bindings.append(_binding("embedded_graph", "failed", reason="conflict"))
                        return bindings
                    managed[path_item] = f"{sid}@{ver}"
        conflicts_raw: object = passport.get("conflicts")
        if isinstance(conflicts_raw, dict):
            conflict_paths_raw: object = cast(dict[str, object], conflicts_raw).get("paths")
            if isinstance(conflict_paths_raw, list):
                for path_item in cast(list[object], conflict_paths_raw):
                    if (
                        isinstance(path_item, str)
                        and path_item in managed
                        and managed[path_item] != f"{sid}@{ver}"
                    ):
                        bindings.append(_binding("embedded_graph", "failed", reason="conflict"))
                        return bindings
    bindings.append(_binding("embedded_graph", "passed"))
    return bindings


def _pin_from_catalog(row: CatalogMetadata, *, expected_digest: str | None) -> dict[str, Any]:
    digest_matches = expected_digest is not None and row.passport_digest == expected_digest
    summary: dict[str, Any] | None = None
    failed_mandatory = False
    if digest_matches and isinstance(row.checks_summary, dict):
        summary = dict(row.checks_summary)
        checks_any: object = summary.get("checks")
        if isinstance(checks_any, list):
            for raw_c in cast(list[object], checks_any):
                if not isinstance(raw_c, dict):
                    continue
                check = cast(dict[str, Any], raw_c)
                if check.get("mandatory") and check.get("result") in {
                    "failed",
                    "degraded",
                    "not_run",
                }:
                    failed_mandatory = True
                    break
    return {
        "stable_id": row.stable_id,
        "name": getattr(row, "name", row.stable_id),
        "version": row.version,
        "embedded": False,
        "digest": expected_digest,
        "digest_matches": digest_matches,
        "checks_summary": summary if digest_matches else None,
        "failed_mandatory": failed_mandatory or not digest_matches,
    }


def _pin_from_scan(
    *,
    stable_id: str,
    version: str,
    digest: str,
    safety: SafetyScanResult,
    name: str,
    source_coordinate: str,
) -> dict[str, Any]:
    bindings = safety.bindings()
    summary = build_checks_summary(bindings)
    failed = any(
        bool(item.get("mandatory", True))
        and str(item.get("result")) in {"failed", "degraded", "not_run"}
        for item in bindings
    )
    return {
        "stable_id": stable_id,
        "name": name,
        "version": version,
        "embedded": True,
        "source_coordinate": source_coordinate,
        "digest": digest,
        "digest_matches": True,
        "checks_summary": summary,
        "failed_mandatory": failed,
    }


async def _catalog_rows(
    session: AsyncSession, stable_ids: set[str]
) -> dict[tuple[str, str], CatalogMetadata]:
    if not stable_ids:
        return {}
    result = await session.scalars(
        select(CatalogMetadata).where(
            CatalogMetadata.object_kind == "component",
            CatalogMetadata.stable_id.in_(tuple(stable_ids)),
        )
    )
    rows: dict[tuple[str, str], CatalogMetadata] = {}
    for row in result.all():
        rows[(row.stable_id, str(row.version))] = row
    return rows


async def resolve_embedded_setup(
    session: AsyncSession,
    *,
    definition_bytes: bytes,
    publisher_id: str,
    public: bool,
    skip_safety: bool = False,
    safety_profile: SafetyProfile | str = SafetyProfile.STANDARD,
    policy_version: str = POLICY_VERSION,
) -> EmbeddedSetupResolution | None:
    """Resolve catalog or embedded refs from stored definition bytes.

    Returns None when the artifact is not a setup-definition document so older
    zip fixtures keep the catalog-pin-only path.
    """
    parsed = try_parse_setup_definition(definition_bytes)
    if parsed is None:
        return None

    components_raw = parsed.get("components")
    if not isinstance(components_raw, list):
        return EmbeddedSetupResolution(
            pins=[],
            bindings=[_binding("embedded_lookup", "failed", reason=MISSING_EMBEDDED_REF)],
        )
    requested: list[tuple[str, str, str]] = []
    for raw in components_raw:
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, JsonValue], raw)
        sid = item.get("stable_id")
        ver = item.get("version")
        digest = item.get("passport_digest")
        if isinstance(sid, str) and isinstance(ver, str) and isinstance(digest, str):
            requested.append((sid, ver, digest))

    embedded_raw = parsed.get("embedded") if parsed.get("format") == DEFINITION_V2 else []
    if not isinstance(embedded_raw, list):
        embedded_raw = []
    embedded_by_ref: dict[tuple[str, str], dict[str, JsonValue]] = {}
    for raw in embedded_raw:
        if not isinstance(raw, dict):
            continue
        record = cast(dict[str, JsonValue], raw)
        ref_raw = record.get("ref")
        if not isinstance(ref_raw, dict):
            continue
        ref = cast(dict[str, JsonValue], ref_raw)
        sid = ref.get("stable_id")
        ver = ref.get("version")
        if isinstance(sid, str) and isinstance(ver, str):
            key = _ref_key(sid, ver)
            if key in embedded_by_ref:
                return EmbeddedSetupResolution(
                    pins=[],
                    bindings=[_binding("embedded_lookup", "failed", reason=INTEGRITY_MISMATCH)],
                    has_embedded=True,
                )
            embedded_by_ref[key] = record

    catalog_member_ids = {
        sid for sid, ver, _digest in requested if _ref_key(sid, ver) not in embedded_by_ref
    }
    try:
        validate_setup_definition(definition_bytes, catalog_ids=frozenset(catalog_member_ids))
    except SourceError as exc:
        code = exc.code
        check = "embedded_lookup"
        if code == INTEGRITY_MISMATCH:
            check = "embedded_integrity"
        return EmbeddedSetupResolution(
            pins=[],
            bindings=[_binding(check, "failed", reason=code)],
            has_embedded=bool(embedded_by_ref),
        )

    rows = await _catalog_rows(
        session,
        {sid for sid, _ver, _digest in requested} | {sid for sid, _ver in embedded_by_ref},
    )
    catalog_identities = {sid for sid, _ver in rows}
    pins: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    scans: list[SafetyScanResult] = []
    graph_members: dict[tuple[str, str], dict[str, object]] = {}
    has_embedded = bool(embedded_by_ref)

    for sid, ver, digest in requested:
        key = _ref_key(sid, ver)
        catalog_row = rows.get(key)
        embedded = embedded_by_ref.get(key)
        if embedded is not None and sid in catalog_identities:
            bindings.append(_binding("embedded_lookup", "failed", reason=CATALOG_COLLISION))
            return EmbeddedSetupResolution(
                pins=pins,
                bindings=bindings,
                scans=scans,
                has_embedded=True,
            )
        if embedded is None and catalog_row is None:
            bindings.append(_binding("embedded_lookup", "failed", reason=MISSING_EMBEDDED_REF))
            pins.append(
                {
                    "stable_id": sid,
                    "version": ver,
                    "digest": digest,
                    "digest_matches": False,
                    "checks_summary": None,
                    "failed_mandatory": True,
                }
            )
            continue
        if catalog_row is not None:
            pin = _pin_from_catalog(catalog_row, expected_digest=digest)
            pins.append(pin)
            if not pin["digest_matches"]:
                bindings.append(_binding("embedded_integrity", "failed", reason=INTEGRITY_MISMATCH))
            passport_document = catalog_row.passport_document
            if isinstance(passport_document, dict):
                graph_members[key] = dict(passport_document)
            continue

        assert embedded is not None
        pin, extra, scan, passport_document = await _scan_embedded(
            embedded,
            publisher_id=publisher_id,
            public=public,
            skip_safety=skip_safety,
            safety_profile=safety_profile,
            policy_version=policy_version,
        )
        pins.append(pin)
        bindings.extend(extra)
        if scan is not None:
            scans.append(scan)
        if passport_document is not None:
            graph_members[key] = passport_document

    if any(item["result"] == "failed" for item in bindings):
        return EmbeddedSetupResolution(
            pins=pins, bindings=bindings, scans=scans, has_embedded=has_embedded
        )
    bindings.append(_binding("embedded_lookup", "passed"))
    if has_embedded and not any(item["check_id"] == "embedded_integrity" for item in bindings):
        bindings.append(_binding("embedded_integrity", "passed"))
    if (
        public
        and has_embedded
        and not any(item["check_id"] == "embedded_redistribution" for item in bindings)
    ):
        bindings.append(_binding("embedded_redistribution", "passed"))
    bindings.extend(_graph_bindings(members=graph_members))
    return EmbeddedSetupResolution(
        pins=pins, bindings=bindings, scans=scans, has_embedded=has_embedded
    )


async def _scan_embedded(
    record: dict[str, JsonValue],
    *,
    publisher_id: str,
    public: bool,
    skip_safety: bool,
    safety_profile: SafetyProfile | str,
    policy_version: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], SafetyScanResult | None, dict[str, object] | None]:
    extra: list[dict[str, Any]] = []
    ref_raw = record.get("ref")
    if not isinstance(ref_raw, dict):
        extra.append(_binding("embedded_lookup", "failed", reason=MISSING_EMBEDDED_REF))
        return (
            {
                "stable_id": "?",
                "version": "?",
                "digest": None,
                "digest_matches": False,
                "checks_summary": None,
                "failed_mandatory": True,
            },
            extra,
            None,
            None,
        )
    ref = cast(dict[str, JsonValue], ref_raw)
    sid = str(ref.get("stable_id") or "?")
    ver = str(ref.get("version") or "?")
    digest = str(record.get("passport_digest") or "")
    failed_pin = {
        "stable_id": sid,
        "version": ver,
        "digest": digest,
        "digest_matches": False,
        "checks_summary": None,
        "failed_mandatory": True,
    }
    try:
        artifact = decode_embedded_artifact(str(record.get("artifact_b64") or ""))
        snapshot_document = dict(cast(dict[str, object], record["snapshot"]))
        snapshot_document.pop("file_paths", None)
        snapshot = SourceSnapshot.model_validate({**snapshot_document, "files": {}})
        validate_frozen_snapshot(snapshot)
        _reject_secret_coordinate(snapshot)
        passport = ComponentVersionPassport.model_validate(record["passport"])
    except (SourceError, ValidationError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, SourceError) else INVALID_SOURCE
        extra.append(_binding("embedded_integrity", "failed", reason=code))
        return failed_pin, extra, None, None

    passport_document = cast(dict[str, object], passport.model_dump(mode="json"))
    if public:
        if not _redistribution_allowed(passport_document.get("license")):
            extra.append(
                _binding("embedded_redistribution", "failed", reason=PROHIBITED_REDISTRIBUTION)
            )
            return failed_pin, extra, None, passport_document
        if _foreign_local(snapshot, passport_document, publisher_id):
            extra.append(
                _binding("embedded_redistribution", "failed", reason=PROHIBITED_REDISTRIBUTION)
            )
            return failed_pin, extra, None, passport_document

    if skip_safety:
        pin = {
            "stable_id": sid,
            "version": ver,
            "digest": digest,
            "digest_matches": True,
            "checks_summary": {
                "status": "available",
                "checks": [{"check_id": "embedded_skip", "result": "passed", "mandatory": True}],
            },
            "failed_mandatory": False,
        }
        return pin, extra, None, passport_document

    safety = await run_safety_suite(
        passport=passport_document,
        content_digest=str(record.get("artifact_digest") or ""),
        policy_version=policy_version,
        object_kind="component",
        profile=safety_profile,
        artifact_bytes=artifact,
        use_cache=True,
    )
    pin = _pin_from_scan(
        stable_id=sid,
        version=ver,
        digest=digest,
        safety=safety,
        name=passport.name,
        source_coordinate=snapshot.canonical_coordinate,
    )
    return pin, extra, safety, passport_document
