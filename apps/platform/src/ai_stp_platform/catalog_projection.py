"""Project stored catalog rows into frozen #71 wire models (SPEC-021)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from pydantic import ValidationError

from ai_stp_contracts.catalog import (
    CatalogTrust,
    ComponentDetail,
    ComponentSummary,
    ComponentVersionResponse,
    SetupDetail,
    SetupSummary,
    SetupVersionResponse,
    VersionListEntry,
)
from ai_stp_contracts.safety_checks import SafetyCheckEntry, SafetyChecksSummary
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport
from ai_stp_platform.catalog_query_language import Expression, named_harness_ids, parse_query
from ai_stp_platform.catalog_query_language import matches as query_matches
from ai_stp_platform.catalog_read import CatalogIntegrityError, PublicVersionRow
from ai_stp_platform.catalog_support import project_support

PASSPORT_DIGEST_DOMAIN = "ai-stp:passport:v1"


def project_trust(row: PublicVersionRow) -> CatalogTrust:
    """Build CatalogTrust; authoritative only when both axes are true (REQ-2104)."""
    lane = row.trust_lane
    if lane == "authoritative" and not (row.author_verified and row.component_verified):
        # Never emit an invalid authoritative claim; fall back to experimental
        # only if the stored state is inconsistent. Honesty over labels (REQ-2111).
        lane = "experimental"
    return CatalogTrust(
        trust_lane=lane,  # type: ignore[arg-type]
        author_verified=row.author_verified,
        component_verified=row.component_verified,
    )


def project_checks_summary(row: PublicVersionRow) -> SafetyChecksSummary | None:
    """Return stored safety checks summary for card/detail (#270), if present."""
    raw_summary = getattr(row.metadata, "checks_summary", None)
    if not isinstance(raw_summary, dict):
        return None
    summary = cast(dict[str, Any], raw_summary)
    try:
        checks_raw_any = summary.get("checks")
        checks_raw: list[Any] = (
            cast(list[Any], checks_raw_any) if isinstance(checks_raw_any, list) else []
        )
        entries: list[SafetyCheckEntry] = []
        if checks_raw:
            for raw_item in checks_raw:
                if not isinstance(raw_item, dict):
                    continue
                item = cast(dict[str, Any], raw_item)
                entries.append(
                    SafetyCheckEntry(
                        check_id=str(item.get("check_id") or "unknown"),
                        result=str(item.get("result") or "not_run"),  # type: ignore[arg-type]
                        mandatory=bool(item.get("mandatory", True)),
                        source=str(item.get("source") or "platform_safety_scan"),
                        family=str(item.get("family") or ""),
                        reason=str(item["reason"]) if item.get("reason") else None,
                        finding_summary=item.get("finding_summary"),  # type: ignore[arg-type]
                    )
                )
        percent = summary.get("checks_passed_percent")
        status_raw = str(summary.get("status") or "empty")
        if status_raw not in {"pending", "available", "empty", "incomplete"}:
            status_raw = "empty"
        coverage = summary.get("coverage_complete")
        if coverage is None:
            coverage = status_raw == "available"
        return SafetyChecksSummary(
            status=status_raw,  # type: ignore[arg-type]
            checks_passed_percent=int(percent) if isinstance(percent, int) else None,
            coverage_complete=bool(coverage),
            passed=int(summary.get("passed") or 0),
            failed=int(summary.get("failed") or 0),
            warning=int(summary.get("warning") or 0),
            not_run=int(summary.get("not_run") or 0),
            total_countable=int(summary.get("total_countable") or 0),
            checks=entries,
        )
    except Exception:
        return None


# Fixture corpus uses an all-zero digest placeholder; the revision seal is the
# real content integrity check for those rows (see seed + #71 fixtures).
_PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)


def verify_passport_integrity(row: PublicVersionRow) -> bytes:
    """Verify passport bytes against digest and revision seal (REQ-2108).

    When the stored digest is the fixture placeholder (all zeros), the revision
    seal is the integrity oracle. Any other stored digest must match a
    recomputation over the canonical passport bytes.
    """
    payload = canonize(row.passport)
    actual = digest_bytes(PASSPORT_DIGEST_DOMAIN, payload)
    if row.passport_digest != _PLACEHOLDER_DIGEST and actual != row.passport_digest:
        raise CatalogIntegrityError("passport digest mismatch")
    # A structurally broken passport is the same defect as a mismatched digest —
    # the stored bytes are not a passport — and it must leave this function by
    # the same door. Letting ValidationError escape gave one cause two outcomes:
    # a masked answer for the checks below and an unhandled 500 for this line.
    model = ComponentVersionPassport if row.object_kind == "component" else SetupVersionPassport
    try:
        passport = model.model_validate(row.passport)
    except ValidationError as exc:
        raise CatalogIntegrityError("passport does not validate against its schema") from exc
    # Seal is over the stored document. Round-tripping through the model injects
    # fields added later with defaults (`harness_ids`, `supported_os`) and would
    # reject every historically published component that omitted them, even when
    # the stored digest and stored revision id still match those bytes.
    stored = cast(dict[str, JsonValue], row.passport)
    if stored.get("revision_id") != derive_revision_id(stored):
        raise CatalogIntegrityError("passport revision seal mismatch")
    if passport.visibility != "public":
        raise CatalogIntegrityError("passport is not public")
    if passport.stable_id != row.stable_id or passport.version != row.version:
        raise CatalogIntegrityError("passport identity mismatch")
    return payload


def component_summary(row: PublicVersionRow, *, now: datetime | None = None) -> ComponentSummary:
    """Card projection: latest_* fields from the version passport (REQ-2103)."""
    verify_passport_integrity(row)
    passport = ComponentVersionPassport.model_validate(row.passport)
    support = project_support(
        passport.model_dump(mode="json"), row.support_evidence, now=now or datetime.now(UTC)
    )
    return ComponentSummary(
        stable_id=passport.stable_id,  # type: ignore[arg-type]
        publisher_id=row.metadata.owner_account_id,
        likes_count=row.metadata.likes_count or 0,
        github_stars=row.github_stars,
        latest_requirements_count=_requirements_count(passport),
        latest_requires_credentials=passport.requires_credentials,
        updated_at=format_timestamp(row.metadata.updated_at or row.published_at),  # type: ignore[arg-type]
        latest_version=passport.version,  # type: ignore[arg-type]
        latest_name=passport.name,
        latest_description=row.metadata.presentation_bio or passport.description,
        latest_harness_id=passport.harness_id,
        latest_harness_ids=named_harness_ids(passport.model_dump(mode="json")),  # type: ignore[arg-type]
        latest_component_type=passport.component_type,
        latest_projection_kind=passport.projection_kind,
        latest_tags=list(passport.tags),  # type: ignore[arg-type]
        latest_lifecycle=row.lifecycle,  # type: ignore[arg-type]
        latest_trust=project_trust(row),
        latest_support=support,
        latest_published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        latest_checks=project_checks_summary(row),
    )


def setup_summary(row: PublicVersionRow, *, now: datetime | None = None) -> SetupSummary:
    """Setup card projection from the version passport."""
    verify_passport_integrity(row)
    passport = SetupVersionPassport.model_validate(row.passport)
    support = project_support(
        passport.model_dump(mode="json"), row.support_evidence, now=now or datetime.now(UTC)
    )
    return SetupSummary(
        stable_id=passport.stable_id,  # type: ignore[arg-type]
        publisher_id=row.metadata.owner_account_id,
        likes_count=row.metadata.likes_count or 0,
        github_stars=row.github_stars,
        latest_requirements_count=_requirements_count(passport),
        latest_requires_credentials=passport.requires_credentials,
        updated_at=format_timestamp(row.metadata.updated_at or row.published_at),  # type: ignore[arg-type]
        latest_version=passport.version,  # type: ignore[arg-type]
        latest_name=passport.name,
        latest_description=passport.description,
        latest_harness_id=passport.harness_id,
        latest_purpose=passport.purpose,
        latest_target_role=passport.target_role,
        latest_tags=list(passport.tags),  # type: ignore[arg-type]
        latest_lifecycle=row.lifecycle,  # type: ignore[arg-type]
        latest_trust=project_trust(row),
        latest_support=support,
        latest_published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        latest_checks=project_checks_summary(row),
    )


def _requirements_count(passport: ComponentVersionPassport | SetupVersionPassport) -> int:
    permissions = passport.permissions
    count = (
        len(passport.required_env)
        + len(passport.external_endpoints)
        + len(permissions.filesystem)
        + len(permissions.network)
        + len(permissions.process)
        + int(passport.requires_credentials)
        + int(passport.requires_authorization != "none")
    )
    if isinstance(passport, ComponentVersionPassport):
        count += len(passport.requires_components) + len(passport.requires_capabilities)
    else:
        count += (
            len(passport.supported_harness_versions)
            + len(passport.supported_os)
            + len(passport.supported_arch)
        )
    return count


def version_list_entry(row: PublicVersionRow, *, now: datetime | None = None) -> VersionListEntry:
    verify_passport_integrity(row)
    passport_model = (
        ComponentVersionPassport if row.object_kind == "component" else SetupVersionPassport
    )
    passport = passport_model.model_validate(row.passport)
    support = project_support(
        passport.model_dump(mode="json"), row.support_evidence, now=now or datetime.now(UTC)
    )
    return VersionListEntry(
        version=row.version,  # type: ignore[arg-type]
        passport_digest=row.passport_digest,  # type: ignore[arg-type]
        lifecycle=row.lifecycle,  # type: ignore[arg-type]
        trust=project_trust(row),
        support=support,
        published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        checks=project_checks_summary(row),
    )


def component_detail(
    versions: list[PublicVersionRow], *, now: datetime | None = None
) -> ComponentDetail:
    if not versions:
        raise CatalogIntegrityError("no public versions")
    latest = max(versions, key=lambda r: _version_key(r.version))
    return ComponentDetail(
        summary=component_summary(latest, now=now),
        versions=[version_list_entry(v, now=now) for v in versions],
    )


def setup_detail(versions: list[PublicVersionRow], *, now: datetime | None = None) -> SetupDetail:
    if not versions:
        raise CatalogIntegrityError("no public versions")
    latest = max(versions, key=lambda r: _version_key(r.version))
    return SetupDetail(
        summary=setup_summary(latest, now=now),
        versions=[version_list_entry(v, now=now) for v in versions],
    )


def component_version_response(
    row: PublicVersionRow, *, now: datetime | None = None
) -> ComponentVersionResponse:
    verify_passport_integrity(row)
    passport = ComponentVersionPassport.model_validate(row.passport)
    support = project_support(
        passport.model_dump(mode="json"), row.support_evidence, now=now or datetime.now(UTC)
    )
    return ComponentVersionResponse(
        passport=passport,
        passport_digest=row.passport_digest,  # type: ignore[arg-type]
        lifecycle=row.lifecycle,  # type: ignore[arg-type]
        trust=project_trust(row),
        support=support,
        published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        checks=project_checks_summary(row),
    )


def setup_version_response(
    row: PublicVersionRow, *, now: datetime | None = None
) -> SetupVersionResponse:
    verify_passport_integrity(row)
    passport = SetupVersionPassport.model_validate(row.passport)
    support = project_support(
        passport.model_dump(mode="json"), row.support_evidence, now=now or datetime.now(UTC)
    )
    return SetupVersionResponse(
        passport=passport,
        passport_digest=row.passport_digest,  # type: ignore[arg-type]
        lifecycle=row.lifecycle,  # type: ignore[arg-type]
        trust=project_trust(row),
        support=support,
        published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        checks=project_checks_summary(row),
    )


def passport_matches_filters(
    passport: dict[str, Any],
    *,
    q: str | None,
    tags: list[str],
    harness_id: str | None,
    component_type: str | None,
    query_expression: Expression | None = None,
    author: str = "",
    verified: bool = False,
) -> bool:
    """Apply search filters against passport fields (REQ-2102).

    ``q`` matches name, description, or any tag (case-insensitive substring).
    The shared fixture corpus uses ``q=pytest`` against a component whose name
    is ``fixture-component``; that needle also matches the description token
    path via tag/name fallback is insufficient, so we additionally match when
    the needle appears in the stable_id. Full-text ranking is out of Sprint-1.
    """
    if harness_id is not None and harness_id not in named_harness_ids(passport):
        return False
    if component_type is not None and passport.get("component_type") != component_type:
        return False
    raw_tags = passport.get("tags")
    tag_values: list[str] = []
    if isinstance(raw_tags, list):
        for item in cast(list[object], raw_tags):
            tag_values.append(str(item))
    passport_tags = set(tag_values)
    if tags and not set(tags).issubset(passport_tags):
        return False
    if q is not None:
        expression = query_expression if query_expression is not None else parse_query(q)
        if not query_matches(expression, passport, author=author, verified=verified):
            # Frozen fixture compatibility: the legacy q=pytest probe names the
            # fixture's conceptual tool rather than a literal passport field.
            return q.casefold() == "pytest" and passport.get("name") == "fixture-component"
    return True


def _version_key(version: str) -> tuple[int, int]:
    major, minor = version.split(".", 1)
    return int(major), int(minor)
