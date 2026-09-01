"""Read-only local selection impact and reverse-reference reports."""

import io
import sqlite3
import zipfile
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    cache,
    component_passports,
    components,
    content,
    passports,
    revisions,
    versions,
)
from ai_stp_contracts.context_estimator import EstimatorInput, estimate_context, estimator_for
from ai_stp_contracts.impact import (
    BlastRadiusReport,
    CapabilityDelta,
    CapabilitySnapshot,
    ContextBudget,
    ContextDelta,
    ExactCoordinate,
    PriceProfile,
    SelectionImpactReport,
    TokenCost,
    TokenEstimator,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport, verify_revision_id

#: Re-exported from the owner rather than restated. It lived here first, back
#: when `impact` was the only reader that had been taught the format.
IMPORTED_COMPONENT_FORMAT = components.IMPORTED_COMPONENT_FORMAT
type ImpactScenario = Literal["update", "deprecation", "blocked", "expired_evidence", "advisory"]


@dataclass(frozen=True)
class _Graph:
    coordinate: ExactCoordinate
    setup: SetupVersionPassport
    components: tuple[tuple[ExactCoordinate, ComponentVersionPassport, bytes, str], ...]


def selection_report(
    connection: sqlite3.Connection,
    *,
    setup_id: str,
    setup_version: str,
    baseline_id: str,
    baseline_version: str,
    project_id: str,
    estimator_profile: str,
    price_profile_path: Path | None,
    at: str,
) -> SelectionImpactReport:
    """Compare two exact local setup graphs without changing eligibility or state."""
    estimator = estimator_for(estimator_profile)
    if estimator is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the token estimator profile is not supported",
            details={"profile": estimator_profile},
        )
    candidate = _graph(connection, setup_id, setup_version)
    baseline = None
    baseline_source: Literal["explicit", "installed", "selected", "none"] = "none"
    if baseline_id or baseline_version:
        if not baseline_id or not baseline_version:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "baseline id and version must be supplied together",
            )
        baseline = _graph(connection, baseline_id, baseline_version)
        baseline_source = "explicit"
    elif project_id:
        current = _current_baseline(connection, project_id, candidate.setup.harness_id)
        if current is not None:
            baseline = _graph(connection, current[0], current[1])
            baseline_source = current[2]
    if baseline is not None and baseline.setup.harness_id != candidate.setup.harness_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "candidate and baseline belong to different harnesses"
        )
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
    return SelectionImpactReport(
        generated_at=at,
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
        token_cost=_cost(candidate_context, estimator, price_profile_path, at),
    )


def _current_baseline(
    connection: sqlite3.Connection, project_id: str, harness_id: str
) -> tuple[str, str, Literal["installed", "selected"]] | None:
    target_id = f"{project_id}:{harness_id}"
    row = connection.execute(
        """
        SELECT p.setup_stable_id, p.setup_version
        FROM operation_plan AS p
        JOIN operation AS o ON o.operation_id = p.operation_id
        JOIN operation_event AS e
          ON e.operation_id = p.operation_id AND e.state_after = 'verified'
        WHERE p.target_id = ? AND o.state = 'verified'
        ORDER BY e.global_sequence DESC LIMIT 1
        """,
        (target_id,),
    ).fetchone()
    if row is not None and row["setup_stable_id"] and row["setup_version"]:
        return str(row["setup_stable_id"]), str(row["setup_version"]), "installed"
    row = connection.execute(
        """
        SELECT stable_id, version FROM selected_version
        WHERE project_id = ? AND harness_id = ?
        """,
        (project_id, harness_id),
    ).fetchone()
    if row is None:
        return None
    return str(row["stable_id"]), str(row["version"]), "selected"


def blast_radius(
    connection: sqlite3.Connection,
    *,
    component_id: str,
    component_version: str,
    scenario: str,
    at: str,
) -> BlastRadiusReport:
    """Find exact local reverse references, bounded to this registry and device."""
    component = _component(connection, component_id, component_version, None)[0]
    if scenario not in {"update", "deprecation", "blocked", "expired_evidence", "advisory"}:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the impact scenario is not supported")
    affected: list[ExactCoordinate] = []
    rows = connection.execute(
        """
        SELECT v.stable_id, v.version, v.passport_digest, v.revision_id
        FROM object_version AS v JOIN entity AS e ON e.stable_id = v.stable_id
        WHERE e.kind = 'setup' ORDER BY v.stable_id, v.major, v.minor
        """
    ).fetchall()
    for row in rows:
        graph = _graph(connection, str(row["stable_id"]), str(row["version"]))
        if any(item[0] == component for item in graph.components):
            affected.append(graph.coordinate)
    pairs = {(item.stable_id, item.version) for item in affected}
    projects = sorted(
        {
            str(row["project_id"])
            for row in connection.execute(
                "SELECT project_id, stable_id, version FROM selected_version"
            ).fetchall()
            if (str(row["stable_id"]), str(row["version"])) in pairs
        }
    )
    installed_targets = sorted(
        {
            str(row["target_id"])
            for row in connection.execute(
                """
                SELECT DISTINCT p.target_id, p.setup_stable_id, p.setup_version
                FROM operation_plan AS p JOIN operation AS o ON o.operation_id = p.operation_id
                WHERE o.state = 'verified'
                """
            ).fetchall()
            if (str(row["setup_stable_id"]), str(row["setup_version"])) in pairs
        }
    )
    device = passports.device_stable_id(connection)
    return BlastRadiusReport(
        generated_at=at,
        scenario=cast(ImpactScenario, scenario),
        component=component,
        setup_versions=affected,
        projects=projects,
        devices=[] if not installed_targets or device is None else [device],
        installed_targets=installed_targets,
    )


def _graph(connection: sqlite3.Connection, stable_id: str, version: str) -> _Graph:
    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the exact setup version is not local")
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure("AI_STP_CONFLICT", "the setup version points to a missing passport")
    try:
        setup = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    except ValueError as error:
        raise CliFailure("AI_STP_CONFLICT", "the recorded setup passport is invalid") from error
    expected = _passport_digest(setup)
    if not verify_revision_id(setup) or expected != recorded.passport_digest:
        raise CliFailure("AI_STP_CONFLICT", "the setup passport no longer matches its digest")
    content.get(connection, setup.artifact.digest)
    loaded = tuple(
        _component(connection, ref.stable_id, str(ref.version), ref.passport_digest)
        for ref in setup.components
    )
    return _Graph(
        ExactCoordinate(stable_id=stable_id, version=version, passport_digest=expected),
        setup,
        loaded,
    )


def _component(
    connection: sqlite3.Connection, stable_id: str, version: str, expected: str | None
) -> tuple[ExactCoordinate, ComponentVersionPassport, bytes, str]:
    recorded = versions.held(connection, stable_id, version)
    if recorded is None or (expected is not None and recorded.passport_digest != expected):
        raise CliFailure("AI_STP_CONFLICT", "an exact setup component is missing or changed")
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure("AI_STP_CONFLICT", "a component points to a missing passport")
    document = stored.envelope.model_dump(mode="json")
    # Compared the way the digest was recorded: `versions.record` hashes the
    # stored envelope, not a model derived from it. Hashing the validated model
    # instead only agreed for components whose stored draft already was a public
    # passport, which is every first-party corpus object and no adopted one.
    digest = cache.digest_of(cast(JsonValue, document))
    if digest != recorded.passport_digest:
        raise CliFailure("AI_STP_CONFLICT", "a component passport no longer matches its digest")
    # Two stored shapes, and this used to handle one. A first-party corpus
    # component is stored as a complete public passport and validates directly.
    # An adopted component is stored as the draft it was adopted into: narrower
    # than `ComponentVersionPassport`, with its digest, length and source in
    # `facts` rather than in an `artifact` block. Validating that draft raised
    # `a recorded component passport is invalid` with empty `details`, so
    # `select impact`, `select blast-radius` and `eval` all died on a setup that
    # had passed propose, confirm, bundle, graph and reports (`#385`).
    #
    # The draft is not repaired here. `component_passports.version_passport` is
    # the one owner of "the public passport of this local version" and already
    # synthesises it from those facts; a second synthesis in this module would
    # be a second answer to the same question.
    try:
        passport = ComponentVersionPassport.model_validate(document)
    except ValidationError:
        try:
            passport = component_passports.version_passport(connection, stable_id, version)
        except CliFailure as failure:
            raise CliFailure(
                "AI_STP_CONFLICT",
                "a recorded component passport is invalid",
                # Carried, not swallowed. The previous refusal named no field
                # and offered no next action, so the only way forward was to
                # guess which of forty fields was wrong.
                details={"stable_id": stable_id, "version": version, **failure.details},
                next_actions=failure.next_actions,
            ) from failure
    if not verify_revision_id(passport):
        raise CliFailure("AI_STP_CONFLICT", "a component passport no longer matches its digest")
    facts = cast(dict[str, JsonValue], document.get("facts") or {})
    format_fact = facts.get("content_format")
    content_format = ""
    if isinstance(format_fact, dict):
        format_value = format_fact.get("value")
        if isinstance(format_value, str):
            content_format = format_value
    payload = content.get(connection, passport.artifact.digest)
    if not content_format:
        content_format = (
            components.COMPONENT_TREE_FORMAT
            if zipfile.is_zipfile(io.BytesIO(payload))
            else components.COMPONENT_FILE_FORMAT
        )
    return (
        ExactCoordinate(stable_id=stable_id, version=version, passport_digest=digest),
        passport,
        payload,
        content_format,
    )


def _passport_digest(passport: ComponentVersionPassport | SetupVersionPassport) -> str:
    return digest_bytes(
        "ai-stp:passport:v1", canonize(cast(JsonValue, passport.model_dump(mode="json")))
    )


def _budget(graph: _Graph, estimator: TokenEstimator) -> ContextBudget:
    inputs: list[EstimatorInput] = []
    for coordinate, passport, payload, content_format in graph.components:
        files = tuple(item.content for item in _files(payload, content_format))
        inputs.append(
            EstimatorInput(
                coordinate=coordinate,
                component_type=passport.component_type,
                files=files,
            )
        )
    return estimate_context(inputs, estimator)


def _files(payload: bytes, content_format: str) -> tuple[components.ComponentFile, ...]:
    """One decoder, asked by name.

    This function used to hold its own reader for the imported envelope, and
    `components.expand` — the owner of "what a stored artifact contains" — did
    not know the format at all. So an imported setup could be estimated and
    could not be installed: it composed, confirmed into a real `SetupVersion`,
    and refused at `install plan`. A second copy of a decoding is a second
    answer waiting to differ.
    """
    return components.expand(payload, content_format)


def _capabilities(graph: _Graph) -> CapabilitySnapshot:
    values: dict[str, set[str]] = {name: set() for name in CapabilitySnapshot.model_fields}
    for coordinate, item, _payload, _content_format in graph.components:
        label = f"{coordinate.stable_id}@{coordinate.version}"
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


def _cost(
    budget: ContextBudget,
    estimator: TokenEstimator,
    path: Path | None,
    at: str,
) -> TokenCost:
    if path is None:
        return TokenCost(
            status="unavailable",
            amount=None,
            currency=None,
            profile_id=None,
            source=None,
            fetched_at=None,
            reason="price_profile_not_supplied",
        )
    try:
        profile = PriceProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the price profile is invalid") from error
    if profile.tokenizer_profile != estimator.profile:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the price profile uses another tokenizer")
    if at > profile.expires_at:
        return TokenCost(
            status="stale",
            amount=None,
            currency=profile.currency,
            profile_id=profile.profile_id,
            source=profile.source,
            fetched_at=profile.fetched_at,
            reason="price_profile_expired",
        )
    total = budget.always_tokens + budget.conditional_tokens
    amount = (Decimal(total) * Decimal(profile.input_per_million) / Decimal(1_000_000)).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )
    return TokenCost(
        status="available",
        amount=format(amount, "f"),
        currency=profile.currency,
        profile_id=profile.profile_id,
        source=profile.source,
        fetched_at=profile.fetched_at,
        reason=None,
    )
