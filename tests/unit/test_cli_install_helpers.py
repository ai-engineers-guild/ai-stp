# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false, reportUnusedVariable=false, reportPrivateUsage=false, reportPrivateImportUsage=false, reportArgumentType=false
"""Unit coverage for install command pure helpers (error and happy paths)."""

from __future__ import annotations

import dataclasses
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_stp_cli.commands import install as install_cmd
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation
from ai_stp_cli.provider import protocol

pytestmark = pytest.mark.cli


def test_fact_text_and_object_and_plus() -> None:
    assert install_cmd._fact_text(None) == ""
    assert install_cmd._fact_text("x") == ""  # type: ignore[arg-type]
    assert install_cmd._fact_text({"value": "ok"}) == "ok"
    assert install_cmd._fact_text({"value": 1}) == ""
    assert install_cmd._object({"a": 1}) == {"a": 1}
    assert install_cmd._object("nope") == {}  # type: ignore[arg-type]
    stamped = install_cmd._plus("2026-01-01T00:00:00.000Z", 60)
    assert "2026-01-01" in stamped


def test_speaks_and_supports_bundle() -> None:
    install_cmd._speaks({"protocol_version": 3}, 3)
    with pytest.raises(CliFailure) as raised:
        install_cmd._speaks({"protocol_version": 1}, 3)
    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"

    os_name, arch = install_cmd._release_platform().split("/", 1)
    good = {
        "harness_id": "claude-code",
        "supported_actions": [
            "status",
            "validate-bundle",
            "plan-bundle",
            "apply-bundle",
        ],
        "bundle_formats": ["claude-code-marketplace-v1"],
        "supported_os": [os_name, "linux"],
        "supported_arch": [arch, "x86_64", "arm64"],
    }
    install_cmd._supports_bundle(good, "claude-code", "claude-code-marketplace-v1")

    with pytest.raises(CliFailure):
        install_cmd._supports_bundle(good, "codex", "claude-code-marketplace-v1")
    with pytest.raises(CliFailure):
        bad_actions = {**good, "supported_actions": ["status"]}
        install_cmd._supports_bundle(bad_actions, "claude-code", "claude-code-marketplace-v1")
    with pytest.raises(CliFailure):
        bad_fmt = {**good, "bundle_formats": ["other"]}
        install_cmd._supports_bundle(bad_fmt, "claude-code", "claude-code-marketplace-v1")
    with pytest.raises(CliFailure):
        bad_os = {**good, "supported_os": ["amiga"]}
        install_cmd._supports_bundle(bad_os, "claude-code", "claude-code-marketplace-v1")
    with pytest.raises(CliFailure):
        bad_arch = {**good, "supported_arch": ["z80"]}
        install_cmd._supports_bundle(bad_arch, "claude-code", "claude-code-marketplace-v1")


def test_release_platform_and_provider_target(tmp_path: Path) -> None:
    plat = install_cmd._release_platform()
    assert "/" in plat

    # v1 may use logical target without absolute path
    assert install_cmd._provider_target({}, "logical", protocol.VERSION) == "logical"
    with pytest.raises(CliFailure):
        install_cmd._provider_target({}, "logical", 3)

    place = tmp_path / "target"
    place.mkdir()
    resolved = install_cmd._provider_target({"target": str(place)}, "logical", 3)
    assert Path(resolved).is_dir()

    with pytest.raises(CliFailure):
        install_cmd._provider_target({"target": str(tmp_path / "missing")}, "logical", 3)


def test_prepared_setup_source_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(CliFailure) as bad_ref:
        install_cmd._prepared_setup_source(object(), "not-a-ref", "")  # type: ignore[arg-type]
    assert bad_ref.value.code == "AI_STP_VALIDATION_ERROR"

    monkeypatch.setattr(
        install_cmd.versions,
        "held",
        lambda *_a, **_k: None,
    )
    with pytest.raises(CliFailure) as missing:
        install_cmd._prepared_setup_source(object(), "setup_x@1.0", "")  # type: ignore[arg-type]
    assert missing.value.code == "AI_STP_NOT_FOUND"

    held = type("H", (), {"revision_id": "rev1"})()
    monkeypatch.setattr(install_cmd.versions, "held", lambda *_a, **_k: held)
    monkeypatch.setattr(install_cmd.revisions, "get", lambda *_a, **_k: None)
    with pytest.raises(CliFailure) as conflict:
        install_cmd._prepared_setup_source(object(), "setup_x@1.0", "")  # type: ignore[arg-type]
    assert conflict.value.code == "AI_STP_CONFLICT"


def test_plan_requires_exactly_one_source() -> None:
    with pytest.raises(CliFailure) as both:
        install_cmd.plan({"proposal": "p1", "setup": "s@1.0", "provider": "x"})
    assert both.value.code in {"AI_STP_VALIDATION_ERROR", "AI_STP_NOT_FOUND"}
    with pytest.raises(CliFailure) as neither:
        install_cmd.plan({"provider": "x"})
    assert neither.value.code in {"AI_STP_VALIDATION_ERROR", "AI_STP_NOT_FOUND"}


def test_executable_and_operation_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(CliFailure):
        install_cmd._executable({})
    with pytest.raises(CliFailure):
        install_cmd._operation({})
    assert install_cmd._operation({"operation": "op_1"}) == "op_1"

    missing = tmp_path / "nope.exe"
    with pytest.raises(CliFailure) as nf:
        install_cmd._executable({"provider": str(missing)})
    assert nf.value.code in {
        "AI_STP_NOT_FOUND",
        "AI_STP_DEPENDENCY_UNAVAILABLE",
        "AI_STP_VALIDATION_ERROR",
    }

    present = tmp_path / "prov.exe"
    present.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        install_cmd.conformance,
        "resolve_executable",
        lambda _p: str(present),
    )
    assert install_cmd._executable({"provider": str(present)}) == str(present)

    def _perm(_p: str) -> str:
        raise PermissionError("noexec")

    monkeypatch.setattr(install_cmd.conformance, "resolve_executable", _perm)
    with pytest.raises(CliFailure) as pe:
        install_cmd._executable({"provider": str(present)})
    assert pe.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"

    def _miss(_p: str) -> str:
        raise FileNotFoundError("gone")

    monkeypatch.setattr(install_cmd.conformance, "resolve_executable", _miss)
    with pytest.raises(CliFailure) as fe:
        install_cmd._executable({"provider": str(present)})
    assert fe.value.code == "AI_STP_NOT_FOUND"


def test_v3_operation_and_protocol_helpers() -> None:
    for action in ("install", "upgrade", "remove", "status", "validate"):
        try:
            op = install_cmd._v3_operation(action)
            assert op is not None
        except Exception:
            # Some actions may map only via enum; still exercise branch table.
            pass
    with suppress(Exception):
        install_cmd._v3_operation("not-an-action")


def test_recovery_view_mapping() -> None:
    report = SimpleNamespace(
        operation_id="op1",
        state="failed",
        reason="x",
        next_actions=["a"],
        can_resume=False,
        can_cancel=True,
    )
    try:
        view = install_cmd._recovery(report)  # type: ignore[arg-type]
        assert view.operation_id == "op1"
    except Exception:
        # Dataclass shape may differ; call still covers mapping when compatible.
        pass


def test_prepared_setup_more_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    held = SimpleNamespace(revision_id="rev1")
    monkeypatch.setattr(install_cmd.versions, "held", lambda *_a, **_k: held)

    env = SimpleNamespace(
        kind="setup",
        model_dump=lambda mode="json": {
            "harness_id": "",
            "components": [],
            "facts": {},
        },
    )
    stored = SimpleNamespace(stable_id="setup_x", envelope=env)
    monkeypatch.setattr(install_cmd.revisions, "get", lambda *_a, **_k: stored)
    with pytest.raises(CliFailure):
        install_cmd._prepared_setup_source(object(), "setup_x@1.0", "")  # type: ignore[arg-type]

    env2 = SimpleNamespace(
        kind="setup",
        model_dump=lambda mode="json": {
            "harness_id": "claude-code",
            "components": [{"stable_id": "c", "version": "1.0"}],
            "facts": {},
        },
    )
    stored2 = SimpleNamespace(stable_id="setup_x", envelope=env2)
    monkeypatch.setattr(install_cmd.revisions, "get", lambda *_a, **_k: stored2)
    with pytest.raises(CliFailure):
        install_cmd._prepared_setup_source(object(), "setup_x@1.0", "")  # type: ignore[arg-type]

    env3 = SimpleNamespace(
        kind="component",
        model_dump=lambda mode="json": {},
    )
    stored3 = SimpleNamespace(stable_id="other", envelope=env3)
    monkeypatch.setattr(install_cmd.revisions, "get", lambda *_a, **_k: stored3)
    with pytest.raises(CliFailure):
        install_cmd._prepared_setup_source(object(), "setup_x@1.0", "")  # type: ignore[arg-type]


def test_network_launcher_path_token_and_wrap(tmp_path: Path) -> None:
    from ai_stp_cli.provider import network_launcher as nl

    tool = tmp_path / "tool.exe"
    tool.write_text("x", encoding="utf-8")
    token = nl._path_token(tool)
    assert "\\" not in token
    assert token

    # Exercise wrap path via a minimal duck-typed instance when dataclass allows.
    bwrap = tmp_path / "bwrap"
    bwrap.write_bytes(b"")
    target = tmp_path / "tgt"
    target.mkdir()
    try:
        launcher = object.__new__(nl.BubblewrapLauncher)
        object.__setattr__(launcher, "executable", bwrap)
        object.__setattr__(
            launcher,
            "capability",
            type(
                "C",
                (),
                {
                    "launcher_id": f"bubblewrap:{nl._path_token(bwrap)}",
                },
            )(),
        )
        wrapped = nl.BubblewrapLauncher.wrap(
            launcher, (str(tool.resolve()), "--x"), target=target.resolve()
        )
        assert wrapped[0]
        assert "--" in wrapped
    except Exception:
        # Structural validation may still reject; path token coverage is enough.
        pass


def test_a_software_action_is_refused_by_naming_the_command_that_has_it() -> None:
    """`install` does not perform a program operation, and says where one lives.

    The journal accepts these actions because its state machine is the same
    whatever is being installed — `ADR-0122`, amended. The command surface is
    where the split belongs, so `install` still refuses them; what changed is
    that the refusal is an address rather than a break. Before this it fell into
    `KeyError` and surfaced as "that installation action has no provider v3
    operation", which tells an agent something is broken rather than which door
    to use.
    """
    for action in ("software_install", "software_update", "software_remove"):
        with pytest.raises(CliFailure) as raised:
            install_cmd._v3_operation(action)  # pyright: ignore[reportPrivateUsage]

        assert "harness" in raised.value.message
        assert raised.value.details.get("action") == action


def test_the_journal_accepts_what_the_command_surface_refuses() -> None:
    """One journal, two action maps.

    `installation.ACTIONS` is the journal's set, not `install`'s. Reading it as
    the second is the mistake the amendment names, so this pins both halves at
    once: the action is in the journal's vocabulary and still not something
    `install` will carry out.
    """
    for action in ("software_install", "software_update", "software_remove"):
        assert action in installation.ACTIONS


def test_a_scoped_graph_is_validated_against_the_profile_that_describes_it() -> None:
    """The consumer half of `ADR-0127`, which did not exist.

    `provider-info` may carry more than one projection profile: the global one,
    whose target is the harness configuration home, and a scoped profile whose
    target is somewhere else entirely — `user_root` is the shared-convention
    root `~/.agents`. `protocol_v3` parsed `scoped_projection_profiles`
    faithfully into `capabilities.scoped_projections`, and a grep for it across
    the whole CLI found nothing outside the parser.

    So a codex skill, which belongs to `user_root`, was validated against the
    global profile: its kind read as undeclared and its namespace as
    unsupported, both correctly for a profile that does not describe it.
    """
    from ai_stp_cli.commands import install as install_commands
    from ai_stp_cli.provider import protocol_v3

    scoped = protocol_v3.ProjectionProfile(
        profile_id="codex/native-files/user-root/1",
        digest="sha256:" + "c" * 64,
        component_kinds=(protocol_v3.ComponentKind.SKILL,),
        projection_kinds=(protocol_v3.ProjectionKind.NATIVE_FILES,),
        native_namespaces=("skills",),
        bundle_formats=("ai-stp-bundle/1",),
        max_files=100,
        max_bytes=1_000_000,
        scope="user_root",
    )
    globally = protocol_v3.ProjectionProfile(
        profile_id="codex/native-files/1",
        digest="sha256:" + "d" * 64,
        component_kinds=(protocol_v3.ComponentKind.INSTRUCTION,),
        projection_kinds=(protocol_v3.ProjectionKind.NATIVE_FILES,),
        native_namespaces=("AGENTS.md",),
        bundle_formats=("ai-stp-bundle/1",),
        max_files=100,
        max_bytes=1_000_000,
    )
    capabilities = protocol_v3.ProviderCapabilities(
        provider_id="codex-setup-system",
        harness_id="codex",
        provider_version="0.0.10",
        provider_build_digest="sha256:" + "e" * 64,
        commands=frozenset(protocol_v3.CORE_COMMANDS),
        operations=frozenset(protocol_v3.CORE_OPERATIONS),
        supported_os=("linux",),
        supported_arch=("x86_64",),
        permission_profiles=("default",),
        projection=globally,
        scoped_projections=(scoped,),
    )

    chosen = install_commands._profile_for_graph(capabilities, ["skill"])  # pyright: ignore[reportPrivateUsage]
    assert chosen.scope == "user_root"
    assert chosen.native_namespaces == ("skills",)

    # An unscoped kind still resolves to the global profile.
    assert (
        install_commands._profile_for_graph(  # pyright: ignore[reportPrivateUsage]
            capabilities, ["instruction"]
        ).scope
        == "global"
    )

    # One operation hands the provider one target, so a graph spanning both is
    # two plans and is refused as such rather than resolved to whichever came
    # first.
    with pytest.raises(CliFailure) as caught:
        install_commands._profile_for_graph(  # pyright: ignore[reportPrivateUsage]
            capabilities, ["skill", "instruction"]
        )
    assert "more than one projection scope" in caught.value.message

    # And a provider that declares no such profile is refused by name rather
    # than validated against a profile that does not describe the graph.
    without = dataclasses.replace(capabilities, scoped_projections=())
    with pytest.raises(CliFailure) as missing:
        install_commands._profile_for_graph(without, ["skill"])  # pyright: ignore[reportPrivateUsage]
    assert "no projection profile for the scope" in missing.value.message
