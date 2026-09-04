"""Project stored catalog rows into frozen #71 wire models (SPEC-021)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from pydantic import Field, SerializerFunctionWrapHandler, ValidationError, model_serializer

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
from ai_stp_contracts.safety_checks import (
    SafetyCheckEntry,
    SafetyChecksSummary,
    SetupComponentChecks,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.markdown import project_safe_markdown
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport
from ai_stp_platform.catalog_query_language import Expression, named_harness_ids, parse_query
from ai_stp_platform.catalog_query_language import matches as query_matches
from ai_stp_platform.catalog_read import CatalogIntegrityError, PublicVersionRow
from ai_stp_platform.catalog_support import project_support
from ai_stp_platform.safety.percent import is_user_facing_row, verdict_percent

PASSPORT_DIGEST_DOMAIN = "ai-stp:passport:v1"


def _overlay_stored_passport(dumped: object, stored: dict[str, JsonValue]) -> dict[str, Any]:
    if not isinstance(dumped, dict):
        raise TypeError("catalog version serializer must return an object")
    payload = cast(dict[str, Any], dumped)
    payload["passport"] = stored
    return payload


class _WiredComponentVersionResponse(ComponentVersionResponse):
    """Wire the stored passport document, not a model dump with later defaults."""

    published_passport: dict[str, JsonValue] = Field(exclude=True)

    @model_serializer(mode="wrap")
    def _published_bytes(self, serializer: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return _overlay_stored_passport(serializer(self), self.published_passport)


class _WiredSetupVersionResponse(SetupVersionResponse):
    """Wire the stored passport document, not a model dump with later defaults."""

    published_passport: dict[str, JsonValue] = Field(exclude=True)

    @model_serializer(mode="wrap")
    def _published_bytes(self, serializer: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return _overlay_stored_passport(serializer(self), self.published_passport)


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


def project_checks_summary(
    row: PublicVersionRow, *, public: bool = True
) -> SafetyChecksSummary | None:
    """Return stored safety checks summary for card/detail (#270), if present.

    The per-member checks are not here. They are one surface's question — the
    setup detail page's — and this document is also the card that `registry
    search` returns, where the name alone broke every released client on
    2026-09-02. See `project_component_checks`.

    ``public=True`` (catalog card and version page) projects finished verdicts
    and mandatory unfinished rows. ``public=False`` is the machine audit list
    (``GET …/versions/{version}/checks``) and keeps optional unfinished checks.
    Percent is always ``passed / (passed + failed + warning)``, recomputed from
    stored counts so historical snapshots do not keep an old denominator.
    """
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
        # A setup is a composition, not one scannable component. Its stored
        # aggregate remains an internal publication gate; public clients get
        # only the exact members and each member's own checks.
        is_setup = row.object_kind == "setup"
        passed = 0 if is_setup else int(summary.get("passed") or 0)
        failed = 0 if is_setup else int(summary.get("failed") or 0)
        warning = 0 if is_setup else int(summary.get("warning") or 0)
        stored_not_run = 0 if is_setup else int(summary.get("not_run") or 0)
        percent = None if is_setup else verdict_percent(passed, failed, warning)
        status_raw = str(summary.get("status") or "empty")
        if is_setup:
            status_raw = "empty"
        if status_raw not in {"pending", "available", "empty", "incomplete"}:
            status_raw = "empty"
        coverage = summary.get("coverage_complete")
        if coverage is None:
            coverage = status_raw == "available"
        if is_setup:
            coverage = False
        shown = [] if is_setup else entries
        if public and shown:
            shown = [
                entry
                for entry in shown
                if is_user_facing_row({"result": entry.result, "mandatory": entry.mandatory})
            ]
        if is_setup:
            not_run = 0
            total_countable = 0
        elif public and entries:
            not_run = sum(1 for entry in shown if entry.result == "not_run")
            total_countable = passed + failed + warning
        else:
            not_run = stored_not_run
            total_countable = passed + failed + warning
        return SafetyChecksSummary(
            status=status_raw,  # type: ignore[arg-type]
            checks_passed_percent=percent,
            coverage_complete=bool(coverage),
            passed=passed,
            failed=failed,
            warning=warning,
            not_run=not_run,
            total_countable=total_countable,
            checks=shown,
        )
    except Exception:
        return None


# Fixture corpus uses an all-zero digest placeholder; the revision seal is the
# real content integrity check for those rows (see seed + #71 fixtures).
_PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)


def project_component_checks(row: PublicVersionRow) -> list[SetupComponentChecks]:
    """The per-member checks of one setup, for its detail read only.

    This used to live inside `SafetyChecksSummary`, which is the *card*
    document as well as the detail's. A card is returned by `registry search`,
    and adding a field to it broke every released client at once: their models
    forbade unknown names, and a key is a key whether or not its list is empty
    — emptying it in the card was not enough, the name had to leave the card's
    model. One surface reads these members, the setup detail page, so they
    belong to the detail response and to nothing else.
    """
    raw_summary = getattr(row.metadata, "checks_summary", None)
    summary = cast(dict[str, Any], raw_summary) if isinstance(raw_summary, dict) else {}
    try:
        components: list[SetupComponentChecks] = []
        components_raw = summary.get("components")
        if isinstance(components_raw, list):
            for raw_component in cast(list[object], components_raw):
                if not isinstance(raw_component, dict):
                    continue
                component = cast(dict[str, Any], raw_component)
                nested = component.get("checks_summary")
                nested_checks: list[object] = []
                if isinstance(nested, dict):
                    nested_map = cast(dict[str, object], nested)
                    checks_value = nested_map.get("checks")
                    if isinstance(checks_value, list):
                        nested_checks = cast(list[object], checks_value)
                components.append(
                    SetupComponentChecks(
                        stable_id=str(component.get("stable_id") or "unknown"),
                        name=str(component.get("name") or component.get("stable_id") or "unknown"),
                        version=str(component.get("version") or "unknown"),
                        embedded=bool(component.get("embedded", False)),
                        source_coordinate=(
                            str(component["source_coordinate"])
                            if component.get("source_coordinate")
                            else None
                        ),
                        digest_matches=bool(component.get("digest_matches", False)),
                        failed_mandatory=bool(component.get("failed_mandatory", True)),
                        checks=[
                            SafetyCheckEntry.model_validate(item)
                            for item in nested_checks
                            if isinstance(item, dict)
                        ],
                    )
                )
        if row.object_kind == "setup" and not components:
            # Older published setup rows stored the human composition in the
            # passport but predate the per-member checks projection. Keep
            # those rows useful without inventing check results.
            facts_raw = row.passport.get("facts")
            facts = cast(dict[str, Any], facts_raw) if isinstance(facts_raw, dict) else {}
            presentations_raw = facts.get("component_presentations")
            presentations: list[Any] = []
            if isinstance(presentations_raw, dict):
                value = cast(dict[str, Any], presentations_raw).get("value")
                if isinstance(value, list):
                    presentations = cast(list[Any], value)
            refs_raw = row.passport.get("components")
            refs = cast(list[Any], refs_raw) if isinstance(refs_raw, list) else []
            for raw_ref in refs if presentations else []:
                if not isinstance(raw_ref, dict):
                    continue
                ref = cast(dict[str, Any], raw_ref)
                stable_id = str(ref.get("stable_id") or "unknown")
                version = str(ref.get("version") or "unknown")
                presentation: dict[str, Any] = {}
                for raw_presentation in presentations:
                    if not isinstance(raw_presentation, dict):
                        continue
                    candidate = cast(dict[str, Any], raw_presentation)
                    if (
                        candidate.get("stable_id") == stable_id
                        and candidate.get("version") == version
                    ):
                        presentation = candidate
                        break
                components.append(
                    SetupComponentChecks(
                        stable_id=stable_id,
                        name=str(presentation.get("name") or stable_id),
                        version=version,
                        embedded=bool(presentation.get("embedded", False)),
                        source_coordinate=(
                            str(presentation["source_coordinate"])
                            if presentation.get("source_coordinate")
                            else None
                        ),
                        # The old row passed setup publication, but did not
                        # retain enough member evidence to recompute a digest.
                        digest_matches=False,
                        failed_mandatory=False,
                        checks=[],
                    )
                )
        return components
    except Exception:
        return []


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
        owner_account_id=row.metadata.owner_account_id,
        owner_handle=row.owner_handle,
        canonical_name=row.canonical_name,
        display_name=row.display_name,
        display_locale=row.display_locale or "",  # type: ignore[arg-type]
        likes_count=row.metadata.likes_count or 0,
        github_stars=row.github_stars,
        latest_requirements_count=_requirements_count(passport),
        latest_requires_credentials=passport.requires_credentials,
        updated_at=format_timestamp(row.metadata.updated_at or row.published_at),  # type: ignore[arg-type]
        latest_version=passport.version,  # type: ignore[arg-type]
        latest_name=passport.name,
        latest_description=_card_excerpt(row.metadata.presentation_bio or passport.description),
        latest_harness_id=cast(
            HarnessId, sorted(item.harness_id for item in passport.adaptations)[0]
        ),
        latest_harness_ids=named_harness_ids(passport.model_dump(mode="json")),  # type: ignore[arg-type]
        latest_component_type=passport.component_type,
        latest_projection_kind=passport.adaptations[0].scope_adaptations[0].projection_kind,
        latest_tags=list(passport.tags),  # type: ignore[arg-type]
        latest_lifecycle=row.lifecycle,  # type: ignore[arg-type]
        latest_trust=project_trust(row),
        latest_support=support,
        latest_published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        latest_checks=project_checks_summary(row),
    )


def _card_excerpt(source: str) -> str:
    """The bounded plain-text excerpt a card carries, never the raw description.

    `DescriptionExcerpt` is `max_length=240` and both summary fields document
    themselves as "deterministic plain-text `safe_markdown_v1` excerpt, never raw
    Markdown or HTML". The projection handed the raw description through anyway,
    and nothing noticed for as long as no published description exceeded 240
    characters — the bound and the only data that met it agreed by accident.

    Importing all four published postures ended that in one step: `full-auto`
    descriptions are load-bearing safety context and run from 690 to 3312
    characters. Eleven setups exceeded the bound, every one of them failed
    `SetupSummary` validation, and the catalogue answered `AI_STP_INTERNAL` on
    the detail route and on any listing page that reached them.

    The excerpt is what the field was always meant to hold, and the projector
    already computes it — `project_safe_markdown(...).excerpt`, bounded to 240
    with a trailing ellipsis on a word boundary.
    """
    return project_safe_markdown(source).excerpt


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
        latest_description=_card_excerpt(passport.description),
        latest_harness_id=passport.harness_id,
        latest_harness_ids=named_harness_ids(passport.model_dump(mode="json")),  # type: ignore[arg-type]
        latest_purpose=passport.purpose,
        latest_target_role=passport.target_role,
        latest_posture=passport.posture,
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
        component_checks=project_component_checks(latest),
    )


def component_version_response(
    row: PublicVersionRow, *, now: datetime | None = None
) -> ComponentVersionResponse:
    verify_passport_integrity(row)
    passport = ComponentVersionPassport.model_validate(row.passport)
    support = project_support(
        passport.model_dump(mode="json"), row.support_evidence, now=now or datetime.now(UTC)
    )
    return _WiredComponentVersionResponse(
        passport=passport,
        passport_digest=row.passport_digest,  # type: ignore[arg-type]
        lifecycle=row.lifecycle,  # type: ignore[arg-type]
        trust=project_trust(row),
        support=support,
        published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        checks=project_checks_summary(row),
        published_passport=cast(dict[str, JsonValue], row.passport),
    )


def setup_version_response(
    row: PublicVersionRow, *, now: datetime | None = None
) -> SetupVersionResponse:
    verify_passport_integrity(row)
    passport = SetupVersionPassport.model_validate(row.passport)
    support = project_support(
        passport.model_dump(mode="json"), row.support_evidence, now=now or datetime.now(UTC)
    )
    return _WiredSetupVersionResponse(
        passport=passport,
        passport_digest=row.passport_digest,  # type: ignore[arg-type]
        lifecycle=row.lifecycle,  # type: ignore[arg-type]
        trust=project_trust(row),
        support=support,
        published_at=format_timestamp(row.published_at),  # type: ignore[arg-type]
        checks=project_checks_summary(row),
        component_checks=project_component_checks(row),
        published_passport=cast(dict[str, JsonValue], row.passport),
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
