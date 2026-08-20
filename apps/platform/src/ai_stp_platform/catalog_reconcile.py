"""Inventory of published versions the public projection cannot read.

`ADR-0079` made a corrupt row answer with its own code instead of a miss, which
tells a caller the truth at the moment they ask. It does not tell an operator
how many such rows exist, and an immutable version cannot be republished under
the same `X.Y`, so the set has to be known before anyone can plan a recovery.

This is deliberately not a migration. A migration runs once, inside a deploy,
and its findings live only in that deploy's log; the same question is asked
again after every publication incident. It is also, in practice, untestable.
A function is both, and the seed and operations entry points can call it.

Nothing here writes. Quarantining a row changes what the catalog discloses about
it, and that is a contract decision with its own ADR — not a side effect of
counting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.catalog_projection import verify_passport_integrity
from ai_stp_platform.catalog_read import (
    PUBLIC_LIFECYCLES,
    CatalogIntegrityError,
    public_version_row,
)
from ai_stp_platform.logging import get_logger
from ai_stp_platform.models import CatalogMetadata

_log = get_logger("catalog")


@dataclass(frozen=True)
class UnreadableVersion:
    """One published version the public projection refuses, and why."""

    object_kind: str
    stable_id: str
    version: str
    reason: str


@dataclass(frozen=True)
class IntegrityReport:
    """What the sweep looked at and what it could not read."""

    checked: int = 0
    unreadable: list[UnreadableVersion] = field(default_factory=list[UnreadableVersion])

    @property
    def healthy(self) -> bool:
        """True when every published version projects."""
        return not self.unreadable


async def reconcile_catalog_integrity(session: AsyncSession) -> IntegrityReport:
    """Verify every publicly reachable version against the projection's own rules.

    The check is the same `verify_passport_integrity` the read path runs, called
    the same way, so the inventory cannot drift from the behaviour it describes.
    A row that fails here is exactly a row that answers `AI_STP_CATALOG_INTEGRITY`.
    """
    rows = list(
        (
            await session.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)),
                    CatalogMetadata.published_at.is_not(None),
                    CatalogMetadata.passport_document.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    unreadable: list[UnreadableVersion] = []
    for meta in rows:
        try:
            # public_version_row rejects a row missing publication fields, and
            # verify_passport_integrity rejects one whose bytes disagree with
            # the passport. Both are reasons the projection refuses the row.
            verify_passport_integrity(public_version_row(meta))
        except CatalogIntegrityError as exc:
            unreadable.append(
                UnreadableVersion(
                    object_kind=meta.object_kind,
                    stable_id=meta.stable_id,
                    version=meta.version or "",
                    reason=str(exc),
                )
            )

    report = IntegrityReport(checked=len(rows), unreadable=unreadable)
    if unreadable:
        # One line per row: an operator planning a recovery needs the identities,
        # not a count. The aggregate is in the same call's return value.
        for item in unreadable:
            _log.error(
                "catalog_version_unreadable",
                reason=item.reason,
                object_kind=item.object_kind,
                stable_id=item.stable_id,
                version=item.version,
            )
    return report
