"""Account-scoped selection impact and exact setup context budget (SPEC-047, SPEC-049)."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.catalog import ComponentContextBudget, SetupContextBudget
from ai_stp_contracts.context_estimator import (
    TOKENIZED_TYPES,
    EstimatorInput,
    estimate_context,
    estimator_for,
    extract_file_payloads,
)
from ai_stp_contracts.impact import (
    AccountImpactStatus,
    AccountSelectionImpactQuery,
    AccountSelectionImpactReport,
    CapabilityDelta,
    CapabilitySnapshot,
    ContextDelta,
    ExactCoordinate,
    TokenCost,
    TokenEstimator,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.projections import PROJECTION_FORMAT, verify_projection
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport
from ai_stp_platform.catalog_projection import component_passport
from ai_stp_platform.catalog_read import CatalogIntegrityError, ObjectKind, get_visible_metadata
from ai_stp_platform.models import CatalogMetadata, ObjectLocation
from ai_stp_platform.storage.object_store import ImmutableObjectStore, ObjectIntegrityError
from ai_stp_sources.definition import decode_embedded_artifact, try_parse_setup_definition
from ai_stp_sources.errors import SourceError

PASSPORT_DIGEST_DOMAIN = "ai-stp:passport:v1"


class SelectionNotFound(LookupError):
    """Candidate, baseline or component is not visible in this account."""


class SelectionDependency(RuntimeError):
    """Exact artifact storage is unavailable after authorization."""


class SelectionInvalid(ValueError):
    """The exact graph cannot be projected without inventing completeness."""


@dataclass(frozen=True)
class _ComponentNode:
    coordinate: ExactCoordinate
    passport: ComponentVersionPassport
    payload: bytes | None
    content_format: str | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class _SetupGraph:
    coordinate: ExactCoordinate
    setup: SetupVersionPassport
    components: tuple[_ComponentNode, ...]
    incomplete: bool
    unavailable_reason: str | None = None


async def account_impact(
    session: AsyncSession,
    *,
    account_id: str,
    query: AccountSelectionImpactQuery,
    store: ImmutableObjectStore | None,
    now: datetime | None = None,
) -> AccountSelectionImpactReport:
    """Build one account-scoped impact report from catalog rows the caller may see."""
    moment = now or datetime.now(UTC)
    estimator = estimator_for(query.estimator_profile)
    if estimator is None:
        raise SelectionInvalid("the token estimator profile is not supported")
    candidate = await _setup_graph(
        session,
        account_id,
        query.candidate_id,
        query.candidate_version,
        store,
    )
    baseline: _SetupGraph | None = None
    baseline_source: Literal["explicit", "installed", "selected", "none"] = "none"
    if query.baseline_id and query.baseline_version:
        baseline = await _setup_graph(
            session, account_id, query.baseline_id, query.baseline_version, store
        )
        baseline_source = "explicit"
        if baseline.setup.harness_id != candidate.setup.harness_id:
            raise SelectionInvalid("candidate and baseline belong to different harnesses")
    candidate_context = _budget(candidate, estimator)
    baseline_context = None if baseline is None else _budget(baseline, estimator)
    candidate_capabilities = _capabilities(candidate)
    baseline_capabilities = None if baseline is None else _capabilities(baseline)
    delta = None
    capability_delta = None
    if baseline_context is not None and baseline_capabilities is not None:
        delta = ContextDelta(
            always_tokens=candidate_context.always_tokens - baseline_context.always_tokens,
            conditional_tokens=(
                candidate_context.conditional_tokens - baseline_context.conditional_tokens
            ),
        )
        capability_delta = CapabilityDelta(
            added=_difference(candidate_capabilities, baseline_capabilities),
            removed=_difference(baseline_capabilities, candidate_capabilities),
        )
    status, reason = _status(candidate, baseline)
    return AccountSelectionImpactReport(
        generated_at=format_timestamp(moment),
        freshness="account_snapshot",
        source_revision=format_timestamp(moment),
        status=status,
        unavailable_reason=reason,
        candidate_setup=candidate.coordinate,
        baseline_setup=None if baseline is None else baseline.coordinate,
        baseline_source=baseline_source,
        estimator=estimator,
        candidate_context=candidate_context,
        baseline_context=baseline_context,
        context_delta=delta,
        candidate_capabilities=candidate_capabilities,
        baseline_capabilities=baseline_capabilities,
        capability_delta=capability_delta,
        token_cost=TokenCost(
            status="unavailable",
            amount=None,
            currency=None,
            profile_id=None,
            source=None,
            fetched_at=None,
            reason="price_profile_not_supplied",
        ),
    )


async def setup_context_budget(
    session: AsyncSession,
    *,
    account_id: str | None,
    stable_id: str,
    version: str,
    store: ImmutableObjectStore | None,
    estimator_profile: str = "ai-stp:unicode-chars-div4/1",
) -> SetupContextBudget:
    """Absolute context estimate of one visible exact setup (SPEC-049)."""
    estimator = estimator_for(estimator_profile)
    if estimator is None:
        raise SelectionInvalid("the token estimator profile is not supported")
    graph = await _setup_graph(session, account_id, stable_id, version, store)
    budget = _budget(graph, estimator)
    status: Literal["ready", "unavailable"] = (
        "unavailable" if graph.incomplete or budget.unavailable_components else "ready"
    )
    return SetupContextBudget(
        coordinate=graph.coordinate,
        estimator=estimator,
        always_tokens=budget.always_tokens,
        conditional_tokens=budget.conditional_tokens,
        total_tokens=budget.always_tokens + budget.conditional_tokens,
        reason=graph.unavailable_reason
        or next((item.reason for item in budget.components if item.reason), None),
        unavailable_components=budget.unavailable_components,
        status=status,
        components=budget.components,
    )


async def component_context_budget(
    session: AsyncSession,
    *,
    account_id: str | None,
    stable_id: str,
    version: str,
    store: ImmutableObjectStore | None,
    estimator_profile: str = "ai-stp:unicode-chars-div4/1",
) -> ComponentContextBudget:
    """Context estimate of one visible exact component."""
    estimator = estimator_for(estimator_profile)
    if estimator is None:
        raise SelectionInvalid("the token estimator profile is not supported")
    row = await _visible_row(session, account_id, "component", stable_id, version)
    if row is None or row.passport_digest is None:
        raise SelectionNotFound("the exact component version is not visible")
    node = await _component_node(
        session, account_id, stable_id, version, row.passport_digest, store
    )
    if node is None:
        raise SelectionInvalid("the exact component is missing or changed")
    if node.passport.component_type not in TOKENIZED_TYPES:
        return ComponentContextBudget(
            coordinate=node.coordinate,
            estimator=estimator,
            component_type=node.passport.component_type,
            status="not_applicable",
            reason="runtime_context_not_statically_measurable",
        )
    budget = _budget_nodes((node,), estimator)
    measurement = budget.components[0]
    return ComponentContextBudget(
        coordinate=node.coordinate,
        estimator=estimator,
        component_type=node.passport.component_type,
        loading=measurement.loading,
        tokens=measurement.tokens,
        utf8_bytes=measurement.utf8_bytes,
        status=measurement.status,
        reason=measurement.reason,
    )


async def _setup_graph(
    session: AsyncSession,
    account_id: str | None,
    stable_id: str,
    version: str,
    store: ImmutableObjectStore | None,
) -> _SetupGraph:
    row = await _visible_row(session, account_id, "setup", stable_id, version)
    if row is None or row.passport_document is None or row.passport_digest is None:
        raise SelectionNotFound("the exact setup version is not visible")
    try:
        setup = SetupVersionPassport.model_validate(row.passport_document)
    except ValueError as error:
        raise SelectionInvalid("the recorded setup passport is invalid") from error
    digest = _stored_passport_digest(row, stable_id, version)
    setup_payload, setup_reason = await _artifact_payload(session, row, setup, store)
    embedded = embedded_component_nodes(setup_payload) if setup_payload is not None else {}
    loaded: list[_ComponentNode] = []
    incomplete = setup_payload is None
    for ref in setup.components:
        node = embedded.get((ref.stable_id, str(ref.version)))
        if node is not None and node.coordinate.passport_digest != ref.passport_digest:
            raise SelectionInvalid("an exact setup component is missing or changed")
        if node is None:
            node = await _component_node(
                session,
                account_id,
                ref.stable_id,
                str(ref.version),
                ref.passport_digest,
                store,
                harness_id=setup.harness_id,
            )
        if node is None:
            raise SelectionInvalid("an exact setup component is missing or changed")
        if not any(item.harness_id == setup.harness_id for item in node.passport.adaptations):
            raise SelectionInvalid("a setup component has no matching harness adaptation")
        if node.payload is None and node.passport.component_type in TOKENIZED_TYPES:
            incomplete = True
        loaded.append(node)
    return _SetupGraph(
        ExactCoordinate(stable_id=stable_id, version=version, passport_digest=digest),
        setup,
        tuple(loaded),
        incomplete,
        setup_reason,
    )


async def _component_node(
    session: AsyncSession,
    account_id: str | None,
    stable_id: str,
    version: str,
    expected_digest: str,
    store: ImmutableObjectStore | None,
    *,
    harness_id: str | None = None,
) -> _ComponentNode | None:
    row = await _visible_row(session, account_id, "component", stable_id, version)
    if row is None or row.passport_document is None or row.passport_digest is None:
        return None
    if row.passport_digest != expected_digest:
        return None
    try:
        passport = component_passport(cast(dict[str, JsonValue], row.passport_document))
    except (ValueError, CatalogIntegrityError):
        return None
    digest = _stored_passport_digest(row, stable_id, version)
    payload: bytes | None = None
    reason: str | None = None
    content_format: str | None = None
    if harness_id and not any(item.harness_id == harness_id for item in passport.adaptations):
        raise SelectionInvalid("a setup component has no matching harness adaptation")
    if passport.component_type in TOKENIZED_TYPES:
        payload, reason = await _artifact_payload(session, row, passport, store)
        if "adaptations" in row.passport_document:
            selected = [
                item
                for item in passport.adaptations
                if not harness_id or item.harness_id == harness_id
            ]
            if len(selected) != 1 or len(selected[0].scope_adaptations) != 1:
                payload, reason = None, "adaptation_selection_required"
            elif payload is not None:
                try:
                    verify_projection(selected[0].scope_adaptations[0], payload)
                    content_format = PROJECTION_FORMAT
                except ValueError:
                    payload, reason = None, "artifact_invalid"
    return _ComponentNode(
        ExactCoordinate(stable_id=stable_id, version=version, passport_digest=digest),
        passport,
        payload,
        content_format,
        reason,
    )


async def _artifact_payload(
    session: AsyncSession,
    row: CatalogMetadata,
    passport: ComponentVersionPassport | SetupVersionPassport,
    store: ImmutableObjectStore | None,
) -> tuple[bytes | None, str | None]:
    if store is None:
        raise SelectionDependency("artifact storage is unavailable")
    location = await session.scalar(
        select(ObjectLocation).where(
            ObjectLocation.catalog_metadata_id == row.id,
            ObjectLocation.purpose == "artifact",
        )
    )
    if location is None:
        return None, "artifact_unavailable"
    if (
        location.digest != passport.artifact.digest
        or location.size_bytes != passport.artifact.size_bytes
    ):
        return None, "artifact_corrupt"
    try:
        payload = await store.read_verified(
            object_key=location.object_key,
            expected_digest=location.digest,
            expected_size=location.size_bytes,
        )
    except ObjectIntegrityError:
        return None, "artifact_corrupt"
    except Exception as exc:
        raise SelectionDependency("artifact storage is unavailable") from exc
    return payload, "artifact_unavailable" if payload is None else None


def embedded_component_nodes(payload: bytes) -> dict[tuple[str, str], _ComponentNode]:
    try:
        document = try_parse_setup_definition(payload)
    except SourceError as exc:
        raise SelectionInvalid("the setup definition failed integrity verification") from exc
    if document is None:
        return {}
    records = document.get("embedded")
    if not isinstance(records, list):
        return {}
    nodes: dict[tuple[str, str], _ComponentNode] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        record = cast(dict[str, JsonValue], raw)
        ref = record.get("ref")
        passport_raw = record.get("passport")
        if not isinstance(ref, dict) or not isinstance(passport_raw, dict):
            continue
        passport = ComponentVersionPassport.model_validate(passport_raw)
        stable_id = str(ref.get("stable_id"))
        version = str(ref.get("version"))
        digest = str(ref.get("passport_digest"))
        nodes[(stable_id, version)] = _ComponentNode(
            coordinate=ExactCoordinate(
                stable_id=stable_id, version=version, passport_digest=digest
            ),
            passport=passport,
            payload=decode_embedded_artifact(str(record.get("artifact_b64") or "")),
            content_format=PROJECTION_FORMAT,
        )
    return nodes


async def _visible_row(
    session: AsyncSession,
    account_id: str | None,
    object_kind: ObjectKind,
    stable_id: str,
    version: str,
) -> CatalogMetadata | None:
    return await get_visible_metadata(
        session,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        account_id=account_id,
    )


def _stored_passport_digest(row: CatalogMetadata, stable_id: str, version: str) -> str:
    document = cast(dict[str, JsonValue], row.passport_document)
    digest = digest_bytes(PASSPORT_DIGEST_DOMAIN, canonize(document))
    if (
        digest != row.passport_digest
        or document.get("revision_id") != derive_revision_id(document)
        or document.get("stable_id") != stable_id
        or document.get("version") != version
    ):
        raise SelectionInvalid("the exact passport is missing or changed")
    return digest


def _budget(graph: _SetupGraph, estimator: TokenEstimator):
    return _budget_nodes(graph.components, estimator)


def _budget_nodes(nodes: tuple[_ComponentNode, ...], estimator: TokenEstimator):
    inputs: list[EstimatorInput] = []
    for node in nodes:
        if node.passport.component_type not in TOKENIZED_TYPES:
            continue
        reason = node.unavailable_reason
        try:
            files = (
                ()
                if node.payload is None
                else extract_file_payloads(node.payload, node.content_format)
            )
        except (ValueError, OSError, zipfile.BadZipFile):
            files, reason = (), "artifact_invalid"
        inputs.append(
            EstimatorInput(
                coordinate=node.coordinate,
                component_type=node.passport.component_type,
                files=files,
                missing=node.payload is None or reason is not None,
                missing_reason=reason or "artifact_unavailable",
            )
        )
    return estimate_context(inputs, estimator)


def _capabilities(graph: _SetupGraph) -> CapabilitySnapshot:
    values: dict[str, set[str]] = {name: set() for name in CapabilitySnapshot.model_fields}
    for node in graph.components:
        label = f"{node.coordinate.stable_id}@{node.coordinate.version}"
        item = node.passport
        adaptation = next(
            (held for held in item.adaptations if held.harness_id == graph.setup.harness_id), None
        )
        native_ids = (
            []
            if adaptation is None
            else [
                native_id
                for scope in adaptation.scope_adaptations
                for member in scope.members
                for native_id in member.native_ids
            ]
        )
        if item.component_type == "command":
            values["tools"].update(native_ids or [label])
        elif item.component_type == "mcp":
            values["mcp_servers"].update(native_ids or [label])
        elif item.component_type == "hook":
            values["hooks"].update(native_ids or [label])
        values["network_requirements"].update(item.external_endpoints)
        if item.requires_credentials or item.required_env:
            values["credential_requirements"].add(label)
        values["filesystem_permissions"].update(item.permissions.filesystem)
        values["network_permissions"].update(item.permissions.network)
        values["process_permissions"].update(item.permissions.process)
    return CapabilitySnapshot(**{name: sorted(value) for name, value in values.items()})


def _difference(left: CapabilitySnapshot, right: CapabilitySnapshot) -> CapabilitySnapshot:
    return CapabilitySnapshot(
        **{
            name: sorted(set(getattr(left, name)) - set(getattr(right, name)))
            for name in CapabilitySnapshot.model_fields
        }
    )


def _status(
    candidate: _SetupGraph, baseline: _SetupGraph | None
) -> tuple[AccountImpactStatus, str | None]:
    if candidate.incomplete or (baseline is not None and baseline.incomplete):
        return "partial", "artifact_unavailable"
    return "ready", None
