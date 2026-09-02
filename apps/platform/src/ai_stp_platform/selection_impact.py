"""Account-scoped selection impact and exact setup context budget (SPEC-047, SPEC-049)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

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
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport
from ai_stp_platform.catalog_read import ObjectKind, get_visible_metadata
from ai_stp_platform.models import CatalogMetadata
from ai_stp_platform.storage.object_store import ImmutableObjectStore
from ai_stp_sources.definition import decode_embedded_artifact, try_parse_setup_definition

PASSPORT_DIGEST_DOMAIN = "ai-stp:passport:v1"


class SelectionNotFound(LookupError):
    """Candidate, baseline or component is not visible in this account."""


class SelectionInvalid(ValueError):
    """The exact graph cannot be projected without inventing completeness."""


@dataclass(frozen=True)
class _ComponentNode:
    coordinate: ExactCoordinate
    passport: ComponentVersionPassport
    payload: bytes | None


@dataclass(frozen=True)
class _SetupGraph:
    coordinate: ExactCoordinate
    setup: SetupVersionPassport
    components: tuple[_ComponentNode, ...]
    incomplete: bool


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
        "unavailable" if budget.unavailable_components else "ready"
    )
    return SetupContextBudget(
        coordinate=graph.coordinate,
        estimator=estimator,
        always_tokens=budget.always_tokens,
        conditional_tokens=budget.conditional_tokens,
        total_tokens=budget.always_tokens + budget.conditional_tokens,
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
    digest = _passport_digest(setup)
    if digest != row.passport_digest:
        raise SelectionInvalid("the setup passport no longer matches its digest")
    setup_payload = await _artifact_payload(setup, store)
    embedded = embedded_component_nodes(setup_payload) if setup_payload is not None else {}
    loaded: list[_ComponentNode] = []
    incomplete = False
    for ref in setup.components:
        node = embedded.get((ref.stable_id, str(ref.version)))
        if node is not None and node.coordinate.passport_digest != ref.passport_digest:
            raise SelectionInvalid("an exact setup component is missing or changed")
        if node is None:
            node = await _component_node(
                session, account_id, ref.stable_id, str(ref.version), ref.passport_digest, store
            )
        if node is None:
            raise SelectionInvalid("an exact setup component is missing or changed")
        if node.payload is None:
            incomplete = True
        loaded.append(node)
    return _SetupGraph(
        ExactCoordinate(stable_id=stable_id, version=version, passport_digest=digest),
        setup,
        tuple(loaded),
        incomplete,
    )


async def _component_node(
    session: AsyncSession,
    account_id: str | None,
    stable_id: str,
    version: str,
    expected_digest: str,
    store: ImmutableObjectStore | None,
) -> _ComponentNode | None:
    row = await _visible_row(session, account_id, "component", stable_id, version)
    if row is None or row.passport_document is None or row.passport_digest is None:
        return None
    if row.passport_digest != expected_digest:
        return None
    try:
        passport = ComponentVersionPassport.model_validate(row.passport_document)
    except ValueError:
        return None
    digest = _passport_digest(passport)
    if digest != row.passport_digest:
        return None
    payload = await _artifact_payload(passport, store)
    return _ComponentNode(
        ExactCoordinate(stable_id=stable_id, version=version, passport_digest=digest),
        passport,
        payload,
    )


async def _artifact_payload(
    passport: ComponentVersionPassport | SetupVersionPassport,
    store: ImmutableObjectStore | None,
) -> bytes | None:
    if store is None:
        return None
    try:
        return await store.read_by_digest(
            passport.artifact.digest, expected_size=passport.artifact.size_bytes
        )
    except Exception:
        return None


def embedded_component_nodes(payload: bytes) -> dict[tuple[str, str], _ComponentNode]:
    document = try_parse_setup_definition(payload)
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


def _passport_digest(passport: ComponentVersionPassport | SetupVersionPassport) -> str:
    return digest_bytes(
        PASSPORT_DIGEST_DOMAIN, canonize(cast(JsonValue, passport.model_dump(mode="json")))
    )


def _budget(graph: _SetupGraph, estimator: TokenEstimator):
    return _budget_nodes(graph.components, estimator)


def _budget_nodes(nodes: tuple[_ComponentNode, ...], estimator: TokenEstimator):
    inputs: list[EstimatorInput] = []
    for node in nodes:
        inputs.append(
            EstimatorInput(
                coordinate=node.coordinate,
                component_type=node.passport.component_type,
                files=() if node.payload is None else extract_file_payloads(node.payload),
                missing=node.payload is None,
            )
        )
    return estimate_context(inputs, estimator)


def _capabilities(graph: _SetupGraph) -> CapabilitySnapshot:
    values: dict[str, set[str]] = {name: set() for name in CapabilitySnapshot.model_fields}
    for node in graph.components:
        label = f"{node.coordinate.stable_id}@{node.coordinate.version}"
        item = node.passport
        if item.component_type == "command":
            values["tools"].update(item.native_ids or [label])
        elif item.component_type == "mcp":
            values["mcp_servers"].update(item.native_ids or [label])
        elif item.component_type == "hook":
            values["hooks"].update(item.native_ids or [label])
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
