"""Federated source authority and identity conformance (SPEC-045)."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.federation import (
    CATALOG_METADATA_ADAPTERS_ENABLED_BY_DEFAULT,
    CatalogExternalCoordinate,
    CatalogMetadataObservation,
    CatalogMetadataObservationSet,
    FederatedSourceDescriptor,
    FederatedSourceSet,
    describe_catalog_metadata,
    describe_github_evidence,
    describe_store_port,
)
from ai_stp_contracts.github_evidence import GitHubArchiveEvidence
from ai_stp_contracts.store_ports import StorePortDescriptor

DIGEST = "sha256:" + "a" * 64
AT = "2026-08-13T12:00:00.000Z"
EXPIRES = "2026-08-14T12:00:00.000Z"


def _port() -> StorePortDescriptor:
    return StorePortDescriptor(
        adapter="sx",
        contract_version="2",
        root="/redacted/project",
        manifest="sx.toml",
        snapshot_digest=DIGEST,
        cli_status="not_required",
    )


def _github(*, freshness: str = "fresh") -> GitHubArchiveEvidence:
    available = freshness != "unavailable"
    return GitHubArchiveEvidence.model_validate(
        {
            "observation_id": 1 if available else None,
            "stable_id": "component_01J0000000000000000000000A",
            "version": "1.0",
            "passport_digest": DIGEST,
            "source_repository": "https://github.com/example/tool",
            "repository_id": 42 if available else None,
            "repository_full_name": "example/tool" if available else None,
            "repository_state": "active" if available else "unavailable",
            "archived": False if available else None,
            "fetched_at": AT if available else None,
            "expires_at": EXPIRES if available else None,
            "freshness": freshness,
            "proposal": "none",
        }
    )


def test_local_port_and_remote_metadata_share_one_closed_descriptor() -> None:
    local = describe_store_port(_port(), checked_at=AT)
    remote = describe_github_evidence(_github(), checked_at=AT)
    assert local.source_kind == "local_port"
    assert local.freshness == "local_snapshot"
    assert local.registry_effect == "confirmed_private_draft_import"
    assert local.checked_at == AT
    assert local.external_state == "present"
    assert local.rate_limit_policy == "not_applicable"
    assert remote.source_kind == "metadata_adapter"
    assert remote.freshness == "fresh"
    assert remote.registry_effect == "none"
    assert remote.external_state == "present"
    assert remote.rate_limit_policy == "adapter_owned"
    for descriptor in (local, remote):
        assert descriptor.authority == "external_observation"
        assert descriptor.author_verified is False
        assert descriptor.component_verified is False
        assert descriptor.target_write is False


@pytest.mark.parametrize("freshness", ["fresh", "stale", "unavailable"])
def test_remote_freshness_preserves_the_same_non_authoritative_boundary(freshness: str) -> None:
    descriptor = describe_github_evidence(_github(freshness=freshness), checked_at=AT)
    assert descriptor.freshness == freshness
    assert descriptor.authority == "external_observation"
    assert descriptor.registry_effect == "none"
    assert descriptor.external_state == ("unavailable" if freshness == "unavailable" else "present")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority", "canonical"),
        ("author_verified", True),
        ("component_verified", True),
        ("target_write", True),
        ("content", "poison"),
        ("local_path", "/secret"),
    ],
)
def test_external_metadata_cannot_promote_authority_or_expand_the_allowlist(
    field: str, value: object
) -> None:
    document = describe_github_evidence(_github(), checked_at=AT).model_dump(mode="json")
    document[field] = value
    with pytest.raises(ValidationError):
        FederatedSourceDescriptor.model_validate(document)


def test_exact_provider_identity_deduplicates_without_name_matching() -> None:
    local = describe_store_port(_port(), checked_at=AT)
    remote = describe_github_evidence(_github(), checked_at=AT)
    source_set = FederatedSourceSet(
        stable_id="component_01J0000000000000000000000A",
        references=[local, remote],
    )
    assert len(source_set.references) == 2
    assert source_set.auto_merged is False
    assert source_set.deduplication == "exact_provider_external_identifier"
    with pytest.raises(ValidationError, match="only once"):
        FederatedSourceSet(
            stable_id=source_set.stable_id,
            references=[remote, remote],
        )


def test_unavailable_reference_preserves_other_references() -> None:
    local = describe_store_port(_port(), checked_at=AT)
    unavailable = describe_github_evidence(_github(freshness="unavailable"), checked_at=AT)
    source_set = FederatedSourceSet(
        stable_id="component_01J0000000000000000000000A",
        references=[local, unavailable],
    )
    assert source_set.references == [local, unavailable]
    assert unavailable.external_state == "unavailable"


def test_archived_remote_state_is_an_observation_without_authority() -> None:
    document = _github().model_dump(mode="json")
    document.update(repository_state="archived", archived=True, proposal="deprecated")
    archived = describe_github_evidence(
        GitHubArchiveEvidence.model_validate(document), checked_at=AT
    )
    assert archived.external_state == "archived"
    assert archived.authority == "external_observation"
    assert archived.registry_effect == "none"


def test_canonical_url_and_dedup_key_cannot_hide_credentials_or_fuzzy_identity() -> None:
    document = describe_github_evidence(_github(), checked_at=AT).model_dump(mode="json")
    document["canonical_url"] = "https://token@github.com/example/tool"
    document["dedup_key"] = "github:similar-name"
    with pytest.raises(ValidationError):
        FederatedSourceDescriptor.model_validate(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "github"),
        ("freshness", "fresh"),
        ("provenance", "official_remote_observation"),
        ("registry_effect", "none"),
        ("fetched_at", AT),
        ("rate_limit_policy", "adapter_owned"),
        ("external_state", "archived"),
    ],
)
def test_local_port_rejects_incoherent_remote_properties(field: str, value: object) -> None:
    document = describe_store_port(_port(), checked_at=AT).model_dump(mode="json")
    document[field] = value
    if field == "provider":
        document["dedup_key"] = f"github:{document['external_identifier']}"
    with pytest.raises(ValidationError):
        FederatedSourceDescriptor.model_validate(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [("fetched_at", None), ("external_state", "unavailable")],
)
def test_available_remote_observation_rejects_unavailable_properties(
    field: str, value: object
) -> None:
    document = describe_github_evidence(_github(), checked_at=AT).model_dump(mode="json")
    document[field] = value
    with pytest.raises(ValidationError):
        FederatedSourceDescriptor.model_validate(document)


def _catalog_observation(
    *,
    provider: str = "skills_sh",
    external_identifier: str = "skill:exact-id",
    freshness: str = "fresh",
) -> CatalogMetadataObservation:
    available = freshness != "unavailable"
    return CatalogMetadataObservation.model_validate(
        {
            "provider": provider,
            "external_identifier": external_identifier,
            "dedup_key": f"{provider}:{external_identifier}",
            "source_url": "https://skills.sh/skill/exact-id",
            "attribution": "skills.sh terms",
            "terms_url": "https://skills.sh/terms",
            "fetched_at": AT,
            "checked_at": AT,
            "expires_at": EXPIRES,
            "freshness": freshness,
            "display_name": "Exact Skill",
            "summary": "Bounded summary",
            "homepage_url": "https://example.com",
            "popularity_count": 3,
            "external_state": "present" if available else "unavailable",
        }
    )


def test_catalog_adapters_are_disabled_until_policy_gate() -> None:
    assert CATALOG_METADATA_ADAPTERS_ENABLED_BY_DEFAULT is False


@pytest.mark.parametrize("provider", ["skills_sh", "nori", "modelcontextprotocol"])
def test_catalog_metadata_observation_uses_exact_coordinate(provider: str) -> None:
    coordinate = CatalogExternalCoordinate(
        provider=provider,  # type: ignore[arg-type]
        external_identifier="pkg:immutable-1",
    )
    observation = _catalog_observation(
        provider=provider, external_identifier=coordinate.external_identifier
    )
    descriptor = describe_catalog_metadata(observation)
    assert descriptor.provider == provider
    assert descriptor.source_kind == "metadata_adapter"
    assert descriptor.dedup_key == coordinate.dedup_key
    assert descriptor.terms_url == observation.terms_url
    assert descriptor.expires_at == EXPIRES
    assert descriptor.authority == "external_observation"
    assert descriptor.author_verified is False
    assert descriptor.component_verified is False
    assert descriptor.registry_effect == "none"
    assert descriptor.target_write is False


def test_catalog_revision_keeps_independent_references() -> None:
    first = _catalog_observation(provider="skills_sh", external_identifier="a")
    second = _catalog_observation(provider="nori", external_identifier="a")
    third = _catalog_observation(provider="modelcontextprotocol", external_identifier="a")
    source_set = CatalogMetadataObservationSet(
        stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        version="1.0",
        references=[first, second, third],
    )
    assert [item.dedup_key for item in source_set.references] == [
        "skills_sh:a",
        "nori:a",
        "modelcontextprotocol:a",
    ]
    with pytest.raises(ValidationError, match="only once"):
        CatalogMetadataObservationSet(
            stable_id=source_set.stable_id,
            version="1.0",
            references=[first, first],
        )


def test_catalog_observation_rejects_unknown_fields_and_fuzzy_identity() -> None:
    document = _catalog_observation().model_dump(mode="json")
    document["content"] = "poison"
    with pytest.raises(ValidationError):
        CatalogMetadataObservation.model_validate(document)
    document = _catalog_observation().model_dump(mode="json")
    document["dedup_key"] = "skills_sh:similar-name"
    with pytest.raises(ValidationError):
        CatalogMetadataObservation.model_validate(document)


def test_unavailable_catalog_observation_keeps_last_valid_timestamps() -> None:
    observation = _catalog_observation(freshness="unavailable")
    assert observation.fetched_at == AT
    descriptor = describe_catalog_metadata(observation)
    assert descriptor.freshness == "unavailable"
    assert descriptor.fetched_at is None
    assert descriptor.expires_at is None
    assert descriptor.terms_url == observation.terms_url
