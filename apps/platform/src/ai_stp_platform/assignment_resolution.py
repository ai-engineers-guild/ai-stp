"""Shared effective-assignment precedence for operations and reports."""

from collections.abc import Sequence
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.versioning import parse_version
from ai_stp_platform.catalog_read import get_visible_object_versions
from ai_stp_platform.organization_models import CorporateCatalogAssignment

ELIGIBLE_LIFECYCLES = frozenset({"active", "deprecated"})


async def eligible_assignment_versions(
    session: AsyncSession,
    *,
    object_kind: Literal["setup", "component"],
    stable_id: str,
    account_id: str | None,
) -> list[tuple[str, str]]:
    rows = await get_visible_object_versions(
        session,
        object_kind=object_kind,
        stable_id=stable_id,
        account_id=account_id,
    )
    eligible = [
        (row.version, row.passport_digest) for row in rows if row.lifecycle in ELIGIBLE_LIFECYCLES
    ]
    eligible.sort(key=lambda item: parse_version(item[0]))
    return eligible


def assignment_scope(row: CorporateCatalogAssignment) -> tuple[str, str]:
    for kind, identity in (
        ("employee", row.account_id),
        ("team", row.team_id),
        ("project", row.project_id),
        ("technology", row.technology_id),
    ):
        if identity is not None:
            return kind, identity
    return "organization", row.organization_id


def select_assignment_winner(
    rows: Sequence[CorporateCatalogAssignment],
    *,
    account_id: str,
    team_ids: set[str],
    project_id: str | None,
    technology_id: str | None,
    harness: str | None,
) -> tuple[
    CorporateCatalogAssignment | None,
    tuple[str, str] | None,
    list[tuple[CorporateCatalogAssignment, tuple[str, str]]],
    bool,
]:
    """Return the same deterministic winner and candidate order as ADR-0195."""
    rank = {"employee": 0, "project": 1, "technology": 2, "team": 3, "organization": 4}

    def sort_key(
        entry: tuple[CorporateCatalogAssignment, tuple[str, str]],
    ) -> tuple[int, int, int, str]:
        row, (kind, _identity) = entry
        return rank[kind], 0 if row.harness is not None else 1, -row.revision, row.id

    considered: list[tuple[CorporateCatalogAssignment, tuple[str, str]]] = []
    for row in rows:
        scope = assignment_scope(row)
        if (row.harness is None or row.harness == harness) and (
            scope[0] == "organization"
            or (scope[0] == "employee" and scope[1] == account_id)
            or (scope[0] == "team" and scope[1] in team_ids)
            or (scope[0] == "project" and scope[1] == project_id)
            or (scope[0] == "technology" and scope[1] == technology_id)
        ):
            considered.append((row, scope))
    considered.sort(key=sort_key)
    employee_entries = [entry for entry in considered if entry[1][0] == "employee"]
    if employee_entries:
        row, scope = employee_entries[0]
        return (
            (row if row.state == "current" else None),
            (scope if row.state == "current" else None),
            considered,
            row.state == "retired",
        )
    for row, scope in considered:
        if row.state == "current":
            return row, scope, considered, False
    return None, None, considered, False
