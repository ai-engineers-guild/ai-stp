"""Account and catalog-line public identity (SPEC-059, ADR-0152)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.first_party import OWNER_ID as OFFICIAL_ACCOUNT_ID
from ai_stp_foundation.identity import (
    OFFICIAL_DISPLAY_NAME,
    OFFICIAL_HANDLE,
    IdentityNormalizationError,
    canonical_slug,
    handle_from_account_id,
    is_protected_official_display,
    is_protected_official_handle,
    normalize_display_key,
    normalize_handle,
    submitted_display_name,
)
from ai_stp_platform.models import Account, CatalogIdentity, CatalogIdentityLocale


class IdentityError(Exception):
    """Typed identity allocation or rename failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _conflict_from_integrity(exc: IntegrityError) -> IdentityError:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint = str(getattr(diag, "constraint_name", "") or orig or "")
    if "handle" in constraint:
        return IdentityError(
            "AI_STP_HANDLE_CONFLICT", "the normalized public handle is already assigned"
        )
    if "display_name" in constraint and "locale" in constraint:
        return IdentityError(
            "AI_STP_LOCALIZED_NAME_CONFLICT",
            "the normalized localized component display name is already assigned",
        )
    if "display_name" in constraint:
        return IdentityError(
            "AI_STP_ACCOUNT_DISPLAY_NAME_CONFLICT",
            "the normalized account display name is already assigned",
        )
    if "canonical" in constraint:
        return IdentityError(
            "AI_STP_CANONICAL_NAME_CONFLICT",
            "the normalized canonical component name is already assigned",
        )
    if "locale_name" in constraint:
        return IdentityError(
            "AI_STP_LOCALIZED_NAME_CONFLICT",
            "the normalized localized component display name is already assigned",
        )
    return IdentityError(
        "AI_STP_HANDLE_CONFLICT", "the normalized public identity is already assigned"
    )


def _apply_account_names(account: Account, handle: str, display_name: str) -> None:
    account.handle = handle
    account.handle_normalized = handle
    account.display_name = display_name
    account.display_name_normalized = normalize_display_key(display_name)


async def allocate_account_identity(
    session: AsyncSession,
    account: Account,
    *,
    handle: str | None = None,
    display_name: str | None = None,
) -> Account:
    """Assign unique handle and display name to a new or unnamed account."""
    if account.id == OFFICIAL_ACCOUNT_ID:
        _apply_account_names(account, OFFICIAL_HANDLE, OFFICIAL_DISPLAY_NAME)
        await session.flush()
        return account
    try:
        assigned_handle = normalize_handle(handle) if handle else handle_from_account_id(account.id)
        assigned_display = (
            submitted_display_name(display_name)
            if display_name
            else submitted_display_name(f"User {assigned_handle.removeprefix('user-')[:16]}")
        )
    except IdentityNormalizationError as exc:
        raise IdentityError("AI_STP_VALIDATION_ERROR", str(exc)) from exc
    if is_protected_official_handle(assigned_handle) or is_protected_official_display(
        assigned_display
    ):
        raise IdentityError("AI_STP_PERMISSION_DENIED", "the Official identity is reserved")
    _apply_account_names(account, assigned_handle, assigned_display)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict_from_integrity(exc) from exc
    return account


async def set_account_identity(
    session: AsyncSession,
    account_id: str,
    *,
    handle: str,
    display_name: str,
) -> Account:
    """Replace the public handle and display name of an ordinary account."""
    account = await session.get(Account, account_id)
    if account is None:
        raise IdentityError("AI_STP_NOT_FOUND", "account not found")
    if account.id == OFFICIAL_ACCOUNT_ID:
        raise IdentityError("AI_STP_PERMISSION_DENIED", "the Official identity cannot be renamed")
    try:
        assigned_handle = normalize_handle(handle)
        assigned_display = submitted_display_name(display_name)
    except IdentityNormalizationError as exc:
        raise IdentityError("AI_STP_VALIDATION_ERROR", str(exc)) from exc
    if is_protected_official_handle(assigned_handle) or is_protected_official_display(
        assigned_display
    ):
        raise IdentityError("AI_STP_PERMISSION_DENIED", "the Official identity is reserved")
    _apply_account_names(account, assigned_handle, assigned_display)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict_from_integrity(exc) from exc
    return account


async def current_catalog_identity(session: AsyncSession, stable_id: str) -> CatalogIdentity | None:
    return await session.get(CatalogIdentity, stable_id)


async def locale_names(session: AsyncSession, stable_id: str) -> dict[str, CatalogIdentityLocale]:
    rows = (
        await session.scalars(
            select(CatalogIdentityLocale).where(CatalogIdentityLocale.stable_id == stable_id)
        )
    ).all()
    return {row.locale: row for row in rows}


async def ensure_catalog_identity(
    session: AsyncSession,
    *,
    stable_id: str,
    owner_account_id: str,
    canonical_name: str,
    display_name_en: str,
    display_name_ru: str,
    expected_ownership_revision_id: str | None = None,
) -> CatalogIdentity:
    """Create the catalog line on first publication or fence an existing owner."""
    try:
        slug = canonical_slug(canonical_name)
        en_name = submitted_display_name(display_name_en)
        ru_name = submitted_display_name(display_name_ru)
    except IdentityNormalizationError as exc:
        raise IdentityError("AI_STP_VALIDATION_ERROR", str(exc)) from exc
    existing = await session.get(CatalogIdentity, stable_id)
    if existing is None:
        identity = CatalogIdentity(
            stable_id=stable_id,
            owner_account_id=owner_account_id,
            canonical_name=slug,
            canonical_name_normalized=slug,
            ownership_revision_id="",
        )
        session.add(identity)
        session.add(
            CatalogIdentityLocale(
                stable_id=stable_id,
                locale="en",
                display_name=en_name,
                display_name_normalized=normalize_display_key(en_name),
            )
        )
        session.add(
            CatalogIdentityLocale(
                stable_id=stable_id,
                locale="ru",
                display_name=ru_name,
                display_name_normalized=normalize_display_key(ru_name),
            )
        )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise _conflict_from_integrity(exc) from exc
        return identity
    if getattr(existing, "owner_account_id", owner_account_id) != owner_account_id:
        raise IdentityError(
            "AI_STP_FOREIGN_LINE_OWNERSHIP", "the catalog line is owned by another account"
        )
    expected = expected_ownership_revision_id
    if expected is not None and expected != getattr(existing, "ownership_revision_id", ""):
        raise IdentityError(
            "AI_STP_STALE_OWNERSHIP_REVISION",
            "the expected catalog-line ownership revision is no longer current",
        )
    return existing


async def assert_publication_owner(
    session: AsyncSession,
    *,
    stable_id: str,
    actor_account_id: str,
    expected_ownership_revision_id: str | None,
    object_kind: str,
) -> CatalogIdentity | None:
    """Fence a later version of an owned component line."""
    if object_kind != "component":
        return None
    identity = await session.scalar(
        select(CatalogIdentity).where(CatalogIdentity.stable_id == stable_id).with_for_update()
    )
    if identity is None:
        return None
    if getattr(identity, "owner_account_id", actor_account_id) != actor_account_id:
        raise IdentityError(
            "AI_STP_FOREIGN_LINE_OWNERSHIP", "the catalog line is owned by another account"
        )
    if expected_ownership_revision_id is not None and expected_ownership_revision_id != getattr(
        identity, "ownership_revision_id", ""
    ):
        raise IdentityError(
            "AI_STP_STALE_OWNERSHIP_REVISION",
            "the expected catalog-line ownership revision is no longer current",
        )
    return identity


@dataclass(frozen=True)
class IdentityConflict:
    kind: str
    key: str
    ids: str


async def collect_identity_conflicts(session: AsyncSession) -> list[IdentityConflict]:
    """Deterministic inventory of normalized collisions (REQ-5908)."""
    conflicts: list[IdentityConflict] = []
    from ai_stp_platform.models import CatalogMetadata

    mixed_rows = (
        await session.execute(
            select(CatalogMetadata.stable_id, CatalogMetadata.owner_account_id).where(
                CatalogMetadata.object_kind == "component"
            )
        )
    ).all()
    owners: dict[str, set[str]] = {}
    for stable_id, owner in mixed_rows:
        owners.setdefault(str(stable_id), set()).add(str(owner))
    for stable_id, present in sorted(owners.items()):
        if len(present) > 1:
            conflicts.append(IdentityConflict("mixed_owner", stable_id, ",".join(sorted(present))))
    handle_rows = (await session.scalars(select(Account))).all()
    handles: dict[str, list[str]] = {}
    displays: dict[str, list[str]] = {}
    for account in handle_rows:
        if account.handle_normalized:
            handles.setdefault(account.handle_normalized, []).append(account.id)
        if account.display_name_normalized:
            displays.setdefault(account.display_name_normalized, []).append(account.id)
    for key, ids in sorted(handles.items()):
        if len(ids) > 1:
            conflicts.append(IdentityConflict("handle", key, ",".join(sorted(ids))))
    for key, ids in sorted(displays.items()):
        if len(ids) > 1:
            conflicts.append(IdentityConflict("account_display", key, ",".join(sorted(ids))))
    return conflicts
