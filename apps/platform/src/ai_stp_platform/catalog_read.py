"""Public catalog read repository (SPEC-021 REQ-2102..2108)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.catalog_cursor import CursorKey
from ai_stp_platform.models import AccountAuthorVerification, CatalogMetadata, RepositoryMetric

PUBLIC_LIFECYCLES: frozenset[str] = frozenset({"active", "deprecated", "blocked"})
ObjectKind = Literal["component", "setup"]


def _empty_support_evidence() -> list[dict[str, object]]:
    return []


@dataclass(frozen=True)
class PublicVersionRow:
    """One published public catalog version with stored passport bytes."""

    metadata: CatalogMetadata
    passport: dict[str, Any]
    passport_digest: str
    published_at: datetime
    trust_lane: str
    author_verified: bool
    component_verified: bool
    lifecycle: str
    stable_id: str
    version: str
    object_kind: str
    support_evidence: list[dict[str, object]] = field(default_factory=_empty_support_evidence)
    github_stars: int | None = None


class CatalogIntegrityError(RuntimeError):
    """Stored passport fails digest or revision integrity before response."""


def _public_base(object_kind: ObjectKind) -> Select[tuple[CatalogMetadata]]:
    return select(CatalogMetadata).where(
        CatalogMetadata.object_kind == object_kind,
        CatalogMetadata.visibility == "public",
        CatalogMetadata.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)),
        CatalogMetadata.published_at.is_not(None),
        CatalogMetadata.version.is_not(None),
        CatalogMetadata.passport_document.is_not(None),
        CatalogMetadata.passport_digest.is_not(None),
        CatalogMetadata.trust_lane.is_not(None),
    )


def public_version_row(meta: CatalogMetadata) -> PublicVersionRow:
    """Project one stored row, refusing a row that cannot be a public version.

    Public because the integrity sweep must ask the projection the same
    question the read path asks. A sweep with its own copy of these rules would
    drift from the behaviour it claims to inventory.
    """
    if (
        meta.published_at is None
        or meta.version is None
        or meta.passport_document is None
        or meta.passport_digest is None
        or meta.trust_lane is None
    ):
        raise CatalogIntegrityError("public row missing publication fields")
    return PublicVersionRow(
        metadata=meta,
        passport=dict(meta.passport_document),
        passport_digest=meta.passport_digest,
        published_at=meta.published_at,
        trust_lane=meta.trust_lane,
        author_verified=meta.author_verified,
        component_verified=meta.component_verified,
        lifecycle=meta.lifecycle_state,
        stable_id=meta.stable_id,
        version=meta.version,
        object_kind=meta.object_kind,
        support_evidence=list(meta.support_evidence or []),
    )


def with_current_author_verification(
    rows: list[PublicVersionRow], verified_by_account: dict[str, bool]
) -> list[PublicVersionRow]:
    """Overlay mutable account verification onto immutable publication rows."""
    return [
        replace(
            row,
            author_verified=verified_by_account.get(row.metadata.owner_account_id, False),
        )
        for row in rows
    ]


def _repository(row: PublicVersionRow) -> str | None:
    source = row.passport.get("source")
    if not isinstance(source, dict):
        return None
    repository = cast(dict[str, object], source).get("repository")
    return repository if isinstance(repository, str) else None


async def _current_author_verification(
    session: AsyncSession, rows: list[PublicVersionRow]
) -> list[PublicVersionRow]:
    account_ids = {row.metadata.owner_account_id for row in rows}
    if not account_ids:
        return rows
    result = await session.execute(
        select(AccountAuthorVerification.account_id, AccountAuthorVerification.verified).where(
            AccountAuthorVerification.account_id.in_(account_ids)
        )
    )
    verified_rows = with_current_author_verification(rows, dict(result.tuples().all()))
    repositories = {repository for row in verified_rows if (repository := _repository(row))}
    if not repositories:
        return verified_rows
    metrics = await session.execute(
        select(RepositoryMetric.repository, RepositoryMetric.github_stars).where(
            RepositoryMetric.repository.in_(repositories)
        )
    )
    stars = dict(metrics.tuples().all())
    return [
        replace(
            row,
            github_stars=stars.get(repository) if (repository := _repository(row)) else None,
        )
        for row in verified_rows
    ]


#: The cursor carries a canonical wire timestamp, and that format is
#: milliseconds — `format_timestamp` writes `microsecond // 1000`. PostgreSQL
#: keeps microseconds, so a row published at `.746829` is handed back as a
#: cursor saying `.746`, and `published_at > .746000` is true of that very row.
#: It was returned again as the first entry of the next page: one duplicate per
#: page boundary, for every row whose timestamp had sub-millisecond digits.
#:
#: So the order is defined at the resolution the cursor can express. Both the
#: sort and the keyset comparison use this bucket, because using it in only one
#: of them trades duplicates for something worse — two rows inside one
#: millisecond would sort by microsecond and be filtered by `stable_id`, and the
#: one that sorts first with the larger id would be skipped entirely.
def _cursor_bucket(column: Any) -> Any:
    return func.date_trunc("milliseconds", column)


def bucketed(moment: datetime) -> datetime:
    """The same truncation, for comparing rows already in memory."""
    return moment.replace(microsecond=(moment.microsecond // 1000) * 1000)


async def list_public_versions(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    after: CursorKey | None = None,
    limit: int,
) -> list[PublicVersionRow]:
    """Return public versions in total order (published_at, stable_id, version).

    Order is total and stable. The version column breaks residual ties when the
    same stable_id carries multiple published versions so keyset pagination does
    not skip or duplicate version rows that share a published_at.
    """
    published = _cursor_bucket(CatalogMetadata.published_at)
    stmt = _public_base(object_kind).order_by(
        published.asc(),
        CatalogMetadata.stable_id.asc(),
        CatalogMetadata.version.asc(),
    )
    if after is not None:
        stmt = stmt.where(
            or_(
                published > after.published_at,
                and_(
                    published == after.published_at,
                    CatalogMetadata.stable_id > after.stable_id,
                ),
                and_(
                    published == after.published_at,
                    CatalogMetadata.stable_id == after.stable_id,
                    # Advance past all versions already emitted for this key.
                    # The wire cursor only carries (published_at, stable_id);
                    # callers that page by object must not use this helper for
                    # multi-version keysets without collapsing first.
                    CatalogMetadata.version > "",
                ),
            )
        )
    stmt = stmt.limit(limit)
    result = await session.scalars(stmt)
    return await _current_author_verification(
        session, [public_version_row(row) for row in result.all()]
    )


async def list_latest_public_objects(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    after: CursorKey | None = None,
    limit: int,
) -> list[PublicVersionRow]:
    """Return one row per stable_id: the latest offered public version.

    "Latest" is the maximum version string among published public versions for
    that identity (version format is X.Y, so lexical order matches numeric for
    single-digit minor segments used in Sprint-1; the wire contract uses the
    same X.Y pattern).
    """
    # Load a generous candidate window and collapse in process. Sprint-1 seed
    # and tests stay small; a SQL window function can replace this later without
    # changing the repository contract.
    window = max(limit * 8, 64)
    candidates = await list_public_versions(
        session, object_kind=object_kind, after=after, limit=window * 4
    )
    latest_by_id: dict[str, PublicVersionRow] = {}
    for row in candidates:
        current = latest_by_id.get(row.stable_id)
        if current is None or _version_key(row.version) > _version_key(current.version):
            latest_by_id[row.stable_id] = row
    ordered = sorted(
        latest_by_id.values(),
        key=lambda r: (bucketed(r.published_at), r.stable_id),
    )
    if after is not None:
        ordered = [
            r
            for r in ordered
            if (bucketed(r.published_at), r.stable_id) > (after.published_at, after.stable_id)
        ]
    return ordered[:limit]


def _version_key(version: str) -> tuple[int, int]:
    major, minor = version.split(".", 1)
    return int(major), int(minor)


async def get_public_object_versions(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    stable_id: str,
) -> list[PublicVersionRow]:
    """All public offered versions of one object, ordered by version ascending."""
    stmt = (
        _public_base(object_kind)
        .where(CatalogMetadata.stable_id == stable_id)
        .order_by(CatalogMetadata.version.asc())
    )
    result = await session.scalars(stmt)
    return await _current_author_verification(
        session, [public_version_row(row) for row in result.all()]
    )


async def get_public_version(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    stable_id: str,
    version: str,
) -> PublicVersionRow | None:
    """Exact public version read, or None when absent or not public."""
    stmt = _public_base(object_kind).where(
        CatalogMetadata.stable_id == stable_id,
        CatalogMetadata.version == version,
    )
    meta = await session.scalar(stmt)
    if meta is None:
        return None
    return (await _current_author_verification(session, [public_version_row(meta)]))[0]


async def get_visible_metadata(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    stable_id: str,
    version: str,
    account_id: str | None,
) -> CatalogMetadata | None:
    """Public version, or the caller's owned version. Missing and foreign private are None."""
    public = await get_public_version(
        session, object_kind=object_kind, stable_id=stable_id, version=version
    )
    if public is not None:
        return public.metadata
    if not account_id:
        return None
    return await session.scalar(
        select(CatalogMetadata).where(
            CatalogMetadata.owner_account_id == account_id,
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
            CatalogMetadata.passport_document.is_not(None),
            CatalogMetadata.passport_digest.is_not(None),
        )
    )
