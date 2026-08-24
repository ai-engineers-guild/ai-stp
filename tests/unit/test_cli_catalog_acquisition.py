"""Exact catalogue setup acquisition into the local compiler (REQ-2113)."""

from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.cloud import catalog as cloud_catalog
from ai_stp_cli.commands import registry as registry_commands
from ai_stp_cli.commands.select import compile_setup_version_bundle
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache as local_cache
from ai_stp_cli.local import versions as local_versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_contracts.catalog import CatalogTrust
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import versions as corpus_versions
from ai_stp_contracts.machine_help import AnswerSource, CatalogVersionView
from ai_stp_passports.versions import SetupVersionPassport


def _grok() -> tuple[FirstPartyVersion, FirstPartyVersion]:
    component, setup = [
        item for item in corpus_versions() if item.passport.harness_id == "grok-build"
    ]
    return component, setup


def _held(
    item: FirstPartyVersion, *, source: AnswerSource = "online"
) -> registry_commands.AcquiredCatalogVersion:
    return registry_commands.AcquiredCatalogVersion(
        view=CatalogVersionView(
            kind=item.kind,
            source=source,
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


def test_exact_setup_graph_is_idempotently_acquired_and_compiled_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component, setup = _grok()
    held = {
        ("component", component.passport.stable_id, component.passport.version): _held(
            component, source="cache"
        ),
        ("setup", setup.passport.stable_id, setup.passport.version): _held(setup, source="cache"),
    }
    calls: list[tuple[str, str, str, bool]] = []

    def acquire_one(
        kind: str, stable_id: str, version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        calls.append((kind, stable_id, version, offline))
        return held[(kind, stable_id, version)]  # type: ignore[index]

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    parameters = {"id": setup.passport.stable_id, "version": "1.0", "offline": True}
    first = registry_commands.acquire(parameters).payload
    second = registry_commands.acquire(parameters).payload

    assert first == second
    assert first.source == "cache"
    assert [item.stable_id for item in first.components] == [component.passport.stable_id]
    assert (
        calls
        == [
            ("setup", setup.passport.stable_id, "1.0", True),
            ("component", component.passport.stable_id, "1.0", True),
        ]
        * 2
    )

    with closing(open_readonly(configured_path())) as connection:
        compiled = compile_setup_version_bundle(
            connection, setup.passport.stable_id, "1.0", expected_harness="grok-build"
        )
        assert len(compiled.archive) > 0
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM object_version), "
            "(SELECT count(*) FROM revision), (SELECT count(*) FROM content)"
        ).fetchone()
        assert tuple(counts) == (2, 2, 2)


def test_all_role_family_graphs_are_acquired_and_compiled_for_their_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = corpus_versions()
    role_setups: list[FirstPartyVersion] = []
    for item in corpus:
        if item.kind != "setup":
            continue
        assert isinstance(item.passport, SetupVersionPassport)
        if item.passport.target_role != "ai-harness-engineer":
            role_setups.append(item)
    held = {
        (item.kind, item.passport.stable_id, item.passport.version): _held(item, source="cache")
        for item in corpus
    }

    def acquire_one(
        kind: str, stable_id: str, version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        assert offline is True
        return held[(kind, stable_id, version)]

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    for setup in role_setups:
        assert isinstance(setup.passport, SetupVersionPassport)
        acquired = registry_commands.acquire(
            {"id": setup.passport.stable_id, "version": "1.0", "offline": True}
        ).payload
        assert acquired.harness_id in {"claude-code", "codex"}
        with closing(open_readonly(configured_path())) as connection:
            compiled = compile_setup_version_bundle(
                connection,
                setup.passport.stable_id,
                "1.0",
                expected_harness=setup.passport.harness_id,
            )
        assert compiled.archive
        assert compiled.files
        assert len({item.path for item in compiled.files}) == len(compiled.files)


@pytest.mark.parametrize(
    ("harness_id", "expected_paths"),
    [
        (
            "opencode",
            {
                "AGENTS.md",
                "agents/nddev-builder.md",
                "commands/nddev-orient.md",
                "commands/nddev-validate.md",
                "plugins/nddev-builder.js",
                "skills/nddev-builder/SKILL.md",
                "skills/nddev-builder/references/native-surfaces.md",
                "skills/nddev-builder/references/security-boundary.md",
            },
        ),
        (
            "pi",
            {
                "AGENTS.md",
                "packages/nddev-builder/AGENTS.md",
                "packages/nddev-builder/package.json",
                "packages/nddev-builder/skills/nddev-builder/SKILL.md",
                "settings.json",
                "skills/nddev-builder/SKILL.md",
            },
        ),
        (
            "cursor",
            {
                "AGENTS.md",
                "cli-config.json",
                "plugins/nddev-builder/.cursor-plugin/plugin.json",
                "plugins/nddev-builder/agents/nddev-builder.md",
                "plugins/nddev-builder/commands/nddev-agent.md",
                "plugins/nddev-builder/commands/nddev-hook-plan.md",
                "plugins/nddev-builder/commands/nddev-lifecycle.md",
                "plugins/nddev-builder/commands/nddev-mcp-plan.md",
                "plugins/nddev-builder/commands/nddev-permissions.md",
                "plugins/nddev-builder/commands/nddev-plugin-plan.md",
                "plugins/nddev-builder/commands/nddev-profile.md",
                "plugins/nddev-builder/commands/nddev-skill.md",
                "plugins/nddev-builder/commands/nddev-validate.md",
                "plugins/nddev-builder/rules/nddev-builder.mdc",
                "plugins/nddev-builder/skills/nddev-builder/SKILL.md",
                "plugins/nddev-builder/skills/nddev-builder/references/agents-subagents.md",
                "plugins/nddev-builder/skills/nddev-builder/references/configuration-profiles.md",
                "plugins/nddev-builder/skills/nddev-builder/references/hooks.md",
                "plugins/nddev-builder/skills/nddev-builder/references/installation-lifecycle.md",
                "plugins/nddev-builder/skills/nddev-builder/references/mcp.md",
                "plugins/nddev-builder/skills/nddev-builder/references/permissions-sandbox.md",
                "plugins/nddev-builder/skills/nddev-builder/references/plugins-marketplace.md",
                "plugins/nddev-builder/skills/nddev-builder/references/skills-instructions.md",
                "plugins/nddev-builder/skills/nddev-builder/references/validation-release.md",
                "plugins/nddev-builder/skills/nddev-builder/scripts/validate-toolkit.py",
            },
        ),
    ],
)
def test_beta_base_setup_graphs_acquire_and_compile_to_exact_native_surfaces(
    monkeypatch: pytest.MonkeyPatch,
    harness_id: str,
    expected_paths: set[str],
) -> None:
    corpus = corpus_versions()
    setup = next(
        item
        for item in corpus
        if item.kind == "setup"
        and isinstance(item.passport, SetupVersionPassport)
        and item.passport.harness_id == harness_id
        and item.passport.target_role == "ai-harness-engineer"
    )
    assert isinstance(setup.passport, SetupVersionPassport)
    held = {
        (item.kind, item.passport.stable_id, item.passport.version): _held(item, source="cache")
        for item in corpus
    }

    def acquire_one(
        kind: str, stable_id: str, version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        assert offline is True
        return held[(kind, stable_id, version)]

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    acquired = registry_commands.acquire(
        {"id": setup.passport.stable_id, "version": "1.0", "offline": True}
    ).payload
    assert len(acquired.components) == len(setup.passport.components)
    with closing(open_readonly(configured_path())) as connection:
        compiled = compile_setup_version_bundle(
            connection,
            setup.passport.stable_id,
            "1.0",
            expected_harness=harness_id,
        )
    assert {item.path for item in compiled.files} == expected_paths


def test_acquisition_failure_rolls_back_the_whole_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component, setup = _grok()
    held = {
        ("component", component.passport.stable_id): _held(component),
        ("setup", setup.passport.stable_id): _held(setup),
    }

    def acquire_one(
        kind: str, stable_id: str, _version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        del offline
        return held[(kind, stable_id)]

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    original = local_versions.record

    def fail_on_setup(connection: object, **values: object) -> object:
        if values["stable_id"] == setup.passport.stable_id:
            raise CliFailure("AI_STP_CONFLICT", "injected setup record failure")
        return original(connection, **values)  # type: ignore[arg-type]

    monkeypatch.setattr(local_versions, "record", fail_on_setup)
    with pytest.raises(CliFailure, match="injected"):
        registry_commands.acquire({"id": setup.passport.stable_id, "version": "1.0"})

    with closing(open_readonly(configured_path())) as connection:
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM object_version), "
            "(SELECT count(*) FROM revision), (SELECT count(*) FROM content)"
        ).fetchone()
        assert tuple(counts) == (0, 0, 0)


def test_offline_acquisition_reads_verified_bytes_without_resolving_an_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    component, _setup = _grok()
    acquired = _held(component, source="cache")
    artifact = tmp_path / "component.zip"
    artifact.write_bytes(component.artifact)

    def cached_version(_kind: str, _stable_id: str, _version: str) -> CatalogVersionView:
        return acquired.view

    def stored_artifact(_digest: str) -> Path:
        return artifact

    monkeypatch.setattr(cloud_catalog, "cached_version", cached_version)
    monkeypatch.setattr(local_cache, "stored_version_artifact", stored_artifact)
    monkeypatch.setattr(
        registry_commands,
        "endpoint",
        lambda: (_ for _ in ()).throw(AssertionError("offline acquisition opened the network")),
    )

    found = registry_commands.acquire_version(
        "component", component.passport.stable_id, "1.0", offline=True
    )
    assert found.artifact == component.artifact


def test_offline_acquisition_refuses_corrupt_cached_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    component, _setup = _grok()
    acquired = _held(component, source="cache")
    artifact = tmp_path / "component.zip"
    artifact.write_bytes(component.artifact + b"corrupt")

    def cached_version(_kind: str, _stable_id: str, _version: str) -> CatalogVersionView:
        return acquired.view

    def stored_artifact(_digest: str) -> Path:
        return artifact

    monkeypatch.setattr(cloud_catalog, "cached_version", cached_version)
    monkeypatch.setattr(local_cache, "stored_version_artifact", stored_artifact)

    with pytest.raises(CliFailure, match="no longer matches"):
        registry_commands.acquire_version(
            "component", component.passport.stable_id, "1.0", offline=True
        )
