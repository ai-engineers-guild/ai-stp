"""Anonymous GET routes for the public catalog (frozen #71 contract)."""

from __future__ import annotations

import re
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, get_settings, optional_auth, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.catalog import service
from ai_stp_api.slices.catalog.artifact_service import (
    ArtifactCorrupt,
    ArtifactNotFound,
    read_public_artifact,
)
from ai_stp_contracts.catalog import (
    CATALOG_UNSPECIFIED_FILTER,
    ComponentSearchRequest,
    SetupContextBudgetQuery,
    SetupSearchRequest,
)
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.versioning import VersionError, parse_version
from ai_stp_platform.catalog_usage import (
    ARTIFACT_DOWNLOAD,
    DETAIL_VIEW,
    peer_network_signal,
    record_usage,
)
from ai_stp_platform.selection_impact import (
    SelectionInvalid,
    SelectionNotFound,
    setup_context_budget,
)
from ai_stp_platform.storage.object_store import ImmutableObjectStore

router = APIRouter(tags=["catalog"])

_COMPONENT_ID_RE = re.compile(stable_id_pattern("component"))
_SETUP_ID_RE = re.compile(stable_id_pattern("setup"))


def require_component_id(stable_id: str) -> str:
    if _COMPONENT_ID_RE.fullmatch(stable_id) is None:
        raise ApiError(ErrorCategory.VALIDATION, "invalid component id")
    return stable_id


def require_setup_id(stable_id: str) -> str:
    if _SETUP_ID_RE.fullmatch(stable_id) is None:
        raise ApiError(ErrorCategory.VALIDATION, "invalid setup id")
    return stable_id


def require_catalog_target(object_kind: str, stable_id: str) -> tuple[service.ObjectKind, str]:
    if object_kind == "component":
        return "component", require_component_id(stable_id)
    if object_kind == "setup":
        return "setup", require_setup_id(stable_id)
    raise ApiError(ErrorCategory.VALIDATION, "invalid catalog object kind")


def require_version(version: str) -> str:
    """Reject non-canonical X.Y (OpenAPI path pattern / SPEC-015)."""
    try:
        parse_version(version)
    except VersionError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "invalid version") from exc
    return version


def _flatten_query_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            token = part.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def _normalize_country_filters(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for token in _flatten_query_values(values):
        value = (
            CATALOG_UNSPECIFIED_FILTER
            if token.casefold() == CATALOG_UNSPECIFIED_FILTER
            else token.upper()
        )
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_domain_filters(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for token in _flatten_query_values(values):
        value = token.lower()
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


_COMPONENT_SEARCH_KEYS = frozenset(
    {
        "schema_version",
        "q",
        "tags",
        "harness_id",
        "component_type",
        "harness_ids",
        "component_types",
        "authors",
        "verified_only",
        "sort",
        "sort_direction",
        "support_tier",
        "support_state",
        "service_domain",
        "country_code",
        "service_domains",
        "country_codes",
        "updated_from",
        "updated_to",
        "cursor",
        "page_size",
        "page",
        "include_experimental",
    }
)
_SETUP_SEARCH_KEYS = frozenset(
    {
        "schema_version",
        "q",
        "tags",
        "harness_id",
        "harness_ids",
        "authors",
        "verified_only",
        "sort",
        "sort_direction",
        "support_tier",
        "support_state",
        "service_domain",
        "country_code",
        "service_domains",
        "country_codes",
        "updated_from",
        "updated_to",
        "cursor",
        "page_size",
        "page",
        "include_experimental",
    }
)


def _resource(request: Request, model: object) -> JSONResponse:
    """Return the resource body itself — no ok/data wrapper (http.py)."""
    del request
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    return JSONResponse(content=payload, status_code=200)


async def _publish_usage(request: Request, db: AsyncSession, model: object) -> object:
    policy = get_settings(request).catalog.usage_policy()
    return await service.apply_usage_metrics(db, model, policy=policy)


async def _count_detail_view(request: Request, db: AsyncSession, stable_id: str) -> None:
    policy = get_settings(request).catalog.usage_policy()
    host = request.client.host if request.client is not None else None
    await record_usage(
        db,
        policy=policy,
        action=DETAIL_VIEW,
        stable_id=stable_id,
        network_signal=peer_network_signal(host),
        method=request.method,
    )


async def _count_artifact_download(request: Request, db: AsyncSession, stable_id: str) -> None:
    policy = get_settings(request).catalog.usage_policy()
    host = request.client.host if request.client is not None else None
    await record_usage(
        db,
        policy=policy,
        action=ARTIFACT_DOWNLOAD,
        stable_id=stable_id,
        network_signal=peer_network_signal(host),
        method=request.method,
    )


def _reject_unknown_query(request: Request, allowed: frozenset[str]) -> None:
    """Unknown query keys are dropped filters — reject, do not ignore (REQ-2105)."""
    unknown = sorted({key for key in request.query_params if key not in allowed})
    if unknown:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "request validation failed",
            details={"fields": ",".join(unknown)},
        )


@router.get("/catalog/services", response_model=None)
async def list_external_products(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    return _resource(request, await service.list_external_products(db))


@router.get("/catalog/services/{domain}", response_model=None)
async def read_external_product(
    request: Request, domain: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    try:
        result = await service.read_external_product(db, domain)
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "service not found") from exc
    return _resource(request, result)


@router.get("/catalog/countries", response_model=None)
async def list_countries(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    return _resource(request, await service.list_countries(db))


@router.get("/catalog/countries/{code}", response_model=None)
async def read_country(
    request: Request, code: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    try:
        result = await service.read_country(db, code)
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "country not found") from exc
    return _resource(request, result)


def _component_search_request(
    request: Request,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    harness_id: Annotated[str | None, Query()] = None,
    component_type: Annotated[str | None, Query()] = None,
    harness_ids: Annotated[list[str] | None, Query()] = None,
    component_types: Annotated[list[str] | None, Query()] = None,
    authors: Annotated[list[str] | None, Query()] = None,
    verified_only: Annotated[bool, Query()] = False,
    sort: Annotated[str, Query()] = "relevance",
    sort_direction: Annotated[str, Query()] = "desc",
    support_tier: Annotated[str | None, Query()] = None,
    support_state: Annotated[str | None, Query()] = None,
    service_domain: Annotated[str | None, Query()] = None,
    country_code: Annotated[str | None, Query()] = None,
    service_domains: Annotated[list[str] | None, Query()] = None,
    country_codes: Annotated[list[str] | None, Query()] = None,
    updated_from: Annotated[str | None, Query()] = None,
    updated_to: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
    page: Annotated[int | None, Query(ge=1, le=10_000)] = None,
    include_experimental: Annotated[bool, Query()] = False,
) -> ComponentSearchRequest:
    _reject_unknown_query(request, _COMPONENT_SEARCH_KEYS)
    try:
        return ComponentSearchRequest(
            q=q,
            tags=list(tags or []),
            harness_id=harness_id,  # type: ignore[arg-type]
            component_type=component_type,  # type: ignore[arg-type]
            harness_ids=list(harness_ids or []),  # type: ignore[arg-type]
            component_types=list(component_types or []),  # type: ignore[arg-type]
            authors=list(authors or []),
            verified_only=verified_only,
            sort=sort,  # type: ignore[arg-type]
            sort_direction=sort_direction,  # type: ignore[arg-type]
            support_tier=support_tier,  # type: ignore[arg-type]
            support_state=support_state,  # type: ignore[arg-type]
            service_domain=service_domain,
            country_code=country_code,  # type: ignore[arg-type]
            service_domains=_normalize_domain_filters(service_domains),
            country_codes=_normalize_country_filters(country_codes),  # type: ignore[arg-type]
            updated_from=updated_from,  # type: ignore[arg-type]
            updated_to=updated_to,  # type: ignore[arg-type]
            cursor=cursor,  # type: ignore[arg-type]
            page_size=page_size,
            page=page,
            include_experimental=include_experimental,
        )
    except ValidationError as exc:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "request validation failed",
            details={"fields": ",".join(str(e["loc"]) for e in exc.errors())},
        ) from exc


def _setup_search_request(
    request: Request,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    harness_id: Annotated[str | None, Query()] = None,
    harness_ids: Annotated[list[str] | None, Query()] = None,
    authors: Annotated[list[str] | None, Query()] = None,
    verified_only: Annotated[bool, Query()] = False,
    sort: Annotated[str, Query()] = "relevance",
    sort_direction: Annotated[str, Query()] = "desc",
    support_tier: Annotated[str | None, Query()] = None,
    support_state: Annotated[str | None, Query()] = None,
    service_domain: Annotated[str | None, Query()] = None,
    country_code: Annotated[str | None, Query()] = None,
    service_domains: Annotated[list[str] | None, Query()] = None,
    country_codes: Annotated[list[str] | None, Query()] = None,
    updated_from: Annotated[str | None, Query()] = None,
    updated_to: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
    page: Annotated[int | None, Query(ge=1, le=10_000)] = None,
    include_experimental: Annotated[bool, Query()] = False,
) -> SetupSearchRequest:
    _reject_unknown_query(request, _SETUP_SEARCH_KEYS)
    try:
        return SetupSearchRequest(
            q=q,
            tags=list(tags or []),
            harness_id=harness_id,  # type: ignore[arg-type]
            harness_ids=list(harness_ids or []),  # type: ignore[arg-type]
            authors=list(authors or []),
            verified_only=verified_only,
            sort=sort,  # type: ignore[arg-type]
            sort_direction=sort_direction,  # type: ignore[arg-type]
            support_tier=support_tier,  # type: ignore[arg-type]
            support_state=support_state,  # type: ignore[arg-type]
            service_domain=service_domain,
            country_code=country_code,  # type: ignore[arg-type]
            service_domains=_normalize_domain_filters(service_domains),
            country_codes=_normalize_country_filters(country_codes),  # type: ignore[arg-type]
            updated_from=updated_from,  # type: ignore[arg-type]
            updated_to=updated_to,  # type: ignore[arg-type]
            cursor=cursor,  # type: ignore[arg-type]
            page_size=page_size,
            page=page,
            include_experimental=include_experimental,
        )
    except ValidationError as exc:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "request validation failed",
            details={"fields": ",".join(str(e["loc"]) for e in exc.errors())},
        ) from exc


@router.get("/catalog/components", response_model=None)
async def search_components(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    search: Annotated[ComponentSearchRequest, Depends(_component_search_request)],
) -> JSONResponse:
    """GET /v1/catalog/components — anonymous component search."""
    try:
        result = await service.search_components(
            db, search, cursor_secret=settings.catalog.cursor_signing_secret
        )
        result = await _publish_usage(request, db, result)
    except service.CatalogBadRequest as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    except service.CatalogCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog object failed integrity verification"
        ) from exc
    return _resource(request, result)


@router.get("/account/catalog-reactions", response_model=None)
async def list_reactions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    return _resource(request, await service.list_reactions(db, account_id=ctx.account_id))


@router.put("/account/catalog-reactions/{object_kind}/{stable_id}", response_model=None)
async def like_catalog_object(
    request: Request,
    object_kind: str,
    stable_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    kind, target = require_catalog_target(object_kind, stable_id)
    try:
        result = await service.set_reaction(
            db, account_id=ctx.account_id, object_kind=kind, stable_id=target, liked=True
        )
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    return _resource(request, result)


@router.delete("/account/catalog-reactions/{object_kind}/{stable_id}", response_model=None)
async def unlike_catalog_object(
    request: Request,
    object_kind: str,
    stable_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    kind, target = require_catalog_target(object_kind, stable_id)
    try:
        result = await service.set_reaction(
            db, account_id=ctx.account_id, object_kind=kind, stable_id=target, liked=False
        )
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    return _resource(request, result)


@router.get("/catalog/components/{stable_id}", response_model=None)
async def read_component(
    request: Request,
    stable_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /v1/catalog/components/{stable_id}."""
    stable_id = require_component_id(stable_id)
    try:
        result = await service.read_component(db, stable_id)
        await _count_detail_view(request, db, stable_id)
        result = await _publish_usage(request, db, result)
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except service.CatalogCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog object failed integrity verification"
        ) from exc
    return _resource(request, result)


@router.get("/catalog/components/{stable_id}/versions/{version}", response_model=None)
async def read_component_version(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /v1/catalog/components/{stable_id}/versions/{version}."""
    stable_id = require_component_id(stable_id)
    version = require_version(version)
    try:
        result = await service.read_component_version(db, stable_id, version)
        result = await _publish_usage(request, db, result)
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except service.CatalogCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog object failed integrity verification"
        ) from exc
    return _resource(request, result)


@router.get("/catalog/components/{stable_id}/versions/{version}/checks", response_model=None)
async def read_component_version_checks(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /v1/catalog/components/{stable_id}/versions/{version}/checks (#270)."""
    stable_id = require_component_id(stable_id)
    version = require_version(version)
    try:
        result = await service.read_version_checks(
            db, object_kind="component", stable_id=stable_id, version=version
        )
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    return _resource(request, result)


@router.get("/catalog/components/{stable_id}/versions/{version}/artifact", response_model=None)
async def read_component_artifact(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Return verified component bytes without exposing the opaque object key."""
    stable_id = require_component_id(stable_id)
    version = require_version(version)
    store = ImmutableObjectStore(settings=settings.storage, client=request.app.state.object_client)
    try:
        payload = await read_public_artifact(
            db,
            store=store,
            object_kind="component",
            stable_id=stable_id,
            version=version,
        )
        await _count_artifact_download(request, db, stable_id)
    except ArtifactNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except ArtifactCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog artifact failed integrity verification"
        ) from exc
    return StreamingResponse(
        iter((payload,)),
        media_type="application/octet-stream",
        headers={"Content-Length": str(len(payload))},
    )


@router.get("/catalog/setups", response_model=None)
async def search_setups(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    search: Annotated[SetupSearchRequest, Depends(_setup_search_request)],
) -> JSONResponse:
    """GET /v1/catalog/setups — anonymous setup search."""
    try:
        result = await service.search_setups(
            db, search, cursor_secret=settings.catalog.cursor_signing_secret
        )
        result = await _publish_usage(request, db, result)
    except service.CatalogBadRequest as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    except service.CatalogCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog object failed integrity verification"
        ) from exc
    return _resource(request, result)


@router.get("/catalog/setups/{stable_id}", response_model=None)
async def read_setup(
    request: Request,
    stable_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /v1/catalog/setups/{stable_id}."""
    stable_id = require_setup_id(stable_id)
    try:
        result = await service.read_setup(db, stable_id)
        await _count_detail_view(request, db, stable_id)
        result = await _publish_usage(request, db, result)
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except service.CatalogCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog object failed integrity verification"
        ) from exc
    return _resource(request, result)


@router.get("/catalog/setups/{stable_id}/versions/{version}", response_model=None)
async def read_setup_version(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /v1/catalog/setups/{stable_id}/versions/{version}."""
    stable_id = require_setup_id(stable_id)
    version = require_version(version)
    try:
        result = await service.read_setup_version(db, stable_id, version)
        result = await _publish_usage(request, db, result)
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except service.CatalogCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog object failed integrity verification"
        ) from exc
    return _resource(request, result)


@router.get("/catalog/setups/{stable_id}/versions/{version}/checks", response_model=None)
async def read_setup_version_checks(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /v1/catalog/setups/{stable_id}/versions/{version}/checks (#270)."""
    stable_id = require_setup_id(stable_id)
    version = require_version(version)
    try:
        result = await service.read_version_checks(
            db, object_kind="setup", stable_id=stable_id, version=version
        )
    except service.CatalogNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    return _resource(request, result)


@router.get("/catalog/setups/{stable_id}/versions/{version}/artifact", response_model=None)
async def read_setup_artifact(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Return verified setup bytes without exposing the opaque object key."""
    stable_id = require_setup_id(stable_id)
    version = require_version(version)
    store = ImmutableObjectStore(settings=settings.storage, client=request.app.state.object_client)
    try:
        payload = await read_public_artifact(
            db,
            store=store,
            object_kind="setup",
            stable_id=stable_id,
            version=version,
        )
        await _count_artifact_download(request, db, stable_id)
    except ArtifactNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except ArtifactCorrupt as exc:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "catalog artifact failed integrity verification"
        ) from exc
    return StreamingResponse(
        iter((payload,)),
        media_type="application/octet-stream",
        headers={"Content-Length": str(len(payload))},
    )


def _store(request: Request) -> ImmutableObjectStore | None:
    client = getattr(request.app.state, "object_client", None)
    settings = getattr(request.app.state, "settings", None)
    if client is None or settings is None:
        return None
    return ImmutableObjectStore(settings=settings.storage, client=client)


@router.get(
    "/catalog/components/{stable_id}/versions/{version}/github-metadata", response_model=None
)
async def read_component_github_metadata(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext | None, Depends(optional_auth)],
) -> JSONResponse:
    stable_id = require_component_id(stable_id)
    version = require_version(version)
    async with httpx.AsyncClient() as client:
        try:
            result = await service.read_github_metadata(
                db,
                object_kind="component",
                stable_id=stable_id,
                version=version,
                account_id=None if ctx is None else ctx.account_id,
                client=client,
            )
        except service.CatalogNotFound as exc:
            raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    return _resource(request, result)


@router.get("/catalog/setups/{stable_id}/versions/{version}/github-metadata", response_model=None)
async def read_setup_github_metadata(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext | None, Depends(optional_auth)],
) -> JSONResponse:
    stable_id = require_setup_id(stable_id)
    version = require_version(version)
    async with httpx.AsyncClient() as client:
        try:
            result = await service.read_github_metadata(
                db,
                object_kind="setup",
                stable_id=stable_id,
                version=version,
                account_id=None if ctx is None else ctx.account_id,
                client=client,
            )
        except service.CatalogNotFound as exc:
            raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    return _resource(request, result)


@router.get("/catalog/setups/{stable_id}/versions/{version}/context-budget", response_model=None)
async def read_setup_context_budget(
    request: Request,
    stable_id: str,
    version: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext | None, Depends(optional_auth)],
    estimator_profile: Annotated[str, Query()] = "ai-stp:utf8-bytes/1",
) -> JSONResponse:
    stable_id = require_setup_id(stable_id)
    version = require_version(version)
    try:
        query = SetupContextBudgetQuery(estimator_profile=estimator_profile)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "request validation failed",
            details={"fields": ",".join(str(error["loc"]) for error in exc.errors())},
        ) from exc
    try:
        result = await setup_context_budget(
            db,
            account_id=None if ctx is None else ctx.account_id,
            stable_id=stable_id,
            version=version,
            store=_store(request),
            estimator_profile=query.estimator_profile,
        )
    except SelectionNotFound as exc:
        raise ApiError(ErrorCategory.NOT_FOUND, "catalog object not found") from exc
    except SelectionInvalid as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    return _resource(request, result)
