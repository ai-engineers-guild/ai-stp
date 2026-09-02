"""Catalog projection honesty and latest_* mapping (REQ-2103/2104/2111)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_stp_contracts.catalog import CatalogTrust
from ai_stp_foundation.canonical import canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.catalog_projection import (
    PASSPORT_DIGEST_DOMAIN,
    component_detail,
    component_summary,
    component_version_response,
    passport_matches_filters,
    project_component_checks,
    project_trust,
    setup_detail,
    verify_passport_integrity,
)
from ai_stp_platform.catalog_read import CatalogIntegrityError, PublicVersionRow
from ai_stp_platform.catalog_seed import seed_corpus
from ai_stp_platform.models import CatalogMetadata

pytestmark = pytest.mark.platform

_PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)


def _row_from_seed() -> PublicVersionRow:
    _kind, passport, _published, digest = next(c for c in seed_corpus() if c[0] == "component")
    meta = CatalogMetadata(
        id=1,
        owner_account_id=str(passport["owner_id"]),
        object_kind="component",
        stable_id=str(passport["stable_id"]),
        version=str(passport["version"]),
        current_revision_id=str(passport["revision_id"]),
        visibility="public",
        lifecycle_state="active",
        published_at=datetime(2026, 8, 5, tzinfo=UTC),
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        passport_digest=digest,
        passport_document=passport,
    )
    return PublicVersionRow(
        metadata=meta,
        passport=passport,
        passport_digest=digest,
        published_at=meta.published_at,  # type: ignore[arg-type]
        trust_lane="experimental",
        author_verified=False,
        component_verified=False,
        lifecycle="active",
        stable_id=meta.stable_id,
        version=str(meta.version),
        object_kind="component",
    )


def test_component_summary_projects_every_named_harness() -> None:
    row = _row_from_seed()
    primary = str(row.passport["harness_id"])
    extra = "codex" if primary != "codex" else "claude-code"
    variant = _row_with_passport_variant(
        harness_ids=[primary, extra],
        supported_os=["linux", "macos", "windows"],
    )
    summary = component_summary(variant)
    assert summary.latest_harness_id == primary
    assert list(summary.latest_harness_ids) == [primary, extra]
    passport = ComponentVersionPassport.model_validate(variant.passport)
    assert list(passport.supported_os) == ["linux", "macos", "windows"]


def test_latest_fields_map_from_passport() -> None:
    row = _row_from_seed()
    summary = component_summary(row)
    assert summary.latest_name == row.passport["name"]
    assert summary.latest_description == row.passport["description"]
    assert summary.latest_harness_id == row.passport["harness_id"]
    assert summary.latest_component_type == row.passport["component_type"]
    assert summary.latest_projection_kind == row.passport["projection_kind"]
    assert list(summary.latest_tags) == list(row.passport["tags"])
    assert summary.latest_version == row.passport["version"]


def test_requirements_count_includes_dependencies_and_capabilities() -> None:
    row = _row_with_passport_variant(
        requires_components=[
            {
                "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                "version": "1.0",
                "passport_digest": _PLACEHOLDER_DIGEST,
                "variant_id": None,
            }
        ],
        requires_capabilities=["project.language.python"],
        requires_credentials=True,
    )
    summary = component_summary(row)
    assert summary.latest_requirements_count == 3
    assert summary.latest_requires_credentials is True


def test_authoritative_requires_both_axes() -> None:
    with pytest.raises(ValidationError):
        CatalogTrust(
            trust_lane="authoritative",
            author_verified=True,
            component_verified=False,
        )


def test_projection_never_claims_verified_without_evidence() -> None:
    row = _row_from_seed()
    trust = project_trust(row)
    assert trust.component_verified is False
    assert trust.author_verified is False
    assert trust.trust_lane == "experimental"


def test_project_trust_downgrades_inconsistent_authoritative() -> None:
    row = _row_from_seed()
    # Stored state claims authoritative without both axes — honesty wins.
    inconsistent = PublicVersionRow(
        metadata=row.metadata,
        passport=row.passport,
        passport_digest=row.passport_digest,
        published_at=row.published_at,
        trust_lane="authoritative",
        author_verified=True,
        component_verified=False,
        lifecycle=row.lifecycle,
        stable_id=row.stable_id,
        version=row.version,
        object_kind=row.object_kind,
    )
    trust = project_trust(inconsistent)
    assert trust.trust_lane == "experimental"


def test_passport_matches_filters_harness_tags_and_type() -> None:
    row = _row_from_seed()
    passport = dict(row.passport)
    assert passport_matches_filters(
        passport,
        q=None,
        tags=list(passport.get("tags") or []),
        harness_id=str(passport["harness_id"]),
        component_type=str(passport["component_type"]),
    )
    assert not passport_matches_filters(
        passport,
        q=None,
        tags=[],
        harness_id="other-harness",
        component_type=None,
    )
    assert not passport_matches_filters(
        passport,
        q=None,
        tags=[],
        harness_id=None,
        component_type="mcp",
    )
    assert not passport_matches_filters(
        passport,
        q=None,
        tags=["not-a-real-tag"],
        harness_id=None,
        component_type=None,
    )


def test_passport_matches_filters_q_and_pytest_probe() -> None:
    row = _row_from_seed()
    passport = dict(row.passport)
    assert passport_matches_filters(
        passport,
        q=str(passport["name"])[:4],
        tags=[],
        harness_id=None,
        component_type=None,
    )
    assert not passport_matches_filters(
        passport,
        q="zzzz-no-match",
        tags=[],
        harness_id=None,
        component_type=None,
    )
    # Fixture corpus probe: q=pytest + fixture-component name.
    passport["name"] = "fixture-component"
    assert passport_matches_filters(
        passport,
        q="pytest",
        tags=[],
        harness_id=None,
        component_type=None,
    )


def test_component_detail_and_version_response_from_seed() -> None:
    row = _row_from_seed()
    # Seed corpus includes multiple component versions; use one for detail.
    components = [
        PublicVersionRow(
            metadata=row.metadata,
            passport=passport,
            passport_digest=digest,
            published_at=row.published_at,
            trust_lane="experimental",
            author_verified=False,
            component_verified=False,
            lifecycle="active",
            stable_id=str(passport["stable_id"]),
            version=str(passport["version"]),
            object_kind="component",
        )
        for kind, passport, _published, digest in seed_corpus()
        if kind == "component" and str(passport["stable_id"]) == row.stable_id
    ]
    detail = component_detail(components)
    assert detail.summary.stable_id == row.stable_id
    assert len(detail.versions) == len(components)
    with pytest.raises(CatalogIntegrityError):
        component_detail([])
    version = component_version_response(row)
    assert version.passport.stable_id == row.stable_id


def test_setup_detail_uses_setup_passports_for_version_entries() -> None:
    rows: list[PublicVersionRow] = []
    for kind, passport, _published, digest in seed_corpus():
        if kind != "setup":
            continue
        meta = CatalogMetadata(
            id=2,
            owner_account_id=str(passport["owner_id"]),
            object_kind="setup",
            stable_id=str(passport["stable_id"]),
            version=str(passport["version"]),
            current_revision_id=str(passport["revision_id"]),
            visibility="public",
            lifecycle_state="active",
            published_at=datetime(2026, 8, 5, tzinfo=UTC),
            trust_lane="experimental",
            passport_digest=digest,
            passport_document=passport,
        )
        rows.append(
            PublicVersionRow(
                metadata=meta,
                passport=passport,
                passport_digest=digest,
                published_at=meta.published_at,  # type: ignore[arg-type]
                trust_lane="experimental",
                author_verified=False,
                component_verified=False,
                lifecycle="active",
                stable_id=meta.stable_id,
                version=str(meta.version),
                object_kind="setup",
            )
        )

    detail = setup_detail(rows)
    assert detail.summary.latest_harness_id == "claude-code"
    assert detail.versions[0].support.tier == "primary"


def test_verify_passport_integrity_rejects_digest_mismatch() -> None:
    row = _row_from_seed()
    bad = PublicVersionRow(
        metadata=row.metadata,
        passport=row.passport,
        passport_digest="sha256:" + ("1" * 64),
        published_at=row.published_at,
        trust_lane=row.trust_lane,
        author_verified=row.author_verified,
        component_verified=row.component_verified,
        lifecycle=row.lifecycle,
        stable_id=row.stable_id,
        version=row.version,
        object_kind=row.object_kind,
    )
    with pytest.raises(CatalogIntegrityError, match="digest"):
        verify_passport_integrity(bad)


def _row_with_passport_variant(**changes: object) -> PublicVersionRow:
    row = _row_from_seed()
    passport = dict(row.passport)
    passport.update(changes)
    passport["revision_id"] = derive_revision_id(passport)
    return PublicVersionRow(
        metadata=row.metadata,
        passport=passport,
        passport_digest=_PLACEHOLDER_DIGEST,
        published_at=row.published_at,
        trust_lane=row.trust_lane,
        author_verified=row.author_verified,
        component_verified=row.component_verified,
        lifecycle=row.lifecycle,
        stable_id=row.stable_id,
        version=row.version,
        object_kind=row.object_kind,
    )


def test_verify_passport_integrity_rejects_revision_seal_mismatch() -> None:
    row = _row_from_seed()
    bad = PublicVersionRow(
        metadata=row.metadata,
        passport=dict(row.passport) | {"revision_id": "revision_" + ("0" * 64)},
        passport_digest=_PLACEHOLDER_DIGEST,
        published_at=row.published_at,
        trust_lane=row.trust_lane,
        author_verified=row.author_verified,
        component_verified=row.component_verified,
        lifecycle=row.lifecycle,
        stable_id=row.stable_id,
        version=row.version,
        object_kind=row.object_kind,
    )

    with pytest.raises(CatalogIntegrityError, match="revision seal"):
        verify_passport_integrity(bad)


def test_verify_passport_integrity_rejects_private_passport() -> None:
    with pytest.raises(CatalogIntegrityError, match="not public"):
        verify_passport_integrity(_row_with_passport_variant(visibility="private"))


def test_verify_passport_integrity_rejects_identity_mismatch() -> None:
    row = _row_with_passport_variant(stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7X")

    with pytest.raises(CatalogIntegrityError, match="identity"):
        verify_passport_integrity(row)


def test_verify_passport_integrity_accepts_stored_bytes_without_later_defaults() -> None:
    """A published component may omit fields the model later grew with defaults.

    Prod 2026-08-24: every public component failed the revision seal because
    `model_dump` injected empty `harness_ids` and `supported_os` that were not
    in the stored document. The digest over the stored bytes still matched.
    """
    row = _row_from_seed()
    passport = dict(row.passport)
    passport.pop("harness_ids", None)
    passport.pop("supported_os", None)
    passport["revision_id"] = derive_revision_id(passport)
    stored = PublicVersionRow(
        metadata=row.metadata,
        passport=passport,
        passport_digest=_PLACEHOLDER_DIGEST,
        published_at=row.published_at,
        trust_lane=row.trust_lane,
        author_verified=row.author_verified,
        component_verified=row.component_verified,
        lifecycle=row.lifecycle,
        stable_id=row.stable_id,
        version=row.version,
        object_kind=row.object_kind,
    )
    verify_passport_integrity(stored)
    summary = component_summary(stored)
    assert summary.stable_id == row.stable_id
    assert list(summary.latest_harness_ids) == [row.passport["harness_id"]]


def test_version_response_wires_stored_passport_not_model_defaults() -> None:
    """GET must emit the published document, or historical digests never match.

    Prod 2026-08-25: Claude 1.0 `passport_digest` hashed stored bytes that
    omitted later default fields, while the response dumped the validated model.
    """
    row = _row_from_seed()
    passport = dict(row.passport)
    passport.pop("harness_ids", None)
    passport.pop("supported_os", None)
    passport["revision_id"] = derive_revision_id(passport)
    digest = digest_bytes(PASSPORT_DIGEST_DOMAIN, canonize(passport))
    stored = PublicVersionRow(
        metadata=row.metadata,
        passport=passport,
        passport_digest=digest,
        published_at=row.published_at,
        trust_lane=row.trust_lane,
        author_verified=row.author_verified,
        component_verified=row.component_verified,
        lifecycle=row.lifecycle,
        stable_id=row.stable_id,
        version=row.version,
        object_kind=row.object_kind,
    )
    payload = component_version_response(stored).model_dump(mode="json")
    assert payload["passport"] == passport
    assert "harness_ids" not in payload["passport"]
    assert payload["passport_digest"] == digest
    dumped = ComponentVersionPassport.model_validate(passport).model_dump(mode="json")
    assert "harness_ids" in dumped
    assert dumped != payload["passport"]


def test_verify_passport_integrity_rejects_unparsable_passport() -> None:
    """A structurally broken passport is an integrity failure, not a crash.

    The placeholder digest is the documented fixture path that skips the digest
    comparison, so this lands on schema validation — the branch that used to
    raise ValidationError straight past every caller's except clause.
    """
    row = _row_from_seed()
    broken = dict(row.passport)
    del broken["harness_id"]
    bad = PublicVersionRow(
        metadata=row.metadata,
        passport=broken,
        passport_digest=_PLACEHOLDER_DIGEST,
        published_at=row.published_at,
        trust_lane=row.trust_lane,
        author_verified=row.author_verified,
        component_verified=row.component_verified,
        lifecycle=row.lifecycle,
        stable_id=row.stable_id,
        version=row.version,
        object_kind=row.object_kind,
    )

    with pytest.raises(CatalogIntegrityError, match="schema"):
        verify_passport_integrity(bad)
    # The point of the conversion: no caller has to know about pydantic.
    try:
        verify_passport_integrity(bad)
    except ValidationError:  # pragma: no cover - fails the assertion below
        pytest.fail("ValidationError escaped verify_passport_integrity")
    except CatalogIntegrityError:
        pass


def test_a_card_carries_an_excerpt_and_never_the_whole_description() -> None:
    """The bound and the only data that met it agreed by accident, until today.

    `latest_description` is `DescriptionExcerpt` — `max_length=240` — and both
    summaries document themselves as carrying a deterministic plain-text
    excerpt. The projection handed the raw description through, and nothing
    noticed for as long as no published description exceeded 240 characters.

    Importing all four published postures ended that in one step: `full-auto`
    descriptions are load-bearing safety context running to 3312 characters.
    Eleven setups exceeded the bound, every one failed `SetupSummary`
    validation, and the deployed catalogue answered `AI_STP_INTERNAL` on the
    detail route and on every listing page that reached them.
    """
    from ai_stp_passports.markdown import MAX_EXCERPT_CODEPOINTS

    long_description = " ".join(f"word{index}" for index in range(400))
    assert len(long_description) > MAX_EXCERPT_CODEPOINTS * 4

    row = _row_with_passport_variant(description=long_description)
    summary = component_summary(row)

    assert len(summary.latest_description) <= MAX_EXCERPT_CODEPOINTS
    assert summary.latest_description.endswith("…")
    # The excerpt is the head of the text, not an arbitrary slice of Markdown.
    assert summary.latest_description.startswith("word0 word1 ")


def _row_with_member_checks() -> PublicVersionRow:
    """A row whose stored summary carries per-member checks, as a setup's does."""
    row = _row_from_seed()
    row.metadata.checks_summary = {  # pyright: ignore[reportAttributeAccessIssue]
        "status": "empty",
        "components": [
            {
                "stable_id": "component_01J0000000000000000000000A",
                "name": "a member",
                "version": "1.0",
                "embedded": False,
            }
        ],
    }
    return row


def test_a_card_does_not_carry_the_per_member_checks_only_a_detail_reads() -> None:
    """The field that broke every released client leaves the search projection.

    One surface reads `latest_checks.components` — the setup detail page — and
    the card carried it anyway. On 2026-09-02 the deployed platform answered
    `registry search` with it and the released `0.0.14` and `0.0.15` clients
    refused the whole body, because their `SafetyChecksSummary` forbade extras.
    The models now allow additions, as their schema always promised, but bytes
    already installed cannot be changed, so the card stops sending what nothing
    on it reads. The detail keeps it, and the feature is unaffected.
    """
    row = _row_with_member_checks()
    card = component_summary(row)
    assert card.latest_checks is not None
    # The name itself must be absent, not merely empty: a released client
    # refused the card over the key, whatever its value.
    assert "components" not in card.latest_checks.model_dump()
    assert [item.stable_id for item in project_component_checks(row)] == [
        "component_01J0000000000000000000000A"
    ]
