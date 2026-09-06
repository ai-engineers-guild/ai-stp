"""First-party catalog identity is the corpus, not a weaker id+description (A14)."""

from __future__ import annotations

from contextlib import closing

import pytest
from release_scripts.build_first_party_corpus import POSTURES, REPOSITORIES

from ai_stp_cli.commands import registry as registry_commands
from ai_stp_cli.commands.select import compile_setup_version_bundle
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_contracts.catalog import CatalogTrust
from ai_stp_contracts.first_party import (
    FirstPartyVersion,
    catalog_identities,
    catalog_identity,
    family,
)
from ai_stp_contracts.machine_help import CatalogVersionView
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport

PRIVATE = ("NDDev-it-com", "setup-systems", "/home/rldyourmnd/Developer/nddev")


def _held(item: FirstPartyVersion) -> registry_commands.AcquiredCatalogVersion:
    return registry_commands.AcquiredCatalogVersion(
        view=CatalogVersionView(
            kind=item.kind,
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
        ),
        passport=item.passport,
        artifact=item.artifact,
    )


def test_catalog_identity_is_the_corpus_setup_and_its_adaptations() -> None:
    members = family("claude-code", "full-auto")
    setup = next(item for item in members if item.kind == "setup")
    components = [item for item in members if item.kind == "component"]
    assert isinstance(setup.passport, SetupVersionPassport)

    identity = catalog_identity("claude-code", "full-auto")

    assert identity.harness_id == "claude-code"
    assert identity.posture == "full-auto"
    assert identity.setup_id == setup.passport.stable_id
    assert identity.setup_version == setup.passport.version
    assert identity.setup_passport_digest == setup.passport_digest
    assert {item.stable_id for item in identity.component_refs} == {
        item.passport.stable_id for item in components
    }
    by_id = {item.passport.stable_id: item for item in components}
    for ref in identity.component_refs:
        component = by_id[ref.stable_id]
        assert isinstance(component.passport, ComponentVersionPassport)
        assert ref.version == component.passport.version
        assert ref.passport_digest == component.passport_digest
        assert ref.adaptation_id == component.passport.adaptations[0].adaptation_id


def test_compiled_first_party_bundle_keeps_the_same_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    members = family("grok-build", "nddev-builder")
    setup = next(item for item in members if item.kind == "setup")
    held = {
        (item.kind, item.passport.stable_id, item.passport.version): _held(item) for item in members
    }

    def acquire_one(
        kind: str, stable_id: str, version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        assert offline is True
        return held[(kind, stable_id, version)]

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    registry_commands.acquire(
        {
            "id": setup.passport.stable_id,
            "version": setup.passport.version,
            "offline": True,
        }
    )
    identity = catalog_identity("grok-build", "nddev-builder")
    with closing(open_readonly(configured_path())) as connection:
        compiled = compile_setup_version_bundle(
            connection,
            setup.passport.stable_id,
            setup.passport.version,
            expected_harness="grok-build",
        )
    setup_doc = compiled.manifest["setup"]
    assert isinstance(setup_doc, dict)
    assert setup_doc["stable_id"] == identity.setup_id
    assert setup_doc["version"] == identity.setup_version
    conversion = compiled.manifest["conversion_report"]
    assert isinstance(conversion, dict)
    entries = conversion["entries"]
    assert isinstance(entries, list)
    assert {str(item["stable_id"]) for item in entries if isinstance(item, dict)} == {
        ref.stable_id for ref in identity.component_refs
    }


def test_every_published_posture_has_one_deterministic_catalog_identity() -> None:
    first = catalog_identities()
    second = catalog_identities()
    assert first == second
    expected = {(harness, posture) for harness in REPOSITORIES for posture in POSTURES}
    observed = {(item.harness_id, item.posture) for item in first}
    assert observed == expected
    dump = "\n".join(item.model_dump_json() for item in first)
    assert not any(marker in dump for marker in PRIVATE)
    for item in first:
        assert item.component_refs
        assert item.setup_id.startswith("setup_")
        assert all(ref.stable_id.startswith("component_") for ref in item.component_refs)
        assert all(ref.adaptation_id.startswith("adaptation_") for ref in item.component_refs)
