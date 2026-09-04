"""Anonymous public catalog payloads (issue #71, SPEC-005, SPEC-006, ADR-0016)."""

import json
import pathlib
import typing

import pytest
from pydantic import ValidationError

from ai_stp_contracts.catalog import (
    USAGE_METRICS_ENABLED_BY_DEFAULT,
    CatalogSupport,
    CatalogSupportEvidence,
    CatalogTrust,
    CatalogTrustLane,
    CatalogUsageMetrics,
    ComponentDetail,
    ComponentListResponse,
    ComponentSearchRequest,
    ComponentSummary,
    ComponentVersionResponse,
    PublicLifecycle,
    SetupListResponse,
    SetupSearchRequest,
    SetupSummary,
    SetupVersionResponse,
    SupportOperatingSystem,
    VersionListEntry,
)
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, PageInfo
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport

GOLDEN = pathlib.Path(__file__).parents[1] / "golden" / "passports"

AUTHORITATIVE = CatalogTrust(
    trust_lane="authoritative", author_verified=True, component_verified=True
)
EXPERIMENTAL = CatalogTrust(
    trust_lane="experimental", author_verified=False, component_verified=False
)

#: Facts a card carries about its latest version that are **not** in the
#: passport: lifecycle and trust are mutable platform state kept outside the
#: hashed bytes (SPEC-005, SPEC-007), and publication time is the platform's
#: record of the event. The set is closed so a card cannot grow an invented
#: field under cover of the `latest_` prefix.
# Platform facts of a published version that are not passport fields:
# lifecycle/trust/publication time, provider support evidence (SPEC-033),
# and safety-scan summary (#270 checks percent / pending / audit list).
PLATFORM_VERSION_FACTS = {
    "lifecycle",
    "trust",
    "published_at",
    "support",
    "checks",
    "requirements_count",
    "harness_ids",
    "harness_id",
    "projection_kind",
}

SUPPORT_MISSING = CatalogSupport(
    schema_version=1,
    tier="primary",
    state="missing",
    evidence=[],
)

# These values belong to the catalog object/aggregate rather than to one
# immutable passport version.  Keep this list explicit so adding another
# unprefixed descriptive field still fails the ownership test below.
OBJECT_IDENTITY = {
    "schema_version",
    "stable_id",
    "publisher_id",
    "likes_count",
    "github_stars",
    "updated_at",
    "usage_metrics",
}


def page_info() -> PageInfo:
    return PageInfo(next_cursor=None, page_size=PAGE_SIZE_DEFAULT)


def published_passport(name: str, **overrides: object) -> dict[str, object]:
    value = json.loads((GOLDEN / name).read_text(encoding="utf-8"))["value"]
    return dict(value) | {"visibility": "public"} | overrides


def component_summary(**overrides: object) -> ComponentSummary:
    fields: dict[str, object] = {
        "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "publisher_id": "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "likes_count": 0,
        "updated_at": "2026-08-05T00:00:00.000Z",
        "latest_version": "1.2",
        "latest_name": "pytest-runner",
        "latest_description": "Runs pytest and parses the report.",
        "latest_harness_id": "claude-code",
        "latest_component_type": "skill",
        "latest_projection_kind": "native_files",
        "latest_tags": ["python", "tests"],
        "latest_lifecycle": "active",
        "latest_trust": AUTHORITATIVE,
        "latest_published_at": "2026-08-05T00:00:00.000Z",
        "latest_support": SUPPORT_MISSING,
    }
    return ComponentSummary.model_validate(fields | overrides)


def version_response(**overrides: object) -> ComponentVersionResponse:
    fields: dict[str, object] = {
        "passport": published_passport("component-version.json"),
        "passport_digest": "sha256:" + "0" * 64,
        "lifecycle": "active",
        "trust": AUTHORITATIVE,
        "support": SUPPORT_MISSING,
        "published_at": "2026-08-05T00:00:00.000Z",
    }
    return ComponentVersionResponse.model_validate(fields | overrides)


def literal_values(alias: object) -> set[str]:
    return set(typing.get_args(alias.__value__))  # type: ignore[attr-defined]


def test_every_card_field_is_object_identity_or_a_latest_version_fact() -> None:
    # The naming rule is mechanical so it can be verified rather than
    # remembered: unprefixed means the object, `latest_` means the latest
    # version, and a `latest_` field must correspond to something that really
    # exists on that version.
    for card, passport in (
        (ComponentSummary, ComponentVersionPassport),
        (SetupSummary, SetupVersionPassport),
    ):
        for name in card.model_fields:
            if name in OBJECT_IDENTITY:
                continue
            assert name.startswith("latest_"), f"{card.__name__}.{name} claims to be object-level"
            bare = name.removeprefix("latest_")
            assert bare in passport.model_fields or bare in PLATFORM_VERSION_FACTS, (
                f"{card.__name__}.{name} matches no field of {passport.__name__}"
            )


def test_a_card_carries_no_object_level_descriptive_field() -> None:
    # There is no object-level passport (ADR-0012), so an unprefixed `name` or
    # `tags` would be a fact with no owner.
    for card in (ComponentSummary, SetupSummary):
        assert {"name", "description", "tags", "harness_id"}.isdisjoint(card.model_fields)


def test_hidden_is_not_representable_on_the_public_wire() -> None:
    assert literal_values(PublicLifecycle) == {"active", "deprecated", "blocked"}
    with pytest.raises(ValidationError):
        component_summary(latest_lifecycle="hidden")


def test_shared_catalog_os_family_is_linux_macos_windows() -> None:
    assert literal_values(SupportOperatingSystem) == {"linux", "macos", "windows"}
    CatalogSupportEvidence.model_validate(
        {
            "check_id": "provider-startup",
            "policy_version": "support-v1",
            "result": "passed",
            "source": "provider_release_evidence",
            "provider_id": "opencode",
            "provider_version": "1.0.0",
            "release_reference": "a" * 40,
            "operating_system": "windows",
            "architecture": "x86_64",
            "mandatory": True,
            "observed_at": "2026-08-07T12:00:00.000Z",
        }
    )
    with pytest.raises(ValidationError):
        CatalogSupportEvidence.model_validate(
            {
                "check_id": "provider-startup",
                "policy_version": "support-v1",
                "result": "passed",
                "source": "provider_release_evidence",
                "provider_id": "opencode",
                "provider_version": "1.0.0",
                "release_reference": "a" * 40,
                "operating_system": "ubuntu",
                "architecture": "x86_64",
                "mandatory": True,
                "observed_at": "2026-08-07T12:00:00.000Z",
            }
        )


def test_deprecated_and_blocked_stay_visible_and_distinct() -> None:
    # SPEC-005: deprecated stays installable with a warning; blocked forbids new
    # installs without disabling an installed target. They are not one state.
    assert component_summary(latest_lifecycle="deprecated").latest_lifecycle == "deprecated"
    assert component_summary(latest_lifecycle="blocked").latest_lifecycle == "blocked"


def test_a_version_list_makes_no_contiguity_claim() -> None:
    # Hiding a version does not free its number, so 1.0 then 1.2 is a legal
    # answer. The contract must be able to express it rather than imply a dense
    # sequence it cannot deliver.
    entries = [
        VersionListEntry(
            version=version,
            passport_digest="sha256:" + "0" * 64,
            lifecycle="active",
            trust=AUTHORITATIVE,
            support=SUPPORT_MISSING,
            published_at="2026-08-05T00:00:00.000Z",
        )
        for version in ("1.0", "1.2")
    ]
    detail = ComponentDetail(summary=component_summary(), versions=entries)
    assert [entry.version for entry in detail.versions] == ["1.0", "1.2"]
    assert detail.country_codes == []
    assert detail.services == []


def test_local_lane_is_not_a_catalog_assertion() -> None:
    assert literal_values(CatalogTrustLane) == {"authoritative", "experimental"}
    with pytest.raises(ValidationError):
        CatalogTrust(
            trust_lane="local_owner_or_pinned",  # type: ignore[arg-type]
            author_verified=True,
            component_verified=True,
        )


def test_authoritative_cannot_be_claimed_without_both_verifications() -> None:
    for author, component in ((False, False), (True, False), (False, True)):
        with pytest.raises(ValidationError):
            CatalogTrust(
                trust_lane="authoritative", author_verified=author, component_verified=component
            )


def test_enforcing_the_lane_does_not_couple_the_two_axes() -> None:
    # Independence means neither flag is derived from the other, not that the
    # lane may contradict them: every combination stays representable.
    for author, component in ((False, False), (True, False), (False, True), (True, True)):
        trust = CatalogTrust(
            trust_lane="experimental", author_verified=author, component_verified=component
        )
        assert (trust.author_verified, trust.component_verified) == (author, component)


def test_experimental_results_arrive_in_their_own_section() -> None:
    # SPEC-006 REQ-603 and ADR-0016: a separate section, never interleaved.
    response = ComponentListResponse(
        items=[component_summary()],
        experimental=[component_summary(latest_trust=EXPERIMENTAL)],
        page=page_info(),
    )
    assert [card.latest_trust.trust_lane for card in response.items] == ["authoritative"]
    assert [card.latest_trust.trust_lane for card in response.experimental] == ["experimental"]


def test_the_experimental_section_is_empty_by_default() -> None:
    # Consent is request-scoped, so a response that was never asked for the lane
    # carries nothing in it.
    assert ComponentListResponse(items=[], page=page_info()).experimental == []


def test_an_empty_authoritative_lane_is_an_honest_answer() -> None:
    response = ComponentListResponse(
        items=[], experimental=[component_summary(latest_trust=EXPERIMENTAL)], page=page_info()
    )
    assert response.items == []
    assert len(response.experimental) == 1


def test_a_page_is_bounded_across_both_lanes_not_per_lane() -> None:
    # Two arrays each capped at the maximum would let one page carry twice it.
    card = component_summary()
    half = PAGE_SIZE_MAX // 2
    ok = ComponentListResponse(items=[card] * half, experimental=[card] * half, page=page_info())
    assert len(ok.items) + len(ok.experimental) == PAGE_SIZE_MAX
    with pytest.raises(ValidationError):
        ComponentListResponse(items=[card] * PAGE_SIZE_MAX, experimental=[card], page=page_info())


def test_the_setup_page_is_bounded_the_same_way() -> None:
    # The two list responses are separate classes, so the bound has to hold on
    # both rather than only where it was first written.
    card = SetupSummary.model_validate(
        {
            "stable_id": "setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "publisher_id": "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "likes_count": 0,
            "updated_at": "2026-08-05T00:00:00.000Z",
            "latest_version": "1.0",
            "latest_name": "python-review",
            "latest_description": "Review setup for Python projects.",
            "latest_harness_id": "claude-code",
            "latest_purpose": "code review",
            "latest_target_role": "reviewer",
            "latest_tags": ["python"],
            "latest_lifecycle": "active",
            "latest_trust": AUTHORITATIVE,
            "latest_published_at": "2026-08-05T00:00:00.000Z",
            "latest_support": SUPPORT_MISSING,
        }
    )
    assert SetupListResponse(items=[card], page=page_info()).experimental == []
    with pytest.raises(ValidationError):
        SetupListResponse(items=[card] * PAGE_SIZE_MAX, experimental=[card], page=page_info())


def test_no_catalog_response_exposes_a_total_count() -> None:
    forbidden = {"total", "total_count", "count"}
    for model in (ComponentListResponse, SetupListResponse, ComponentSummary, PageInfo):
        assert forbidden.isdisjoint(model.model_fields)


def test_a_search_request_refuses_an_unknown_parameter() -> None:
    # A dropped filter is not forward compatibility: the caller asked to narrow
    # the result and would receive the unfiltered catalogue believing otherwise.
    with pytest.raises(ValidationError):
        ComponentSearchRequest.model_validate({"tag": ["python"]})
    assert ComponentSearchRequest.model_json_schema()["additionalProperties"] is False


def test_consent_to_the_experimental_lane_is_off_by_default() -> None:
    # ADR-0029 removed open-ended stored consent; it is a property of the call.
    assert ComponentSearchRequest().include_experimental is False
    assert SetupSearchRequest().include_experimental is False
    assert ComponentSearchRequest().sort_direction == "desc"
    assert SetupSearchRequest().sort_direction == "desc"


def test_a_search_request_bounds_its_own_inputs() -> None:
    assert ComponentSearchRequest(page_size=PAGE_SIZE_MAX).page_size == PAGE_SIZE_MAX
    with pytest.raises(ValidationError):
        ComponentSearchRequest(page_size=PAGE_SIZE_MAX + 1)
    with pytest.raises(ValidationError):
        ComponentSearchRequest(q="")
    with pytest.raises(ValidationError):
        ComponentSearchRequest(tags=[f"tag-{index}" for index in range(9)])
    with pytest.raises(ValidationError):
        ComponentSearchRequest(cursor="has space")


def test_a_search_request_accepts_an_inclusive_updated_range() -> None:
    from datetime import date

    request = ComponentSearchRequest(updated_from=date(2026, 1, 1), updated_to=date(2026, 1, 31))
    assert request.updated_from == date(2026, 1, 1)
    assert request.updated_to == date(2026, 1, 31)
    with pytest.raises(ValidationError):
        ComponentSearchRequest(updated_from=date(2026, 2, 2), updated_to=date(2026, 2, 1))


def test_a_setup_search_has_no_component_only_filter() -> None:
    assert "component_type" not in SetupSearchRequest.model_fields


def test_component_type_stays_the_closed_passport_taxonomy() -> None:
    with pytest.raises(ValidationError):
        component_summary(latest_component_type="marketplace")


def test_summary_rejects_an_unsupported_harness() -> None:
    with pytest.raises(ValidationError):
        component_summary(latest_harness_id="undefined")


def test_tags_keep_the_passport_bounds() -> None:
    with pytest.raises(ValidationError):
        component_summary(latest_tags=[])
    with pytest.raises(ValidationError):
        component_summary(latest_tags=[f"tag-{index}" for index in range(9)])


def test_version_entry_rejects_a_floating_reference() -> None:
    with pytest.raises(ValidationError):
        VersionListEntry(
            version="latest",
            passport_digest="sha256:" + "0" * 64,
            lifecycle="active",
            trust=AUTHORITATIVE,
            support=SUPPORT_MISSING,
            published_at="2026-08-05T00:00:00.000Z",
        )


def test_a_detail_read_always_carries_at_least_one_version() -> None:
    with pytest.raises(ValidationError):
        ComponentDetail(summary=component_summary(), versions=[])


def test_setup_summary_has_no_variant_axis() -> None:
    # ADR-0014: a setup belongs to one harness, so a variant is not part of its
    # identity.
    assert "variant_id" not in SetupSummary.model_fields
    assert "latest_variant_id" not in SetupSummary.model_fields


def test_version_response_serves_the_passport_as_the_description() -> None:
    # ADR-0012: the passport is the description of the version; there is no
    # separate manifest entity to serve alongside it.
    assert "passport" in ComponentVersionResponse.model_fields
    assert "manifest" not in ComponentVersionResponse.model_fields


def test_the_public_catalog_refuses_a_private_passport() -> None:
    assert version_response().passport.visibility == "public"
    private = published_passport("component-version.json", visibility="private")
    with pytest.raises(ValidationError):
        version_response(passport=private)


def test_an_omitted_visibility_is_not_silently_published() -> None:
    # PassportEnvelope defaults visibility to private, so a response that simply
    # omits the field must not slip through as public.
    complete = published_passport("component-version.json")
    without = {key: value for key, value in complete.items() if key != "visibility"}
    with pytest.raises(ValidationError):
        version_response(passport=without)


def test_the_setup_route_refuses_a_private_passport_too() -> None:
    fields: dict[str, object] = {
        "passport": published_passport("setup-version.json"),
        "passport_digest": "sha256:" + "0" * 64,
        "lifecycle": "active",
        "trust": AUTHORITATIVE,
        "support": SUPPORT_MISSING,
        "published_at": "2026-08-05T00:00:00.000Z",
        # Required, like every declared field of a `/v1` response: the schema
        # this model publishes marks them all required, so a Python default
        # here would accept a document the schema rejects.
        "component_checks": [],
    }
    assert SetupVersionResponse.model_validate(fields).passport.visibility == "public"
    private = published_passport("setup-version.json", visibility="private")
    with pytest.raises(ValidationError):
        SetupVersionResponse.model_validate(fields | {"passport": private})


def test_an_additive_field_is_accepted_and_preserved() -> None:
    card = component_summary().model_dump() | {"latest_deprecated_at": "2026-09-01T00:00:00.000Z"}
    parsed = ComponentSummary.model_validate(card)
    assert parsed.model_dump()["latest_deprecated_at"] == "2026-09-01T00:00:00.000Z"


def test_an_impossible_moment_is_rejected_at_the_boundary() -> None:
    with pytest.raises(ValidationError):
        component_summary(latest_published_at="2026-13-40T25:61:61.999Z")


def test_usage_metrics_are_absent_when_disabled_and_never_a_false_zero() -> None:
    assert USAGE_METRICS_ENABLED_BY_DEFAULT is False
    assert component_summary().usage_metrics is None
    assert version_response().usage_metrics is None
    present = CatalogUsageMetrics(detail_views_count=2, artifact_downloads_count=1)
    assert component_summary(usage_metrics=present).usage_metrics == present
    with pytest.raises(ValidationError):
        CatalogUsageMetrics(detail_views_count=-1, artifact_downloads_count=0)
