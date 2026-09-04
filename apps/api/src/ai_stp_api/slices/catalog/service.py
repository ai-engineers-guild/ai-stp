"""Catalog application service: search, detail, version (SPEC-021)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.catalog import (
    CatalogPageInfo,
    CatalogReactionList,
    CatalogReactionState,
    CatalogUsageMetrics,
    ComponentDetail,
    ComponentListResponse,
    ComponentMediaItem,
    ComponentSearchRequest,
    ComponentVersionResponse,
    CountryDetail,
    CountryListResponse,
    CountrySummary,
    ExternalProductDetail,
    ExternalProductListResponse,
    ExternalProductObject,
    ExternalProductSummary,
    GitHubMetadata,
    LikedCatalogItem,
    SetupDetail,
    SetupListResponse,
    SetupSearchRequest,
    SetupVersionResponse,
)
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.safety_checks import SafetyChecksSummary
from ai_stp_contracts.tag_vocabulary import TagVocabularyResponse, tag_vocabulary_response
from ai_stp_platform.catalog_cursor import (
    CursorError,
    CursorKey,
    decode_cursor,
    encode_cursor,
    filter_signature,
)
from ai_stp_platform.catalog_projection import (
    component_detail,
    component_summary,
    component_version_response,
    project_trust,
    setup_detail,
    setup_summary,
    setup_version_response,
)
from ai_stp_platform.catalog_query_language import QuerySyntaxError, parse_query
from ai_stp_platform.catalog_read import (
    CatalogIntegrityError,
    PublicVersionRow,
    get_public_object_versions,
    get_public_version,
    get_visible_metadata,
)
from ai_stp_platform.catalog_search import (
    relation_filter_signature,
    search_catalog,
    upsert_catalog_search_projection,
)
from ai_stp_platform.catalog_usage import CatalogUsagePolicy, load_usage_metrics
from ai_stp_platform.external_catalog import COUNTRY_CODES
from ai_stp_platform.github_metadata import (
    fetch_github_metadata,
    repository_from_passport,
    unavailable_metadata,
)
from ai_stp_platform.logging import get_logger
from ai_stp_platform.models import (
    CatalogExternalProduct,
    CatalogMetadata,
    CatalogReaction,
    ComponentMedia,
    ExternalProduct,
    ExternalProductCountry,
)

_log = get_logger("catalog")

ObjectKind = Literal["component", "setup"]


async def set_reaction(
    db: AsyncSession,
    *,
    account_id: str,
    object_kind: ObjectKind,
    stable_id: str,
    liked: bool,
) -> CatalogReactionState:
    """Persist one account reaction and keep the public aggregate consistent."""
    reader = read_component if object_kind == "component" else read_setup
    await reader(db, stable_id)
    if liked:
        await db.execute(
            insert(CatalogReaction)
            .values(account_id=account_id, object_kind=object_kind, stable_id=stable_id)
            .on_conflict_do_nothing(index_elements=["account_id", "object_kind", "stable_id"])
        )
    else:
        await db.execute(
            delete(CatalogReaction).where(
                CatalogReaction.account_id == account_id,
                CatalogReaction.object_kind == object_kind,
                CatalogReaction.stable_id == stable_id,
            )
        )
    count = int(
        await db.scalar(
            select(func.count())
            .select_from(CatalogReaction)
            .where(
                CatalogReaction.object_kind == object_kind,
                CatalogReaction.stable_id == stable_id,
            )
        )
        or 0
    )
    await db.execute(
        update(CatalogMetadata)
        .where(
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
        )
        .values(likes_count=count)
    )
    await upsert_catalog_search_projection(db, object_kind=object_kind, stable_id=stable_id)
    await db.flush()
    return CatalogReactionState(liked=liked, likes_count=count)


async def list_reactions(db: AsyncSession, *, account_id: str) -> CatalogReactionList:
    """Return public catalog projections liked by one account."""
    rows = (
        await db.execute(
            select(CatalogReaction)
            .where(CatalogReaction.account_id == account_id)
            .order_by(CatalogReaction.created_at.desc(), CatalogReaction.id.desc())
        )
    ).scalars()
    items: list[LikedCatalogItem] = []
    for reaction in rows:
        try:
            detail = await (
                read_component(db, reaction.stable_id)
                if reaction.object_kind == "component"
                else read_setup(db, reaction.stable_id)
            )
        except CatalogNotFound:
            continue
        object_kind: Literal["component", "setup"] = (
            "component" if reaction.object_kind == "component" else "setup"
        )
        items.append(LikedCatalogItem(object_kind=object_kind, summary=detail.summary))
    return CatalogReactionList(items=items)


class CatalogNotFound(Exception):
    """Absent or non-public catalog target (indistinguishable)."""


class CatalogCorrupt(Exception):
    """A reachable published row failed integrity verification (REQ-2108).

    Deliberately not CatalogNotFound. The row exists and is public; answering a
    miss would tell the caller to look elsewhere for something that is right
    there, and it hid a poisoned immutable version behind an ordinary 404 until
    the state was found by hand.
    """


class CatalogBadRequest(Exception):
    """Malformed cursor or invalid search parameters."""


def row_matches_updated_range(
    row: PublicVersionRow,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    """Apply the inclusive UTC calendar-day window to a public row."""
    if start is None and end is None:
        return True
    moment = row.metadata.updated_at or row.published_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if start is not None and moment < start:
        return False
    return not (end is not None and moment >= end)


def list_tag_vocabulary() -> TagVocabularyResponse:
    """Return the closed tag vocabulary. No catalog rows are required."""
    return tag_vocabulary_response()


def _product_summary(product: ExternalProduct, countries: list[str]) -> ExternalProductSummary:
    return ExternalProductSummary(
        name=product.name,
        canonical_domain=product.canonical_domain,
        primary_url=product.primary_url,
        description=product.description,
        source_url=product.source_url,
        country_codes=sorted(countries),
    )


async def read_object_relations(
    session: AsyncSession, *, object_kind: ObjectKind, stable_id: str
) -> tuple[list[str], list[ExternalProductSummary]]:
    """Linked services and implied country codes for one public catalog object."""
    metadata_ids = select(CatalogMetadata.id).where(
        CatalogMetadata.object_kind == object_kind,
        CatalogMetadata.stable_id == stable_id,
    )
    product_rows = list(
        (
            await session.execute(
                select(ExternalProduct)
                .join(
                    CatalogExternalProduct,
                    CatalogExternalProduct.external_product_id == ExternalProduct.id,
                )
                .where(CatalogExternalProduct.catalog_metadata_id.in_(metadata_ids))
                .order_by(ExternalProduct.name)
                .distinct()
            )
        ).scalars()
    )
    if not product_rows:
        return [], []
    country_rows = list(
        (
            await session.execute(
                select(ExternalProductCountry).where(
                    ExternalProductCountry.external_product_id.in_(
                        [product.id for product in product_rows]
                    )
                )
            )
        ).scalars()
    )
    by_product: dict[int, list[str]] = {}
    for row in country_rows:
        by_product.setdefault(row.external_product_id, []).append(row.country_code)
    services = [_product_summary(row, by_product.get(row.id, [])) for row in product_rows]
    countries = sorted({code for item in services for code in item.country_codes})
    return countries, services


async def list_external_products(session: AsyncSession) -> ExternalProductListResponse:
    products = list(
        (await session.execute(select(ExternalProduct).order_by(ExternalProduct.name))).scalars()
    )
    country_rows = (await session.execute(select(ExternalProductCountry))).scalars().all()
    by_product: dict[int, list[str]] = {}
    for row in country_rows:
        by_product.setdefault(row.external_product_id, []).append(row.country_code)
    return ExternalProductListResponse(
        items=[_product_summary(row, by_product.get(row.id, [])) for row in products]
    )


async def read_external_product(session: AsyncSession, domain: str) -> ExternalProductDetail:
    product = await session.scalar(
        select(ExternalProduct).where(ExternalProduct.canonical_domain == domain.lower())
    )
    if product is None:
        raise CatalogNotFound
    countries = list(
        (
            await session.execute(
                select(ExternalProductCountry.country_code).where(
                    ExternalProductCountry.external_product_id == product.id
                )
            )
        ).scalars()
    )
    objects = await _product_objects(session, product.id)
    summary = _product_summary(product, countries)
    return ExternalProductDetail(**summary.model_dump(), objects=objects)


async def _product_objects(session: AsyncSession, product_id: int) -> list[ExternalProductObject]:
    rows = list(
        (
            await session.execute(
                select(CatalogMetadata)
                .join(
                    CatalogExternalProduct,
                    CatalogExternalProduct.catalog_metadata_id == CatalogMetadata.id,
                )
                .where(
                    CatalogExternalProduct.external_product_id == product_id,
                    CatalogMetadata.visibility == "public",
                    CatalogMetadata.lifecycle_state == "active",
                    CatalogMetadata.published_at.is_not(None),
                )
                .order_by(CatalogMetadata.object_kind, CatalogMetadata.stable_id)
            )
        ).scalars()
    )
    seen: set[tuple[str, str]] = set()
    result: list[ExternalProductObject] = []
    for row in rows:
        key = (row.object_kind, row.stable_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            ExternalProductObject(
                object_kind=row.object_kind,  # type: ignore[arg-type]
                stable_id=row.stable_id,
                name=row.name or row.stable_id,
            )
        )
    return result


async def list_countries(session: AsyncSession) -> CountryListResponse:
    rows = list((await session.execute(select(ExternalProductCountry))).scalars())
    counts: dict[str, set[int]] = {}
    for row in rows:
        counts.setdefault(row.country_code, set()).add(row.external_product_id)
    return CountryListResponse(
        items=[
            CountrySummary(code=code, services_count=len(counts.get(code, set())))
            for code in sorted(COUNTRY_CODES)
        ]
    )


async def read_country(session: AsyncSession, code: str) -> CountryDetail:
    code = code.upper()
    if code not in COUNTRY_CODES:
        raise CatalogNotFound
    product_ids = list(
        (
            await session.execute(
                select(ExternalProductCountry.external_product_id).where(
                    ExternalProductCountry.country_code == code
                )
            )
        ).scalars()
    )
    products = (
        list(
            (
                await session.execute(
                    select(ExternalProduct)
                    .where(ExternalProduct.id.in_(product_ids))
                    .order_by(ExternalProduct.name)
                )
            ).scalars()
        )
        if product_ids
        else []
    )
    services = [_product_summary(row, [code]) for row in products]
    objects: list[ExternalProductObject] = []
    seen: set[tuple[str, str]] = set()
    for product in products:
        for item in await _product_objects(session, product.id):
            key = (item.object_kind, item.stable_id)
            if key not in seen:
                seen.add(key)
                objects.append(item)
    return CountryDetail(
        code=code,
        services_count=len(services),
        objects_count=len(objects),
        services=services,
        objects=objects,
    )


def _corrupt(
    exc: CatalogIntegrityError, *, object_kind: str, stable_id: str, version: str | None = None
) -> CatalogCorrupt:
    """Record the integrity failure, then hand back the error to raise.

    The log line is the operator's alert surface: the client answer carries a
    stable code and no detail, so if the reason is not recorded here it is not
    recorded anywhere.
    """
    _log.error(
        "catalog_integrity_failed",
        reason=str(exc),
        object_kind=object_kind,
        stable_id=stable_id,
        version=version or "",
    )
    return CatalogCorrupt(str(exc))


def _project_search_rows[T](
    rows: list[PublicVersionRow],
    projector: Callable[..., T],
    *,
    now: datetime,
    object_kind: str,
) -> list[T]:
    """Project search rows, mapping a reachable corrupt row to CatalogCorrupt.

    Search used to let CatalogIntegrityError escape as an unhandled 500
    INTERNAL. Detail already maps the same condition to CATALOG_INTEGRITY;
    skipping the row would change page completeness (REQ-2105).
    """
    items: list[T] = []
    for row in rows:
        try:
            items.append(projector(row, now=now))
        except CatalogIntegrityError as exc:
            raise _corrupt(
                exc, object_kind=object_kind, stable_id=row.stable_id, version=row.version
            ) from exc
    return items


@dataclass(frozen=True)
class SearchPage:
    authoritative: list[PublicVersionRow]
    experimental: list[PublicVersionRow]
    next_cursor: str | None
    page_size: int
    now: datetime
    page_number: int | None = None
    total_items: int | None = None


async def apply_usage_metrics[T](
    session: AsyncSession,
    model: T,
    *,
    policy: CatalogUsagePolicy,
) -> T:
    """Attach the one server aggregate, or leave fields absent when disabled."""
    if not policy.enabled:
        return model
    identifiers = _usage_stable_ids(model)
    metrics = await load_usage_metrics(session, identifiers, policy=policy)
    return _copy_with_usage(model, metrics)


def _usage_stable_ids(model: object) -> list[str]:
    if isinstance(model, (ComponentDetail, SetupDetail)):
        return [model.summary.stable_id]
    if isinstance(model, (ComponentVersionResponse, SetupVersionResponse)):
        return [model.passport.stable_id]
    if isinstance(model, (ComponentListResponse, SetupListResponse)):
        return [item.stable_id for item in (*model.items, *model.experimental)]
    return []


def _copy_with_usage[T](model: T, metrics: dict[str, CatalogUsageMetrics]) -> T:
    if isinstance(model, (ComponentDetail, SetupDetail)):
        summary = model.summary.model_copy(
            update={"usage_metrics": metrics[model.summary.stable_id]}
        )
        return model.model_copy(update={"summary": summary})
    if isinstance(model, (ComponentVersionResponse, SetupVersionResponse)):
        return model.model_copy(update={"usage_metrics": metrics[model.passport.stable_id]})
    if isinstance(model, ComponentListResponse):
        return model.model_copy(
            update={
                "items": [
                    item.model_copy(update={"usage_metrics": metrics[item.stable_id]})
                    for item in model.items
                ],
                "experimental": [
                    item.model_copy(update={"usage_metrics": metrics[item.stable_id]})
                    for item in model.experimental
                ],
            }
        )
    if isinstance(model, SetupListResponse):
        return model.model_copy(
            update={
                "items": [
                    item.model_copy(update={"usage_metrics": metrics[item.stable_id]})
                    for item in model.items
                ],
                "experimental": [
                    item.model_copy(update={"usage_metrics": metrics[item.stable_id]})
                    for item in model.experimental
                ],
            }
        )
    return model


async def search_components(
    session: AsyncSession,
    request: ComponentSearchRequest,
    *,
    cursor_secret: str,
) -> ComponentListResponse:
    page = await _search(
        session,
        object_kind="component",
        q=request.q,
        tags=list(request.tags),
        harness_id=request.harness_id,
        component_type=request.component_type,
        harness_ids=list(request.harness_ids),
        component_types=list(request.component_types),
        authors=list(request.authors),
        verified_only=request.verified_only,
        sort=request.sort,
        sort_direction=request.sort_direction,
        support_tier=request.support_tier,
        support_state=request.support_state,
        service_domain=request.service_domain,
        country_code=request.country_code,
        service_domains=list(request.service_domains),
        country_codes=list(request.country_codes),
        updated_from=request.updated_from,
        updated_to=request.updated_to,
        include_experimental=request.include_experimental,
        include_deprecated=request.include_deprecated,
        cursor=request.cursor,
        page_size=request.page_size,
        page_number=request.page,
        cursor_secret=cursor_secret,
    )
    return ComponentListResponse(
        items=_project_search_rows(
            page.authoritative, component_summary, now=page.now, object_kind="component"
        ),
        experimental=_project_search_rows(
            page.experimental, component_summary, now=page.now, object_kind="component"
        ),
        page=_page_info(page),
    )


async def search_setups(
    session: AsyncSession,
    request: SetupSearchRequest,
    *,
    cursor_secret: str,
) -> SetupListResponse:
    page = await _search(
        session,
        object_kind="setup",
        q=request.q,
        tags=list(request.tags),
        harness_id=request.harness_id,
        component_type=None,
        harness_ids=list(request.harness_ids),
        component_types=[],
        authors=list(request.authors),
        verified_only=request.verified_only,
        sort=request.sort,
        sort_direction=request.sort_direction,
        support_tier=request.support_tier,
        support_state=request.support_state,
        service_domain=request.service_domain,
        country_code=request.country_code,
        service_domains=list(request.service_domains),
        country_codes=list(request.country_codes),
        updated_from=request.updated_from,
        updated_to=request.updated_to,
        include_experimental=request.include_experimental,
        include_deprecated=request.include_deprecated,
        cursor=request.cursor,
        page_size=request.page_size,
        page_number=request.page,
        cursor_secret=cursor_secret,
    )
    return SetupListResponse(
        items=_project_search_rows(
            page.authoritative, setup_summary, now=page.now, object_kind="setup"
        ),
        experimental=_project_search_rows(
            page.experimental, setup_summary, now=page.now, object_kind="setup"
        ),
        page=_page_info(page),
    )


def _page_info(page: SearchPage) -> PageInfo | CatalogPageInfo:
    if page.page_number is None or page.total_items is None:
        return PageInfo(next_cursor=page.next_cursor, page_size=page.page_size)  # type: ignore[arg-type]
    total_pages = (page.total_items + page.page_size - 1) // page.page_size
    return CatalogPageInfo(
        mode="page",
        next_cursor=None,
        page_size=page.page_size,
        page_number=page.page_number,
        total_items=page.total_items,
        total_pages=total_pages,
        previous_page=page.page_number - 1 if page.page_number > 1 else None,
        next_page=page.page_number + 1 if page.page_number < total_pages else None,
    )


async def read_component(session: AsyncSession, stable_id: str) -> ComponentDetail:
    versions = await get_public_object_versions(
        session, object_kind="component", stable_id=stable_id
    )
    if not versions:
        raise CatalogNotFound
    try:
        detail = component_detail(versions, now=datetime.now(UTC))
        media_rows = (
            await session.execute(
                select(ComponentMedia)
                .where(ComponentMedia.stable_id == stable_id, ComponentMedia.state == "ready")
                .order_by(ComponentMedia.position)
                .limit(5)
            )
        ).scalars()
        media: list[ComponentMediaItem] = []
        for row in media_rows:
            url = row.youtube_video_id if row.kind == "youtube" else row.public_url
            if not url:
                continue
            media.append(
                ComponentMediaItem(
                    id=row.id,
                    kind=row.kind,  # type: ignore[arg-type]
                    url=url,
                    alt=row.alt,
                    caption=row.caption,
                    source_label={
                        "upload": "ai_stp storage",
                        "github": "GitHub",
                        "youtube": "YouTube",
                    }[row.source_type],
                )
            )
        country_codes, services = await read_object_relations(
            session, object_kind="component", stable_id=stable_id
        )
        return detail.model_copy(
            update={"media": media, "country_codes": country_codes, "services": services}
        )
    except CatalogIntegrityError as exc:
        raise _corrupt(exc, object_kind="component", stable_id=stable_id) from exc


async def read_setup(session: AsyncSession, stable_id: str) -> SetupDetail:
    versions = await get_public_object_versions(session, object_kind="setup", stable_id=stable_id)
    if not versions:
        raise CatalogNotFound
    try:
        detail = setup_detail(versions, now=datetime.now(UTC))
        country_codes, services = await read_object_relations(
            session, object_kind="setup", stable_id=stable_id
        )
        return detail.model_copy(update={"country_codes": country_codes, "services": services})
    except CatalogIntegrityError as exc:
        raise _corrupt(exc, object_kind="setup", stable_id=stable_id) from exc


async def read_component_version(
    session: AsyncSession, stable_id: str, version: str
) -> ComponentVersionResponse:
    row = await get_public_version(
        session, object_kind="component", stable_id=stable_id, version=version
    )
    if row is None:
        raise CatalogNotFound
    try:
        return component_version_response(row, now=datetime.now(UTC))
    except CatalogIntegrityError as exc:
        raise _corrupt(exc, object_kind="component", stable_id=stable_id, version=version) from exc


async def read_setup_version(
    session: AsyncSession, stable_id: str, version: str
) -> SetupVersionResponse:
    row = await get_public_version(
        session, object_kind="setup", stable_id=stable_id, version=version
    )
    if row is None:
        raise CatalogNotFound
    try:
        return setup_version_response(row, now=datetime.now(UTC))
    except CatalogIntegrityError as exc:
        raise _corrupt(exc, object_kind="setup", stable_id=stable_id, version=version) from exc


async def read_version_checks(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    stable_id: str,
    version: str,
) -> SafetyChecksSummary:
    """Public audit summary for one version (#270)."""
    from ai_stp_platform.catalog_projection import project_checks_summary

    row = await get_public_version(
        session, object_kind=object_kind, stable_id=stable_id, version=version
    )
    if row is None:
        raise CatalogNotFound
    summary = project_checks_summary(row, public=False)
    if summary is not None:
        return summary
    return SafetyChecksSummary(
        status="empty",
        checks_passed_percent=None,
        passed=0,
        failed=0,
        warning=0,
        total_countable=0,
        checks=[],
    )


async def read_github_metadata(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    stable_id: str,
    version: str,
    account_id: str | None,
    client: httpx.AsyncClient,
) -> GitHubMetadata:
    """One on-demand GitHub metadata read for a visible exact version."""
    row = await get_visible_metadata(
        session,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        account_id=account_id,
    )
    if row is None:
        raise CatalogNotFound
    repository = repository_from_passport(row.passport_document)
    if repository is None:
        return unavailable_metadata()
    return await fetch_github_metadata(repository, client=client)


async def _search(
    session: AsyncSession,
    *,
    object_kind: ObjectKind,
    q: str | None,
    tags: list[str],
    harness_id: str | None,
    component_type: str | None,
    harness_ids: list[str],
    component_types: list[str],
    authors: list[str],
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
    cursor: str | None,
    page_size: int,
    page_number: int | None,
    cursor_secret: str,
    updated_from: date | None = None,
    updated_to: date | None = None,
) -> SearchPage:
    if cursor is not None and page_number is not None:
        raise CatalogBadRequest("cursor and page modes are mutually exclusive")
    signed_service_domain, signed_country_code = relation_filter_signature(
        service_domain=service_domain,
        country_code=country_code,
        service_domains=service_domains,
        country_codes=country_codes,
    )
    fsig = filter_signature(
        object_kind=object_kind,
        q=q,
        tags=tags,
        harness_id=harness_id,
        component_type=component_type,
        harness_ids=harness_ids,
        component_types=component_types,
        authors=authors,
        verified_only=verified_only,
        sort=sort,
        sort_direction=sort_direction,
        support_tier=support_tier,
        support_state=support_state,
        service_domain=signed_service_domain,
        country_code=signed_country_code,
        include_experimental=include_experimental,
        include_deprecated=include_deprecated,
        updated_from=updated_from.isoformat() if updated_from is not None else None,
        updated_to=updated_to.isoformat() if updated_to is not None else None,
    )
    after: CursorKey | None = None
    if cursor is not None:
        try:
            after = decode_cursor(secret=cursor_secret, token=cursor, filter_sig=fsig)
        except CursorError as exc:
            raise CatalogBadRequest(str(exc)) from exc
    try:
        query_expression = parse_query(q or "")
    except QuerySyntaxError as exc:
        detail = f"catalog query error at offset {exc.offset}: {exc}"
        if exc.expected is not None:
            detail += f"; expected {exc.expected}"
        raise CatalogBadRequest(detail) from exc

    hits = await search_catalog(
        session,
        object_kind=object_kind,
        q=q,
        tags=tags,
        harness_id=harness_id,
        component_type=component_type,
        harness_ids=harness_ids,
        component_types=component_types,
        authors=authors,
        verified_only=verified_only,
        sort=sort,
        sort_direction=sort_direction,
        support_tier=support_tier,
        support_state=support_state,
        service_domain=service_domain,
        country_code=country_code,
        service_domains=service_domains,
        country_codes=country_codes,
        include_experimental=include_experimental,
        include_deprecated=include_deprecated,
        page_size=page_size,
        page_number=page_number,
        after=after,
        query_expression=query_expression,
        updated_from=updated_from,
        updated_to=updated_to,
    )
    next_cursor = None
    if hits.next_cursor_key is not None:
        next_cursor = encode_cursor(secret=cursor_secret, filter_sig=fsig, key=hits.next_cursor_key)
    authoritative: list[PublicVersionRow] = []
    experimental: list[PublicVersionRow] = []
    for row in hits.rows:
        trust = project_trust(row)
        if trust.trust_lane == "authoritative":
            authoritative.append(row)
        else:
            experimental.append(row)
    return SearchPage(
        authoritative=authoritative,
        experimental=experimental,
        next_cursor=next_cursor,
        page_size=page_size,
        now=datetime.now(UTC),
        page_number=page_number,
        total_items=hits.total_items,
    )


def sort_catalog_rows(
    rows: list[PublicVersionRow], *, sort: str, direction: str = "desc"
) -> list[PublicVersionRow]:
    """Stable public ordering for explicit time/likes modes."""
    if sort == "updated_at":
        return sorted(
            rows,
            key=lambda row: (row.metadata.updated_at or row.published_at, row.stable_id),
            reverse=direction == "desc",
        )
    return sorted(
        rows,
        key=lambda row: (
            row.metadata.likes_count or 0,
            row.metadata.updated_at or row.published_at,
            row.stable_id,
        ),
        reverse=direction == "desc",
    )


def sort_relevant_catalog_rows(
    rows: list[PublicVersionRow], *, q: str | None, direction: str = "desc"
) -> list[PublicVersionRow]:
    """Rank direct matches first, with deterministic recency tie-breaking."""
    needle = (q or "").strip().casefold()

    def score(row: PublicVersionRow) -> tuple[int, datetime, str]:
        passport = row.passport
        name = str(passport.get("name", "")).casefold()
        description = str(passport.get("description", "")).casefold()
        tags = {str(tag).casefold() for tag in passport.get("tags", [])}
        author = row.metadata.owner_account_id.casefold()
        relevance = 0
        if needle:
            relevance = (
                100
                if name == needle
                else 80
                if name.startswith(needle)
                else 60
                if needle in name
                else 0
            )
            if needle in tags:
                relevance = max(relevance, 50)
            if needle in author:
                relevance = max(relevance, 40)
            if needle in description:
                relevance = max(relevance, 20)
        return (relevance, row.metadata.updated_at or row.published_at, row.stable_id)

    return sorted(rows, key=score, reverse=direction == "desc")
