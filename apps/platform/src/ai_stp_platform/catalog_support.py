"""Public provider-support projection for the catalog (SPEC-033, ADR-0072)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ai_stp_contracts.catalog import (
    CatalogSupport,
    CatalogSupportEvidence,
    SupportState,
    SupportTier,
)
from ai_stp_foundation.harnesses import SUPPORT_TIERS
from ai_stp_foundation.timestamps import TimestampError, parse_timestamp
from ai_stp_platform.catalog_read import CatalogIntegrityError

_NOT_VERIFIED_RESULTS = frozenset({"warning", "failed", "degraded", "not_run"})


def support_tier_for_harness(harness_id: str) -> SupportTier:
    """Read the declared tier from its single owner in `ai_stp_foundation`.

    The table used to live here as well. Two copies of one product decision
    agree until the decision changes, and then exactly one of them is updated.
    """
    try:
        return SUPPORT_TIERS[harness_id]  # type: ignore[index]
    except KeyError as exc:
        raise CatalogIntegrityError("catalog passport names an unsupported harness") from exc


def project_support(
    passport: dict[str, Any],
    evidence: list[dict[str, Any]] | None,
    *,
    now: datetime,
) -> CatalogSupport:
    """Validate safe evidence and compute freshness from server time.

    The stored JSON is treated as untrusted input. Invalid provenance never
    becomes a successful support claim.
    """
    raw_harness = passport.get("harness_id")
    tier = support_tier_for_harness(str(raw_harness))
    rows: list[CatalogSupportEvidence] = []
    invalid_evidence = False
    seen_contexts: dict[tuple[str, ...], CatalogSupportEvidence] = {}
    for item in evidence or []:
        try:
            row = CatalogSupportEvidence.model_validate(item)
            parse_timestamp(row.observed_at)
            if row.expires_at is not None:
                parse_timestamp(row.expires_at)
        except (ValueError, TypeError, TimestampError):
            # Stored evidence is outside the public trust boundary. Do not
            # expose malformed fields or let one corrupt row become a 500;
            # retain only valid summaries and make the aggregate unverified.
            invalid_evidence = True
            continue
        context = (
            row.check_id,
            row.provider_id,
            row.provider_version,
            row.release_reference,
            row.operating_system,
            row.architecture,
        )
        previous = seen_contexts.get(context)
        if previous is not None and (
            previous.result != row.result
            or previous.policy_version != row.policy_version
            or previous.mandatory != row.mandatory
        ):
            invalid_evidence = True
            continue
        seen_contexts[context] = row
        rows.append(row)

    state = "not_verified" if invalid_evidence else _state_for(rows, now=now)
    return CatalogSupport(tier=tier, state=state, evidence=rows)


def support_matches_filters(
    support: CatalogSupport,
    *,
    support_tier: str | None,
    support_state: str | None,
) -> bool:
    """Apply public support filters without changing trust-lane consent."""
    if support_tier is not None and support.tier != support_tier:
        return False
    return support_state is None or support.state == support_state


def _state_for(rows: list[CatalogSupportEvidence], *, now: datetime) -> SupportState:
    mandatory = [row for row in rows if row.mandatory]
    if not mandatory:
        return "missing"
    if any(row.result in _NOT_VERIFIED_RESULTS for row in mandatory):
        return "not_verified"
    if any(row.result == "expired" for row in mandatory):
        return "stale"
    for row in mandatory:
        if row.expires_at is None:
            continue
        try:
            if parse_timestamp(row.expires_at) <= now.astimezone(UTC):
                return "stale"
        except TimestampError as exc:
            raise CatalogIntegrityError("invalid support evidence expiry") from exc
    if all(row.result == "passed" for row in mandatory):
        return "verified"
    return "not_verified"
