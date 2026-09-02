# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportPrivateUsage=false, reportArgumentType=false
"""Offline setup-definition v2 acquisition and provider-bundle input (REQ-5711)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.cloud import catalog as cloud_catalog
from ai_stp_cli.commands import registry as registry_commands
from ai_stp_cli.commands.select import compile_setup_version_bundle
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import bundle
from ai_stp_cli.local import cache as local_cache
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_contracts.catalog import CatalogTrust
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import family as corpus_family
from ai_stp_contracts.machine_help import CatalogVersionView
from ai_stp_foundation.canonical import JsonValue, canonize, from_json_bytes
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import SetupVersionPassport
from ai_stp_sources.definition import (
    DEFINITION_V1,
    DEFINITION_V2,
    EmbeddedDraft,
    encode_component_ref,
    freeze_setup_definition,
)
from ai_stp_sources.models import SourceSnapshot

EMBEDDED_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAW"
AT = "2026-09-01T00:00:00.000Z"
DIGEST = "sha256:" + "b" * 64


def _grok() -> tuple[tuple[FirstPartyVersion, ...], FirstPartyVersion]:
    family = list(corpus_family("grok-build", "nddev-builder"))
    components = tuple(item for item in family if item.kind == "component")
    (setup,) = [item for item in family if item.kind == "setup"]
    return components, setup


def _fail_upstream(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("upstream GitHub or package registry was contacted")


def _mixed_setup(
    components: tuple[FirstPartyVersion, ...], setup: FirstPartyVersion
) -> tuple[bytes, dict[str, JsonValue]]:
    catalog_refs = tuple(
        ComponentRef(
            stable_id=item.passport.stable_id,
            version=item.passport.version,
            passport_digest=item.passport_digest,
        )
        for item in components
    )
    frozen = freeze_setup_definition(
        setup_id=setup.passport.stable_id,
        version=setup.passport.version,
        harness_id=setup.passport.harness_id,
        input_digest=DIGEST,
        publisher_id=setup.passport.owner_id,
        created_at=AT,
        catalog_members=catalog_refs,
        embedded_members=(
            EmbeddedDraft(
                snapshot=SourceSnapshot(
                    kind="path",
                    canonical_coordinate="path:skills/embedded-offline",
                    exact_identity="skills/embedded-offline",
                    component_digest=DIGEST,
                    files={"embedded-offline/SKILL.md": b"# Embedded offline\n"},
                ),
                component_type="skill",
                name="embedded-offline",
                description="Embedded skill used for offline acquisition.",
                license_spdx="MIT",
                harness_id=setup.passport.harness_id,
                stable_id=EMBEDDED_ID,
                managed_paths=("skills/embedded-offline/SKILL.md",),
            ),
        ),
        catalog_ids=frozenset(item.passport.stable_id for item in components),
    )
    document = cast(dict[str, JsonValue], setup.passport.model_dump(mode="json"))
    refs = [encode_component_ref(item) for item in frozen.components]
    document["components"] = frozen.document["components"]
    document["artifact"] = {
        "digest": digest_bytes("ai-stp:artifact:v1", frozen.payload),
        "size_bytes": len(frozen.payload),
    }
    document["artifact_format"] = DEFINITION_V2
    facts = document.get("facts")
    if isinstance(facts, dict):
        members = facts.get("members")
        if isinstance(members, dict):
            members["value"] = refs
    document.pop("revision_id", None)
    document["revision_id"] = derive_revision_id(document)
    return frozen.payload, document


def _setup_view(document: dict[str, JsonValue]) -> CatalogVersionView:
    return CatalogVersionView(
        kind="setup",
        source="cache",
        checked_at="2026-08-13T00:00:00.000Z",
        passport_digest=digest_bytes("ai-stp:passport:v1", canonize(document)),
        lifecycle="active",
        trust=CatalogTrust(
            author_verified=False,
            component_verified=False,
            trust_lane="experimental",
        ),
        published_at="2026-08-13T00:00:00.000Z",
        passport=document,
    )


def _component_view(item: FirstPartyVersion) -> CatalogVersionView:
    return CatalogVersionView(
        kind="component",
        source="cache",
        checked_at="2026-08-13T00:00:00.000Z",
        passport_digest=item.passport_digest,
        lifecycle="active",
        trust=CatalogTrust(
            author_verified=True,
            component_verified=True,
            trust_lane="authoritative",
        ),
        published_at="2026-08-13T00:00:00.000Z",
        passport=item.passport.model_dump(mode="json"),
    )


def _offline_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    components: tuple[FirstPartyVersion, ...],
    setup_document: dict[str, JsonValue],
    setup_artifact: bytes,
) -> dict[str, Path]:
    artifact_files: dict[str, Path] = {}
    setup_path = tmp_path / "setup.json"
    setup_path.write_bytes(setup_artifact)
    artifact_files[str(cast(dict[str, object], setup_document["artifact"])["digest"])] = setup_path
    views = {
        ("setup", str(setup_document["stable_id"]), str(setup_document["version"])): _setup_view(
            setup_document
        )
    }
    for item in components:
        path = tmp_path / f"{item.passport.stable_id}.bin"
        path.write_bytes(item.artifact)
        artifact_files[item.passport.artifact.digest] = path
        views[("component", item.passport.stable_id, item.passport.version)] = _component_view(item)

    def cached_version(kind: str, stable_id: str, number: str) -> CatalogVersionView:
        try:
            return views[(kind, stable_id, number)]
        except KeyError as error:
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "the exact catalogue version is not available in the verified cache",
                details={"stable_id": stable_id, "version": number},
            ) from error

    def stored_artifact(digest: str) -> Path | None:
        return artifact_files.get(digest)

    monkeypatch.setattr(cloud_catalog, "cached_version", cached_version)
    monkeypatch.setattr(local_cache, "stored_version_artifact", stored_artifact)
    monkeypatch.setattr(registry_commands, "endpoint", _fail_upstream)
    monkeypatch.setattr(cloud_catalog, "version", _fail_upstream)
    monkeypatch.setattr(cloud_catalog, "fetch_artifact", _fail_upstream)
    return artifact_files


def _write_cache_files(artifact_files: dict[str, Path]) -> None:
    for digest, source in artifact_files.items():
        target = local_cache.version_artifact_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def test_mixed_v2_setup_acquires_and_compiles_with_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    components, setup = _grok()
    payload, document = _mixed_setup(components, setup)
    assert document["artifact_format"] == DEFINITION_V2
    artifact_files = _offline_cache(
        monkeypatch,
        tmp_path,
        components=components,
        setup_document=document,
        setup_artifact=payload,
    )
    _write_cache_files(artifact_files)

    acquired = registry_commands.acquire(
        {
            "id": document["stable_id"],
            "version": document["version"],
            "offline": True,
        }
    ).payload
    assert acquired.source == "cache"
    assert EMBEDDED_ID in {item.stable_id for item in acquired.components}
    assert {item.passport.stable_id for item in components}.issubset(
        {item.stable_id for item in acquired.components}
    )

    with closing(open_readonly(configured_path())) as connection:
        compiled = compile_setup_version_bundle(
            connection,
            str(document["stable_id"]),
            str(document["version"]),
            expected_harness=str(document["harness_id"]),
        )
    assert compiled.archive
    assert any(item.path.endswith("embedded-offline/SKILL.md") for item in compiled.files)


def test_definition_version_1_catalog_setup_still_acquires_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    components, setup = _grok()
    artifact_files: dict[str, Path] = {}
    setup_path = tmp_path / "v1.json"
    setup_path.write_bytes(setup.artifact)
    artifact_files[setup.passport.artifact.digest] = setup_path
    views = {
        ("setup", setup.passport.stable_id, setup.passport.version): CatalogVersionView(
            kind="setup",
            source="cache",
            checked_at="2026-08-13T00:00:00.000Z",
            passport_digest=setup.passport_digest,
            lifecycle="active",
            trust=CatalogTrust(
                author_verified=True,
                component_verified=True,
                trust_lane="authoritative",
            ),
            published_at="2026-08-13T00:00:00.000Z",
            passport=setup.passport.model_dump(mode="json"),
        )
    }
    for item in components:
        path = tmp_path / f"{item.passport.stable_id}.bin"
        path.write_bytes(item.artifact)
        artifact_files[item.passport.artifact.digest] = path
        views[("component", item.passport.stable_id, item.passport.version)] = _component_view(item)

    def cached_version(kind: str, stable_id: str, number: str) -> CatalogVersionView:
        return views[(kind, stable_id, number)]

    monkeypatch.setattr(cloud_catalog, "cached_version", cached_version)
    monkeypatch.setattr(local_cache, "stored_version_artifact", artifact_files.get)
    monkeypatch.setattr(registry_commands, "endpoint", _fail_upstream)

    acquired = registry_commands.acquire(
        {
            "id": setup.passport.stable_id,
            "version": setup.passport.version,
            "offline": True,
        }
    ).payload
    assert acquired.source == "cache"
    document = cast(dict[str, JsonValue], from_json_bytes(setup.artifact))
    assert document.get("format") == DEFINITION_V1
    assert "embedded" not in document
    with closing(open_readonly(configured_path())) as connection:
        compiled = compile_setup_version_bundle(
            connection,
            setup.passport.stable_id,
            setup.passport.version,
            expected_harness=setup.passport.harness_id,
        )
    assert compiled.archive


def test_changed_cache_and_embedded_bytes_fail_before_provider_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    components, setup = _grok()
    payload, document = _mixed_setup(components, setup)
    artifact_files = _offline_cache(
        monkeypatch,
        tmp_path,
        components=components,
        setup_document=document,
        setup_artifact=payload,
    )
    _write_cache_files(artifact_files)
    registry_commands.acquire(
        {
            "id": document["stable_id"],
            "version": document["version"],
            "offline": True,
        }
    )

    planned: list[str] = []
    original = bundle.compile_bundle

    def wrapped(*args: object, **kwargs: object) -> object:
        planned.append("compile_bundle")
        return original(*args, **kwargs)

    monkeypatch.setattr(bundle, "compile_bundle", wrapped)

    catalog_digest = components[0].passport.artifact.digest
    local_cache.version_artifact_path(catalog_digest).write_bytes(b"corrupt-cache")
    with (
        closing(open_readonly(configured_path())) as connection,
        pytest.raises(CliFailure, match=r"no longer matches|changed before provider"),
    ):
        compile_setup_version_bundle(
            connection,
            str(document["stable_id"]),
            str(document["version"]),
            expected_harness=str(document["harness_id"]),
        )
    assert planned == []

    _write_cache_files(artifact_files)
    parsed = cast(dict[str, JsonValue], from_json_bytes(payload))
    embedded = parsed["embedded"]
    assert isinstance(embedded, list)
    record = next(
        item
        for item in embedded
        if isinstance(item, dict)
        and isinstance(item.get("ref"), dict)
        and cast(dict[str, JsonValue], item["ref"]).get("stable_id") == EMBEDDED_ID
    )
    digest = str(record["artifact_digest"])
    with closing(open_registry(configured_path())) as connection:
        connection.execute("UPDATE content SET bytes = ? WHERE digest = ?", (b"changed", digest))
        connection.commit()
    with (
        closing(open_readonly(configured_path())) as connection,
        pytest.raises(CliFailure, match=r"changed before provider|no longer matches"),
    ):
        compile_setup_version_bundle(
            connection,
            str(document["stable_id"]),
            str(document["version"]),
            expected_harness=str(document["harness_id"]),
        )
    assert planned == []


def test_embedded_acquire_does_not_fetch_catalog_for_embedded_refs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    components, setup = _grok()
    payload, document = _mixed_setup(components, setup)
    _offline_cache(
        monkeypatch,
        tmp_path,
        components=components,
        setup_document=document,
        setup_artifact=payload,
    )
    calls: list[tuple[str, str, str]] = []
    original = registry_commands.acquire_version

    def tracked(kind: str, stable_id: str, number: str, *, offline: bool) -> object:
        calls.append((kind, stable_id, number))
        assert offline is True
        assert stable_id != EMBEDDED_ID
        return original(kind, stable_id, number, offline=offline)

    monkeypatch.setattr(registry_commands, "acquire_version", tracked)
    acquired = registry_commands.acquire(
        {
            "id": document["stable_id"],
            "version": document["version"],
            "offline": True,
        }
    ).payload
    assert EMBEDDED_ID in {item.stable_id for item in acquired.components}
    assert all(item[1] != EMBEDDED_ID for item in calls)
    assert SetupVersionPassport.model_validate(document).stable_id == document["stable_id"]
