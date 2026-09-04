"""PostgreSQL-native public catalog search (ADR-0151, SPEC-034)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast

from sqlalchemy import (
    Select,
    and_,
    any_,
    case,
    delete,
    exists,
    false,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from ai_stp_contracts.catalog import (
    CATALOG_UNSPECIFIED_FILTER,
    merged_or_values,
    normalize_search_text,
    unique_sorted,
)
from ai_stp_contracts.tag_vocabulary import search_terms_for_tags
from ai_stp_platform.catalog_cursor import CursorKey
from ai_stp_platform.catalog_query_language import (
    Binary,
    Expression,
    Predicate,
    TextTerm,
    Unary,
    named_harness_ids,
)
from ai_stp_platform.catalog_read import (
    PUBLIC_LIFECYCLES,
    CatalogIntegrityError,
    PublicVersionRow,
    bucketed,
    current_author_verification,
    public_version_row,
)
from ai_stp_platform.catalog_support import project_support
from ai_stp_platform.models import (
    AccountAuthorVerification,
    CatalogExternalProduct,
    CatalogMetadata,
    CatalogSearchProjection,
    ExternalProduct,
    ExternalProductCountry,
)

ObjectKind = Literal["component", "setup"]
_DESCRIPTION_LIMIT = 8000


def inclusive_updated_bounds(
    updated_from: date | None, updated_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """UTC window: from >= start-of-day, to < next-day."""
    start = (
        datetime(updated_from.year, updated_from.month, updated_from.day, tzinfo=UTC)
        if updated_from is not None
        else None
    )
    if updated_to is None:
        return start, None
    nxt = updated_to + timedelta(days=1)
    return start, datetime(nxt.year, nxt.month, nxt.day, tzinfo=UTC)


@dataclass(frozen=True)
class RelationFilterPlan:
    """AND between country and service facets; OR inside each facet."""

    active: bool
    empty: bool
    include_unlinked: bool
    query_linked: bool
    domains: frozenset[str] | None
    countries: frozenset[str] | None
    include_country_less: bool


def merge_relation_filters(
    *,
    service_domain: str | None,
    country_code: str | None,
    service_domains: list[str],
    country_codes: list[str],
) -> tuple[frozenset[str], bool, frozenset[str], bool]:
    """Union singleton and multi filters."""
    domain_values = [*([service_domain] if service_domain else []), *service_domains]
    country_values = [*([country_code] if country_code else []), *country_codes]
    unspecified_service = any(
        value.casefold() == CATALOG_UNSPECIFIED_FILTER for value in domain_values
    )
    unspecified_country = any(
        value.casefold() == CATALOG_UNSPECIFIED_FILTER for value in country_values
    )
    domains = frozenset(
        value.lower() for value in domain_values if value.casefold() != CATALOG_UNSPECIFIED_FILTER
    )
    countries = frozenset(
        value.upper() for value in country_values if value.casefold() != CATALOG_UNSPECIFIED_FILTER
    )
    return domains, unspecified_service, countries, unspecified_country


def plan_relation_filter(
    *,
    service_domain: str | None,
    country_code: str | None,
    service_domains: list[str],
    country_codes: list[str],
) -> RelationFilterPlan:
    """Decide linked/unlinked SQL without mixing OR across independent facets."""
    domains, unspecified_service, countries, unspecified_country = merge_relation_filters(
        service_domain=service_domain,
        country_code=country_code,
        service_domains=service_domains,
        country_codes=country_codes,
    )
    service_active = bool(domains or unspecified_service)
    country_active = bool(countries or unspecified_country)
    if not service_active and not country_active:
        return RelationFilterPlan(
            active=False,
            empty=False,
            include_unlinked=False,
            query_linked=False,
            domains=None,
            countries=None,
            include_country_less=False,
        )
    include_unlinked = unspecified_service and (not country_active or unspecified_country)
    query_linked = bool(domains) or (country_active and not unspecified_service)
    return RelationFilterPlan(
        active=True,
        empty=not include_unlinked and not query_linked,
        include_unlinked=include_unlinked,
        query_linked=query_linked,
        domains=domains or None,
        countries=countries or None if country_active else None,
        include_country_less=unspecified_country and query_linked,
    )


def relation_filter_signature(
    *,
    service_domain: str | None,
    country_code: str | None,
    service_domains: list[str],
    country_codes: list[str],
) -> tuple[str | None, str | None]:
    """Stable cursor signature covering singleton and multi relation filters."""
    domains, unspecified_service, countries, unspecified_country = merge_relation_filters(
        service_domain=service_domain,
        country_code=country_code,
        service_domains=service_domains,
        country_codes=country_codes,
    )
    domain_tokens = sorted(domains)
    if unspecified_service:
        domain_tokens.append(CATALOG_UNSPECIFIED_FILTER)
    country_tokens = sorted(countries)
    if unspecified_country:
        country_tokens.append(CATALOG_UNSPECIFIED_FILTER)
    return ",".join(domain_tokens) or None, ",".join(country_tokens) or None


def _version_parts(version: str) -> tuple[int, int]:
    major, minor = version.split(".", 1)
    return int(major), int(minor)


def _passport_tags(passport: dict[str, Any]) -> list[str]:
    raw = passport.get("tags")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in cast(list[object], raw) if str(item)]


def _passport_description(passport: dict[str, Any]) -> str:
    raw = str(passport.get("description") or "")
    return raw[:_DESCRIPTION_LIMIT]


def _support_fields(
    passport: dict[str, Any], evidence: list[dict[str, Any]] | None, *, now: datetime
) -> tuple[str, str, datetime | None]:
    try:
        support = project_support(passport, evidence, now=now)
    except CatalogIntegrityError:
        return "primary", "not_verified", None
    expires: datetime | None = None
    if support.state == "verified":
        moments: list[datetime] = []
        for row in support.evidence:
            if not row.mandatory or row.expires_at is None:
                continue
            from ai_stp_foundation.timestamps import parse_timestamp

            moments.append(parse_timestamp(row.expires_at))
        if moments:
            expires = min(moments)
    return support.tier, support.state, expires


def _projection_row(meta: CatalogMetadata, *, now: datetime) -> CatalogSearchProjection:
    passport = dict(meta.passport_document or {})
    version = str(meta.version or "")
    major, minor = _version_parts(version)
    tags = _passport_tags(passport)
    component_type = passport.get("component_type")
    tier, state, expires = _support_fields(passport, list(meta.support_evidence or []), now=now)
    aliases = search_terms_for_tags(tags)
    description = _passport_description(passport)
    name = str(meta.name or passport.get("name") or "")
    return CatalogSearchProjection(
        catalog_metadata_id=meta.id,
        object_kind=meta.object_kind,
        stable_id=meta.stable_id,
        version=version,
        version_major=major,
        version_minor=minor,
        name=name,
        description=description,
        owner_account_id=meta.owner_account_id,
        component_type=str(component_type) if isinstance(component_type, str) else None,
        harness_ids=named_harness_ids(passport),
        tags=tags,
        tag_aliases=aliases,
        trust_lane=str(meta.trust_lane or "experimental"),
        component_verified=bool(meta.component_verified),
        lifecycle_state=meta.lifecycle_state,
        published_at=meta.published_at or now,
        updated_at=meta.updated_at or meta.published_at or now,
        likes_count=int(meta.likes_count or 0),
        support_tier=tier,
        support_state=state,
        support_expires_at=expires,
        search_text=" ".join(
            [name, description, meta.stable_id, meta.owner_account_id, *tags, *aliases]
        ).casefold(),
    )


async def _latest_public_metadata(
    session: AsyncSession, *, object_kind: str, stable_id: str
) -> CatalogMetadata | None:
    rows = list(
        (
            await session.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.object_kind == object_kind,
                    CatalogMetadata.stable_id == stable_id,
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)),
                    CatalogMetadata.published_at.is_not(None),
                    CatalogMetadata.version.is_not(None),
                    CatalogMetadata.passport_document.is_not(None),
                    CatalogMetadata.passport_digest.is_not(None),
                    CatalogMetadata.trust_lane.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    latest: CatalogMetadata | None = None
    latest_key: tuple[int, int] | None = None
    for row in rows:
        if row.version is None:
            continue
        key = _version_parts(row.version)
        if latest_key is None or key > latest_key:
            latest = row
            latest_key = key
    return latest


async def upsert_catalog_search_projection(
    session: AsyncSession, *, object_kind: str, stable_id: str
) -> None:
    """Replace the search row for one object with its latest public version."""
    # Serialize refreshes for one logical object. Publication, moderation and
    # reactions may commit concurrently; without this lock an older refresh
    # can delete the row inserted by a newer transaction.
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(f"catalog-search:{object_kind}:{stable_id}", 0)
            )
        )
    )
    await session.execute(
        delete(CatalogSearchProjection).where(
            CatalogSearchProjection.object_kind == object_kind,
            CatalogSearchProjection.stable_id == stable_id,
        )
    )
    latest = await _latest_public_metadata(session, object_kind=object_kind, stable_id=stable_id)
    if latest is None:
        return
    session.add(_projection_row(latest, now=datetime.now(UTC)))
    await session.flush()


async def rebuild_catalog_search_projection(session: AsyncSession) -> int:
    """Rebuild every search row from public catalog metadata."""
    await session.execute(delete(CatalogSearchProjection))
    rows = list(
        (
            await session.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)),
                    CatalogMetadata.published_at.is_not(None),
                    CatalogMetadata.version.is_not(None),
                    CatalogMetadata.passport_document.is_not(None),
                    CatalogMetadata.passport_digest.is_not(None),
                    CatalogMetadata.trust_lane.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    latest_by_id: dict[tuple[str, str], CatalogMetadata] = {}
    for row in rows:
        if row.version is None:
            continue
        key = (row.object_kind, row.stable_id)
        current = latest_by_id.get(key)
        if current is None or _version_parts(row.version) > _version_parts(
            current.version or "0.0"
        ):
            latest_by_id[key] = row
    now = datetime.now(UTC)
    for meta in latest_by_id.values():
        session.add(_projection_row(meta, now=now))
    await session.flush()
    return len(latest_by_id)


def compile_expression(
    expression: Expression | None,
    *,
    projection: type[CatalogSearchProjection],
    author_verified: ColumnElement[bool],
) -> ColumnElement[bool] | None:
    """Compile a bounded Catalog QL AST into a parameterized predicate."""
    if expression is None:
        return None
    if isinstance(expression, TextTerm):
        tsquery = func.plainto_tsquery("simple", expression.value)
        return projection.search_vector.op("@@")(tsquery)
    if isinstance(expression, Unary):
        inner = compile_expression(
            expression.operand, projection=projection, author_verified=author_verified
        )
        return ~inner if inner is not None else None
    if isinstance(expression, Binary):
        left = compile_expression(
            expression.left, projection=projection, author_verified=author_verified
        )
        right = compile_expression(
            expression.right, projection=projection, author_verified=author_verified
        )
        if left is None:
            return right
        if right is None:
            return left
        if expression.operator == "AND":
            return and_(left, right)
        return or_(left, right)
    return _compile_predicate(expression, projection=projection, author_verified=author_verified)


def _compile_predicate(
    predicate: Predicate,
    *,
    projection: type[CatalogSearchProjection],
    author_verified: ColumnElement[bool],
) -> ColumnElement[bool]:
    wanted = [value.casefold() for value in predicate.values]
    if predicate.field == "NAME":
        present = func.lower(projection.name).in_(wanted)
    elif predicate.field == "TAGS":
        present = or_(*[literal(value) == any_(projection.tags) for value in wanted])
    elif predicate.field == "HARNESS":
        present = or_(*[literal(value) == any_(projection.harness_ids) for value in wanted])
    elif predicate.field == "TYPE":
        present = func.lower(func.coalesce(projection.component_type, "")).in_(wanted)
    elif predicate.field == "AUTHOR":
        present = func.lower(projection.owner_account_id).in_(wanted)
    else:
        flag = and_(author_verified.is_(True), projection.component_verified.is_(True))
        present = or_(*[flag.is_(True) if value == "true" else flag.is_(False) for value in wanted])
    if predicate.operator == "NOT IN":
        return ~present
    return present


def _relation_clause(
    projection: type[CatalogSearchProjection], plan: RelationFilterPlan
) -> ColumnElement[bool] | None:
    if not plan.active:
        return None
    if plan.empty:
        return false()
    linked = (
        select(1)
        .select_from(CatalogExternalProduct)
        .join(ExternalProduct, ExternalProduct.id == CatalogExternalProduct.external_product_id)
    )
    if plan.domains is not None:
        linked = linked.where(ExternalProduct.canonical_domain.in_(plan.domains))
    if plan.countries is not None or plan.include_country_less:
        linked = linked.outerjoin(
            ExternalProductCountry,
            ExternalProductCountry.external_product_id == ExternalProduct.id,
        )
        if plan.countries is not None and plan.include_country_less:
            linked = linked.where(
                or_(
                    ExternalProductCountry.country_code.is_(None),
                    ExternalProductCountry.country_code.in_(plan.countries),
                )
            )
        elif plan.include_country_less:
            linked = linked.where(ExternalProductCountry.country_code.is_(None))
        elif plan.countries is not None:
            linked = linked.where(ExternalProductCountry.country_code.in_(plan.countries))
    linked = linked.where(
        CatalogExternalProduct.catalog_metadata_id == projection.catalog_metadata_id
    )
    parts: list[ColumnElement[bool]] = []
    if plan.query_linked:
        parts.append(exists(linked))
    if plan.include_unlinked:
        parts.append(
            ~exists(
                select(1).where(
                    CatalogExternalProduct.catalog_metadata_id == projection.catalog_metadata_id
                )
            )
        )
    return or_(*parts) if parts else false()


def _time_bucket(column: Any) -> Any:
    return func.date_trunc("milliseconds", column)


def _relevance_expr(
    projection: type[CatalogSearchProjection], *, q: str | None
) -> ColumnElement[Any]:
    needle = (q or "").strip().casefold()
    if not needle:
        return literal(0)
    name = func.lower(func.coalesce(projection.name, ""))
    name_score = case(
        (name == needle, 100),
        (func.strpos(name, needle) == 1, 80),
        (func.strpos(name, needle) > 0, 60),
        else_=0,
    )
    tag_score = case((literal(needle) == any_(projection.tags), 50), else_=0)
    author_score = case(
        (func.strpos(func.lower(projection.owner_account_id), needle) > 0, 40),
        else_=0,
    )
    description_score = case(
        (func.strpos(func.lower(func.coalesce(projection.description, "")), needle) > 0, 20),
        else_=0,
    )
    discrete = func.greatest(name_score, tag_score, author_score, description_score)
    ts_part = func.least(
        func.coalesce(
            func.round(
                func.ts_rank_cd(projection.search_vector, func.plainto_tsquery("simple", q)) * 10000
            ),
            0,
        ),
        9999,
    )
    return discrete * 10000 + ts_part


def _order_columns(
    projection: type[CatalogSearchProjection],
    *,
    sort: str,
    descending: bool,
    rank: ColumnElement[Any],
) -> list[Any]:
    updated = _time_bucket(projection.updated_at)
    if sort == "likes":
        keys = [projection.likes_count, updated, projection.stable_id]
    elif sort == "updated_at":
        keys = [updated, projection.stable_id]
    else:
        keys = [rank, updated, projection.stable_id]
    return [key.desc() if descending else key.asc() for key in keys]


def _keyset_clause(
    projection: type[CatalogSearchProjection],
    *,
    sort: str,
    descending: bool,
    after: CursorKey,
    rank: ColumnElement[Any],
) -> ColumnElement[bool]:
    updated = _time_bucket(projection.updated_at)
    cmp_op = "__lt__" if descending else "__gt__"
    if sort == "likes":
        keys = [
            (projection.likes_count, after.likes_count),
            (updated, after.published_at),
            (projection.stable_id, after.stable_id),
        ]
    elif sort == "updated_at":
        keys = [(updated, after.published_at), (projection.stable_id, after.stable_id)]
    else:
        keys = [
            (rank, after.relevance),
            (updated, after.published_at),
            (projection.stable_id, after.stable_id),
        ]
    clauses: list[ColumnElement[bool]] = []
    for index, (column, value) in enumerate(keys):
        prefix = [keys[i][0] == keys[i][1] for i in range(index)]
        inequality = getattr(column, cmp_op)(value)
        clauses.append(and_(*prefix, inequality) if prefix else inequality)
    return or_(*clauses)


@dataclass(frozen=True)
class CatalogSearchHits:
    rows: list[PublicVersionRow]
    ranks: list[int]
    next_cursor_key: CursorKey | None
    page_number: int | None
    total_items: int | None
    page_size: int


async def search_catalog(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    q: str | None,
    tags: Sequence[str],
    harness_id: str | None,
    component_type: str | None,
    harness_ids: Sequence[str],
    component_types: Sequence[str],
    authors: Sequence[str],
    verified_only: bool,
    sort: str,
    sort_direction: str,
    support_tier: str | None,
    support_state: str | None,
    service_domain: str | None,
    country_code: str | None,
    service_domains: list[str],
    country_codes: list[str],
    include_experimental: bool,
    include_deprecated: bool,
    page_size: int,
    page_number: int | None,
    after: CursorKey | None,
    query_expression: Expression | None,
    updated_from: date | None,
    updated_to: date | None,
) -> CatalogSearchHits:
    """Execute listing, ranking, totals, and keyset pagination in SQL."""
    q = normalize_search_text(q)
    tag_filter = unique_sorted(tags)
    harness_filter = merged_or_values(harness_id, harness_ids)
    type_filter = merged_or_values(component_type, component_types)
    author_filter = unique_sorted(authors)
    descending = sort_direction != "asc"
    projection = CatalogSearchProjection
    author_verified = func.coalesce(AccountAuthorVerification.verified, False)
    rank = _relevance_expr(projection, q=q)
    now = datetime.now(UTC)

    stmt: Select[Any] = (
        select(projection, CatalogMetadata, rank.label("search_rank"))
        .join(CatalogMetadata, CatalogMetadata.id == projection.catalog_metadata_id)
        .outerjoin(
            AccountAuthorVerification,
            AccountAuthorVerification.account_id == projection.owner_account_id,
        )
        .where(projection.object_kind == object_kind)
    )
    if not include_deprecated:
        stmt = stmt.where(projection.lifecycle_state == "active")
    else:
        stmt = stmt.where(projection.lifecycle_state.in_(tuple(PUBLIC_LIFECYCLES)))

    is_authoritative = and_(
        author_verified.is_(True),
        projection.component_verified.is_(True),
        projection.trust_lane == "authoritative",
    )
    if not include_experimental:
        stmt = stmt.where(is_authoritative)
    if verified_only:
        stmt = stmt.where(author_verified.is_(True), projection.component_verified.is_(True))
    if tag_filter:
        stmt = stmt.where(projection.tags.contains(tag_filter))
    if harness_filter:
        stmt = stmt.where(projection.harness_ids.overlap(harness_filter))
    if type_filter:
        stmt = stmt.where(projection.component_type.in_(type_filter))
    if author_filter:
        stmt = stmt.where(projection.owner_account_id.in_(author_filter))
    if support_tier is not None:
        stmt = stmt.where(projection.support_tier == support_tier)
    if support_state is not None:
        effective_state = case(
            (
                and_(
                    projection.support_state == "verified",
                    projection.support_expires_at.is_not(None),
                    projection.support_expires_at <= now,
                ),
                "stale",
            ),
            else_=projection.support_state,
        )
        stmt = stmt.where(effective_state == support_state)
    start, end = inclusive_updated_bounds(updated_from, updated_to)
    if start is not None:
        stmt = stmt.where(projection.updated_at >= start)
    if end is not None:
        stmt = stmt.where(projection.updated_at < end)
    relation = _relation_clause(
        projection,
        plan_relation_filter(
            service_domain=service_domain,
            country_code=country_code,
            service_domains=service_domains,
            country_codes=country_codes,
        ),
    )
    if relation is not None:
        stmt = stmt.where(relation)
    compiled = compile_expression(
        query_expression, projection=projection, author_verified=author_verified
    )
    if compiled is not None:
        stmt = stmt.where(compiled)

    order = _order_columns(projection, sort=sort, descending=descending, rank=rank)
    total_items: int | None = None
    if page_number is not None:
        total_items = int(
            await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        offset = (page_number - 1) * page_size
        page_stmt = stmt.order_by(*order).offset(offset).limit(page_size)
        fetch_limit = page_size
    else:
        page_stmt = stmt
        if after is not None:
            page_stmt = page_stmt.where(
                _keyset_clause(projection, sort=sort, descending=descending, after=after, rank=rank)
            )
        page_stmt = page_stmt.order_by(*order).limit(page_size + 1)
        fetch_limit = page_size + 1

    fetched = list((await session.execute(page_stmt)).all())
    extra = page_number is None and len(fetched) > page_size
    page_rows = fetched[:page_size] if extra else fetched[:fetch_limit]
    if page_number is not None:
        page_rows = fetched

    metas = [cast(CatalogMetadata, row[1]) for row in page_rows]
    ranks = [int(row[2] or 0) for row in page_rows]
    public_rows = await current_author_verification(
        session, [public_version_row(meta) for meta in metas]
    )
    next_key: CursorKey | None = None
    if extra and public_rows:
        last_meta = metas[-1]
        last_proj = cast(CatalogSearchProjection, page_rows[-1][0])
        next_key = CursorKey(
            published_at=bucketed(
                last_proj.updated_at or last_meta.published_at or datetime.now(UTC)
            ),
            stable_id=last_proj.stable_id,
            likes_count=int(last_proj.likes_count or 0),
            relevance=ranks[-1],
        )
    return CatalogSearchHits(
        rows=public_rows,
        ranks=ranks,
        next_cursor_key=next_key,
        page_number=page_number,
        total_items=total_items,
        page_size=page_size,
    )
