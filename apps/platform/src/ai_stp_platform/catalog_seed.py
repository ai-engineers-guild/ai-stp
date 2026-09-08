"""Seed the canonical development corpus without inventing identities or bytes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts import first_party
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.identity import canonical_slug
from ai_stp_foundation.timestamps import parse_timestamp
from ai_stp_passports.envelope import verify_revision_id
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport, adaptation_for
from ai_stp_platform.catalog_search import upsert_catalog_search_projection
from ai_stp_platform.identity import allocate_account_identity, ensure_catalog_identity
from ai_stp_platform.models import (
    Account,
    AccountAuthorVerification,
    CatalogMetadata,
    ObjectLocation,
)
from ai_stp_platform.storage.object_store import ImmutableObjectStore


@dataclass(frozen=True)
class SeedResult:
    """Counts for one seed run, with immutable reuse separate from creation."""

    created_accounts: int
    created_versions: int
    reused_versions: int
    artifacts_written: int


class CorpusSeedConflict(ValueError):
    """The proposed corpus conflicts with immutable bytes or existing ownership."""


def _checked_corpus(
    objects: Sequence[FirstPartyVersion],
) -> dict[tuple[str, str, str], tuple[FirstPartyVersion, dict[str, Any]]]:
    checked: dict[tuple[str, str, str], tuple[FirstPartyVersion, dict[str, Any]]] = {}
    for item in objects:
        document = item.passport.model_dump(mode="json")
        model = ComponentVersionPassport if item.kind == "component" else SetupVersionPassport
        passport = model.model_validate(document)
        if passport.owner_id != first_party.OWNER_ID or passport.visibility != "public":
            raise CorpusSeedConflict("the canonical corpus must retain its public owner")
        if (
            not verify_revision_id(passport)
            or digest_canonical(first_party.PASSPORT_DIGEST_DOMAIN, cast(JsonValue, document))
            != item.passport_digest
        ):
            raise CorpusSeedConflict("the corpus passport seal or digest does not match")
        if (
            digest_bytes(first_party.ARTIFACT_DIGEST_DOMAIN, item.artifact)
            != passport.artifact.digest
            or len(item.artifact) != passport.artifact.size_bytes
        ):
            raise CorpusSeedConflict("the corpus artifact bytes do not match the passport")
        key = (item.kind, passport.stable_id, passport.version)
        if key in checked and checked[key][0] != item:
            raise CorpusSeedConflict("the corpus repeats an identity with different bytes")
        checked[key] = (item, document)
    for item, _document in checked.values():
        if not isinstance(item.passport, SetupVersionPassport):
            continue
        for reference in item.passport.components:
            component = checked.get(("component", reference.stable_id, reference.version))
            if component is None or component[0].passport_digest != reference.passport_digest:
                raise CorpusSeedConflict("the corpus setup does not have its exact component graph")
            passport = component[0].passport
            if not isinstance(passport, ComponentVersionPassport):
                raise CorpusSeedConflict("a setup member is not a component")
            adaptation_for(passport, item.passport.harness_id)
    return checked


async def load_first_party_seed(
    session: AsyncSession,
    *,
    store: ImmutableObjectStore | None,
    objects: Sequence[FirstPartyVersion] | None = None,
) -> SeedResult:
    """Load exact canonical objects inside the caller's transaction.

    The caller owns the development-environment gate. Production uses the
    ordinary publication pipeline. Seeding establishes no component assessment.
    """
    if store is None:
        raise CorpusSeedConflict("canonical seeding requires configured artifact storage")
    checked = _checked_corpus(first_party.versions() if objects is None else objects)
    rows = (
        await session.scalars(
            select(CatalogMetadata).where(
                CatalogMetadata.stable_id.in_({key[1] for key in checked})
            )
        )
    ).all()
    existing = {(row.object_kind, row.stable_id, row.version): row for row in rows}
    for key, (item, document) in checked.items():
        row = existing.get(key)
        if row is not None and (
            row.owner_account_id != item.passport.owner_id
            or row.passport_digest != item.passport_digest
            or row.current_revision_id != item.passport.revision_id
            or row.passport_document != document
        ):
            raise CorpusSeedConflict("an existing immutable corpus version or owner differs")

    owner = await session.get(Account, first_party.OWNER_ID)
    created_accounts = int(owner is None)
    if owner is None:
        owner = Account(id=first_party.OWNER_ID)
        session.add(owner)
        await allocate_account_identity(session, owner)
    verification = await session.get(AccountAuthorVerification, first_party.OWNER_ID)
    created = artifacts_written = 0
    for key, (item, document) in checked.items():
        passport = item.passport
        if item.kind == "component":
            await ensure_catalog_identity(
                session,
                stable_id=passport.stable_id,
                owner_account_id=passport.owner_id,
                canonical_name=canonical_slug(passport.name),
                display_name_en=passport.name,
                display_name_ru=passport.name,
            )
        stored = await store.put_immutable(
            item.artifact,
            expected_digest=passport.artifact.digest,
            expected_size=passport.artifact.size_bytes,
            owner_account_id=passport.owner_id,
        )
        retained = await store.read_verified(
            object_key=stored.key,
            expected_digest=stored.digest,
            expected_size=stored.size_bytes,
        )
        if retained != item.artifact:
            raise CorpusSeedConflict("the object store did not retain the exact corpus artifact")
        artifacts_written += int(stored.created)
        row = existing.get(key)
        if row is None:
            row = CatalogMetadata(
                owner_account_id=passport.owner_id,
                object_kind=item.kind,
                stable_id=passport.stable_id,
                version=passport.version,
                current_revision_id=passport.revision_id,
                visibility=passport.visibility,
                lifecycle_state="active",
                name=passport.name,
                published_at=parse_timestamp(passport.created_at),
                updated_at=parse_timestamp(passport.created_at),
                trust_lane="experimental",
                author_verified=bool(verification and verification.verified),
                component_verified=False,
                passport_digest=item.passport_digest,
                passport_document=document,
            )
            session.add(row)
            await session.flush()
            created += 1
        location = await session.scalar(
            select(ObjectLocation).where(
                ObjectLocation.catalog_metadata_id == row.id,
                ObjectLocation.purpose == "artifact",
            )
        )
        if location is None:
            session.add(
                ObjectLocation(
                    catalog_metadata_id=row.id,
                    purpose="artifact",
                    bucket=stored.bucket,
                    owner_account_id=passport.owner_id,
                    object_key=stored.key,
                    digest=stored.digest,
                    content_id=stored.content_id,
                    size_bytes=stored.size_bytes,
                )
            )
        elif (
            location.object_key != stored.key
            or location.bucket not in {None, stored.bucket}
            or location.owner_account_id not in {None, passport.owner_id}
            or location.digest != stored.digest
            or location.content_id != stored.content_id
            or location.size_bytes != stored.size_bytes
        ):
            raise CorpusSeedConflict("the existing corpus artifact location differs")
        await session.flush()
        await upsert_catalog_search_projection(
            session, object_kind=item.kind, stable_id=passport.stable_id
        )
    return SeedResult(created_accounts, created, len(checked) - created, artifacts_written)
