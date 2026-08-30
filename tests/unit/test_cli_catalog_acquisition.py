"""Exact catalogue setup acquisition into the local compiler (REQ-2113)."""

from contextlib import closing
from pathlib import Path

import pytest
from release_scripts import build_first_party_corpus as builder
from release_scripts.build_first_party_corpus import REPOSITORIES

from ai_stp_cli.cloud import catalog as cloud_catalog
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import registry as registry_commands
from ai_stp_cli.commands.select import compile_setup_version_bundle
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache as local_cache
from ai_stp_cli.local import versions as local_versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_contracts.catalog import CatalogTrust
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import family as corpus_family
from ai_stp_contracts.first_party import versions as corpus_versions
from ai_stp_contracts.machine_help import AnswerSource, CatalogVersionView
from ai_stp_passports.envelope import derive_revision_id, verify_revision_id
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport


def _grok() -> tuple[tuple[FirstPartyVersion, ...], FirstPartyVersion]:
    """The grok-build family: every component, then the setup that pins them.

    This unpacked two values until 2026-08-29, when the corpus was rebuilt from
    the live setup systems and grok-build went from one component to four. A
    family is a set of an unknown size, and a test that says so keeps working
    when somebody else's builder tree grows.
    """
    # Harness **and** posture: a setup is a pair since `ADR-0130`, and the
    # harness alone now returns four of them.
    family = list(corpus_family("grok-build", "nddev-builder"))
    components = tuple(item for item in family if item.kind == "component")
    (setup,) = [item for item in family if item.kind == "setup"]
    return components, setup


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
    components, setup = _grok()
    held = {
        (item.kind, item.passport.stable_id, item.passport.version): _held(item, source="cache")
        for item in (*components, setup)
    }
    calls: list[tuple[str, str, str, bool]] = []

    def acquire_one(
        kind: str, stable_id: str, version: str, *, offline: bool
    ) -> registry_commands.AcquiredCatalogVersion:
        calls.append((kind, stable_id, version, offline))
        return held[(kind, stable_id, version)]  # type: ignore[index]

    monkeypatch.setattr(registry_commands, "acquire_version", acquire_one)
    # The object's own version. A literal `"1.0"` held while every member of the
    # corpus carried one; objects that were republished now carry `1.1`, and a
    # pinned version asks the corpus for something it no longer has.
    parameters = {
        "id": setup.passport.stable_id,
        "version": setup.passport.version,
        "offline": True,
    }
    first = registry_commands.acquire(parameters).payload
    second = registry_commands.acquire(parameters).payload

    assert first == second
    assert first.source == "cache"
    assert [item.stable_id for item in first.components] == [
        item.passport.stable_id for item in components
    ]
    assert (
        calls
        == [
            ("setup", setup.passport.stable_id, setup.passport.version, True),
            *(
                ("component", item.passport.stable_id, item.passport.version, True)
                for item in components
            ),
        ]
        * 2
    )

    with closing(open_readonly(configured_path())) as connection:
        compiled = compile_setup_version_bundle(
            connection,
            setup.passport.stable_id,
            setup.passport.version,
            expected_harness="grok-build",
        )
        assert len(compiled.archive) > 0
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM object_version), "
            "(SELECT count(*) FROM revision), (SELECT count(*) FROM content)"
        ).fetchone()
        assert tuple(counts) == ((len(components) + 1,) * 3)


def test_every_published_posture_graph_is_acquired_and_compiled_for_its_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All 28, not one — and this test asserted nothing at all until today.

    It selected setups whose `target_role` was **not** `ai-harness-engineer`,
    meaning the twelve invented role setups. Those went with the archived estate,
    so every setup in the corpus carried that role and the list came out empty:
    the loop below ran zero times and the test was green on nothing.

    The successor is the axis that does exist. Four postures on each of seven
    harnesses are published, all four are imported since `ADR-0130`, and each
    one's graph has to acquire and compile on its own.
    """
    corpus = corpus_versions()
    posture_setups = [item for item in corpus if item.kind == "setup"]
    assert len(posture_setups) == len(set(REPOSITORIES)) * len(builder.POSTURES)
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
    for setup in posture_setups:
        assert isinstance(setup.passport, SetupVersionPassport)
        # The passport's own version, not a literal `1.0`. A harness whose
        # projection was corrected republishes at `1.1` (`codex`, `cursor`,
        # `pi`), and a literal here asks the corpus for a version it no longer
        # has — a KeyError about a stable id, which reads as a missing object
        # rather than as this test naming the wrong one.
        acquired = registry_commands.acquire(
            {
                "id": setup.passport.stable_id,
                "version": setup.passport.version,
                "offline": True,
            }
        ).payload
        assert acquired.harness_id == setup.passport.harness_id
        assert setup.passport.posture in builder.POSTURES
        with closing(open_readonly(configured_path())) as connection:
            compiled = compile_setup_version_bundle(
                connection,
                setup.passport.stable_id,
                setup.passport.version,
                expected_harness=setup.passport.harness_id,
            )
        assert compiled.archive
        assert compiled.files
        assert len({item.path for item in compiled.files}) == len(compiled.files)


@pytest.mark.parametrize("harness_id", ["opencode", "pi"])
def test_beta_base_setup_graphs_acquire_and_compile_to_exact_native_surfaces(
    monkeypatch: pytest.MonkeyPatch,
    harness_id: str,
) -> None:
    """Every compiled file sits under a root some member declared, and none is lost.

    The expectation was a pinned set of file names until 2026-08-29. Those names
    belong to somebody else's builder tree — they move when the setup systems
    release — so the test was measuring their content rather than our compiler.
    What is ours is the pairing: the bundle contains exactly the files the
    artifacts carry, each under the managed root its component declared.
    """
    corpus = corpus_versions()
    setup = next(
        item
        for item in corpus
        if item.kind == "setup"
        and isinstance(item.passport, SetupVersionPassport)
        and item.passport.harness_id == harness_id
        and item.passport.posture == "nddev-builder"
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
        {
            "id": setup.passport.stable_id,
            "version": setup.passport.version,
            "offline": True,
        }
    ).payload
    assert len(acquired.components) == len(setup.passport.components)
    with closing(open_readonly(configured_path())) as connection:
        compiled = compile_setup_version_bundle(
            connection,
            setup.passport.stable_id,
            setup.passport.version,
            expected_harness=harness_id,
        )
    members = [
        item
        for item in corpus
        if item.kind == "component"
        and item.passport.stable_id in {ref.stable_id for ref in setup.passport.components}
    ]
    roots = {path for item in members for path in getattr(item.passport, "managed_paths", ())}
    assert roots
    compiled_paths = {item.path for item in compiled.files}
    assert compiled_paths
    for path in compiled_paths:
        assert any(path == root or path.startswith(f"{root}/") for root in roots), path
    for root in roots:
        assert any(path == root or path.startswith(f"{root}/") for path in compiled_paths), (
            f"{root} declared and nothing written under it"
        )


def test_acquisition_failure_rolls_back_the_whole_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components, setup = _grok()
    held = {(item.kind, item.passport.stable_id): _held(item) for item in (*components, setup)}

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
        registry_commands.acquire(
            {"id": setup.passport.stable_id, "version": setup.passport.version}
        )

    with closing(open_readonly(configured_path())) as connection:
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM object_version), "
            "(SELECT count(*) FROM revision), (SELECT count(*) FROM content)"
        ).fetchone()
        assert tuple(counts) == (0, 0, 0)


def test_offline_acquisition_reads_verified_bytes_without_resolving_an_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (component, *_rest), _setup = _grok()
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
        "component", component.passport.stable_id, component.passport.version, offline=True
    )
    assert found.artifact == component.artifact


def test_acquire_version_seals_published_bytes_not_a_model_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A historical passport omitting later defaults must still acquire.

    `verify_revision_id` dumps the validated model, which injects empty
    `harness_ids` / `supported_os` and is not the published seal.
    """
    (component, *_rest), _setup = _grok()
    published = component.passport.model_dump(mode="json")
    published.pop("harness_ids", None)
    published.pop("supported_os", None)
    published["revision_id"] = derive_revision_id(published)
    assert not verify_revision_id(ComponentVersionPassport.model_validate(published))

    view = CatalogVersionView(
        kind="component",
        source="online",
        checked_at="2026-08-25T00:00:00.000Z",
        passport_digest=local_cache.digest_of(published),
        lifecycle="active",
        trust=CatalogTrust(
            author_verified=True,
            component_verified=True,
            trust_lane="authoritative",
        ),
        published_at="2026-08-25T00:00:00.000Z",
        passport=published,
    )
    artifact = tmp_path / "component.zip"
    artifact.write_bytes(component.artifact)

    def version(*_args: object, **_kwargs: object) -> CatalogVersionView:
        return view

    def fetch_artifact(*_args: object, **_kwargs: object) -> Path:
        return artifact

    def stored_none(_digest: str) -> Path | None:
        return None

    monkeypatch.setattr(registry_commands, "endpoint", lambda: Endpoint("https://nddev.asia"))
    monkeypatch.setattr(cloud_catalog, "version", version)
    monkeypatch.setattr(cloud_catalog, "fetch_artifact", fetch_artifact)
    monkeypatch.setattr(local_cache, "stored_version_artifact", stored_none)

    found = registry_commands.acquire_version(
        "component", component.passport.stable_id, component.passport.version, offline=False
    )
    assert found.view.passport == published
    assert found.artifact == component.artifact


def test_offline_acquisition_refuses_corrupt_cached_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (component, *_rest), _setup = _grok()
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
            "component", component.passport.stable_id, component.passport.version, offline=True
        )
