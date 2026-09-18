"""Initialize intent: catalog surfaces, provider region patch, no Python writes."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from ai_stp_cli.application.initialize import (
    ANTIGRAVITY_LIMITATION,
    DIRECTORY_RULE_NAME,
    PATCH_OPERATION,
    SECTION_BEGIN,
    SECTION_END,
    PatchObservation,
    _region_wrote,
    drain,
    extract_section,
    global_instruction,
    instruction_path,
    patch_file_text,
    section_digest,
    surface_relative,
    wrap_section,
)
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.provider import protocol_v3
from ai_stp_foundation.envelope import continuation_argv


def test_section_contract_is_visible_and_bounded() -> None:
    text = wrap_section()
    assert text.startswith(SECTION_BEGIN)
    assert SECTION_END in text
    assert "<!--" not in text
    assert "-->" not in text
    assert len(text.encode("utf-8")) <= 2048
    assert len(text.splitlines()) <= 40
    assert "task intents" in text


def test_wrap_section_refuses_html_comments() -> None:
    with pytest.raises(ValueError, match="HTML comments"):
        wrap_section("hello <!-- secret -->")


def test_initialize_py_does_not_write_harness_files() -> None:
    source = Path("apps/cli/src/ai_stp_cli/application/initialize.py").read_text("utf-8")
    for verb in ("write_text(", "write_bytes(", "Path.open(", ".open("):
        assert verb not in source


def test_claude_code_surface_is_home_claude_md() -> None:
    layout = global_instruction("claude-code")
    assert layout is not None
    assert layout.relative == "CLAUDE.md"
    assert layout.shape == "file"
    assert layout.scope == "global"


def test_cursor_section_is_always_apply_mdc() -> None:
    text = wrap_section(harness_id="cursor")
    assert "alwaysApply: true" in text
    assert SECTION_BEGIN in text
    assert "<!--" not in text
    assert surface_relative("cursor") == f"rules/{DIRECTORY_RULE_NAME}"
    assert len(text.encode("utf-8")) <= 2048
    assert len(text.splitlines()) <= 40
    begin = text.index(SECTION_BEGIN)
    assert "alwaysApply: true" in text[:begin]
    assert "alwaysApply: true" not in (extract_section(text) or "")


def test_empty_cursor_file_keeps_always_apply_prefix() -> None:
    section = wrap_section(harness_id="cursor")
    updated, wrote = patch_file_text("", section)
    assert wrote is True
    assert updated == section
    assert updated.startswith("---\n")
    again, wrote_again = patch_file_text(updated, section)
    assert wrote_again is False
    assert again == updated
    changed = wrap_section("hello from a later patch", harness_id="cursor")
    spliced, wrote_change = patch_file_text(updated, changed)
    assert wrote_change is True
    assert spliced.startswith("---\n")
    assert spliced.count("alwaysApply: true") == 1
    assert "hello from a later patch" in spliced
    assert extract_section(spliced) == extract_section(changed)


def test_region_wrote_reads_the_kernel_effect_line() -> None:
    assert _region_wrote(("patch instruction region at rules/ai-stp.mdc",)) is True
    assert _region_wrote(("instruction region at rules/ai-stp.mdc already matches",)) is False
    assert _region_wrote(()) is False


def test_cursor_rules_stay_under_literal_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_CONFIG_DIR", str(tmp_path / "other"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = instruction_path("cursor")
    assert path == tmp_path / ".cursor" / "rules" / DIRECTORY_RULE_NAME


def test_splice_preserves_bytes_outside_markers() -> None:
    existing = "keep-me\n:::begin-ai-stp\nold\n:::end-ai-stp\nalso-keep\n"
    section = wrap_section()
    updated, wrote = patch_file_text(existing, section)
    assert wrote is True
    assert updated.startswith("keep-me\n")
    assert updated.endswith("also-keep\n")
    assert extract_section(updated) == section
    again, wrote_again = patch_file_text(updated, section)
    assert wrote_again is False
    assert again == updated


def test_antigravity_completes_with_the_catalog_limitation(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "initialize",
            "idempotency-key": "initialize-antigravity-01",
            "input": _facts(tmp_path, {"harness_id": "antigravity"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "completed"
    assert continued.payload.goal_satisfied is True
    assert continued.payload.outcome is not None
    assert continued.payload.outcome.kind == "initialize"
    assert continued.payload.outcome.harness_id == "antigravity"
    assert continued.payload.outcome.wrote is False
    assert continued.payload.outcome.limitation == ANTIGRAVITY_LIMITATION
    assert continued.payload.outcome.surface == ""


def test_missing_harness_blocks_with_one_human_question() -> None:
    started = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-ask-harness-01"}
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.questions[0].question_id == "harness-id"
    assert continued.payload.questions[0].actor == "human"
    assert continued.continuations[0].actor == "human"
    assert continued.continuations[0].arguments["question-id"] == "harness-id"
    assert continued.continuations[0].missing == ["value"]
    assert continuation_argv(continued.continuations[0])[:2] == ["task", "answer"]
    assert "--question-id" in continuation_argv(continued.continuations[0])
    assert "harness-id" in continuation_argv(continued.continuations[0])
    assert "--value" not in continuation_argv(continued.continuations[0])
    assert "help" not in continuation_argv(continued.continuations[0])


def test_answering_harness_id_then_blocks_on_a_too_old_provider(tmp_path: Path) -> None:
    started = task_command.start(
        {"intent": "initialize", "idempotency-key": "initialize-answer-harness-01"}
    )
    blocked = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    answered = task_command.answer(
        {
            "task": blocked.payload.task_id,
            "revision": blocked.payload.revision,
            "question-id": "harness-id",
            "value": "claude-code",
            "input": _facts(tmp_path, {}),
        }
    )
    assert answered.payload.state == "blocked"
    assert answered.payload.questions[0].question_id == "provider-too-old"
    assert answered.continuations[0].actor == "external"
    assert answered.continuations[0].path == ["task", "continue"]


def test_provider_without_the_optional_op_blocks_external() -> None:
    result = drain({"harness_id": "claude-code"}, operations=lambda: frozenset())
    assert result.outcome is None
    assert result.questions[0].question_id == "provider-too-old"
    assert result.questions[0].actor == "external"


def test_declared_op_without_a_patcher_stays_blocked() -> None:
    result = drain(
        {"harness_id": "claude-code"},
        operations=lambda: frozenset({PATCH_OPERATION}),
    )
    assert result.outcome is None
    assert result.questions[0].question_id == "provider-too-old"


def test_fake_provider_patcher_is_the_only_writer() -> None:
    seen: list[tuple[str, str]] = []

    def patcher(harness_id: str, section: str) -> PatchObservation:
        seen.append((harness_id, section))
        return PatchObservation(section_digest=section_digest(section), wrote=True)

    result = drain(
        {"harness_id": "claude-code"},
        operations=lambda: frozenset({PATCH_OPERATION}),
        patcher=patcher,
    )
    assert result.outcome is not None
    assert result.outcome.limitation == ""
    assert result.outcome.wrote is True
    assert result.outcome.surface == "CLAUDE.md"
    assert seen[0][0] == "claude-code"
    assert SECTION_BEGIN in seen[0][1]


def test_fake_patcher_preserves_custom_home_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    target = instruction_path("codex")
    assert target is not None
    target.write_text("keep-me\n", encoding="utf-8")

    def patcher(harness_id: str, section: str) -> PatchObservation:
        path = instruction_path(harness_id)
        assert path is not None
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        updated, wrote = patch_file_text(existing, section)
        if wrote:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(updated, encoding="utf-8")
        observed = extract_section(updated) or updated
        return PatchObservation(section_digest=section_digest(observed), wrote=wrote)

    first = drain(
        {"harness_id": "codex"},
        operations=lambda: frozenset({PATCH_OPERATION}),
        patcher=patcher,
    )
    text = target.read_text(encoding="utf-8")
    assert text.startswith("keep-me\n")
    assert SECTION_BEGIN in text
    assert first.outcome is not None
    assert first.outcome.wrote is True
    assert first.outcome.surface == "AGENTS.md"
    second = drain(
        {"harness_id": "codex"},
        operations=lambda: frozenset({PATCH_OPERATION}),
        patcher=patcher,
    )
    assert second.outcome is not None
    assert second.outcome.wrote is False
    assert target.read_text(encoding="utf-8") == text


def test_patch_instruction_region_is_optional_not_core() -> None:
    assert PATCH_OPERATION not in protocol_v3.CORE_OPERATIONS
    assert PATCH_OPERATION in protocol_v3.OPTIONAL_OPERATIONS
    assert PATCH_OPERATION in protocol_v3.OPERATION_NETWORK


def test_omitted_hooks_block_like_an_empty_provider() -> None:
    result = drain({"harness_id": "claude-code"})
    assert result.outcome is None
    assert result.questions[0].question_id == "provider-too-old"


def test_task_engine_initialize_writes_custom_codex_home_via_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    target = instruction_path("codex")
    assert target is not None
    target.write_text("keep-me\n", encoding="utf-8")
    _install_file_hooks(monkeypatch)
    started = task_command.start(
        {
            "intent": "initialize",
            "idempotency-key": "initialize-task-engine-codex-01",
            "input": _facts(tmp_path, {"harness_id": "codex"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "completed"
    assert continued.payload.goal_satisfied is True
    outcome = continued.payload.outcome
    assert outcome is not None
    assert outcome.kind == "initialize"
    assert outcome.wrote is True
    assert outcome.surface == "AGENTS.md"
    text = target.read_text(encoding="utf-8")
    assert text.startswith("keep-me\n")
    assert SECTION_BEGIN in text
    again = task_command.start(
        {
            "intent": "initialize",
            "idempotency-key": "initialize-task-engine-codex-02",
            "input": _facts(tmp_path, {"harness_id": "codex"}),
        }
    )
    replay = task_command.continue_(
        {"task": again.payload.task_id, "revision": again.payload.revision}
    )
    assert replay.payload.outcome is not None
    assert replay.payload.outcome.kind == "initialize"
    assert replay.payload.outcome.wrote is False
    assert target.read_text(encoding="utf-8") == text


def test_initialize_drain_failure_drops_expert_next_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.application import initialize as initialize_service
    from ai_stp_cli.errors import CliFailure

    monkeypatch.setattr(
        initialize_service, "provider_operations", lambda: frozenset({PATCH_OPERATION})
    )

    def boom(_harness_id: str, _section: str) -> PatchObservation:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "provider isolation is unavailable",
            next_actions=["provider network --json"],
        )

    monkeypatch.setattr(initialize_service, "patch_via_provider", boom)
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "initialize",
                "idempotency-key": "initialize-fail-strip-network-01",
                "input": _facts(tmp_path, {"harness_id": "claude-code"}),
            }
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert raised.value.details.get("task", "").startswith("task_")
    assert raised.value.details.get("state") == "failed"
    assert raised.value.next_actions == []


def _install_file_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.application import initialize as initialize_service

    monkeypatch.setattr(
        initialize_service, "provider_operations", lambda: frozenset({PATCH_OPERATION})
    )

    def patcher(harness_id: str, section: str) -> PatchObservation:
        path = instruction_path(harness_id)
        assert path is not None
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        updated, wrote = patch_file_text(existing, section)
        if wrote:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(updated, encoding="utf-8")
        observed = extract_section(updated) or updated
        return PatchObservation(section_digest=section_digest(observed), wrote=wrote)

    monkeypatch.setattr(initialize_service, "patch_via_provider", patcher)


def _facts(tmp_path: Path, body: dict[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)


def _dummy_provider(tmp_path: Path) -> Path:
    from ai_stp_cli import paths

    suffix = "" if paths.POSIX else ".exe"
    place = tmp_path / f"provider{suffix}"
    place.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    place.chmod(0o755)
    return place


def _remember(harness_id: str, executable: Path, *, source: str) -> None:
    from contextlib import closing

    from ai_stp_cli.local import provider_installations as installations
    from ai_stp_cli.local.database import configured_path, open_registry

    with closing(open_registry(configured_path(), create=True)) as connection:
        installations.remember(
            connection,
            installations.Installation(
                harness_id=harness_id,
                path=str(executable),
                source=source,
                state=installations.STATE_INSTALLED,
            ),
        )


def _capabilities(*, patch: bool, section: bool) -> protocol_v3.ProviderCapabilities:
    from ai_stp_cli.local.bundle import BUNDLE_FORMAT
    from ai_stp_foundation.canonical import JsonValue
    from ai_stp_foundation.digests import digest_canonical

    body: dict[str, JsonValue] = {
        "profile_id": "claude-code/native-files/1",
        "component_kinds": ["instruction"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["CLAUDE.md"],
        "bundle_formats": [BUNDLE_FORMAT],
        "max_files": 64,
        "max_bytes": 1024,
    }
    operations = [item.value for item in protocol_v3.CORE_OPERATIONS]
    if patch:
        operations.append(PATCH_OPERATION.value)
    info: dict[str, object] = {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": "claude-setup-system",
        "harness_id": "claude-code",
        "provider_version": "0.0.70",
        "provider_build_digest": "sha256:" + "c" * 64,
        "supported_commands": list(protocol_v3.CORE_COMMANDS),
        "supported_operations": operations,
        "supported_os": ["linux"],
        "supported_arch": ["x86_64"],
        "permission_profiles": ["standard"],
        "projection_profile": {
            **body,
            "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, body),
        },
    }
    if section:
        info["plan_request_fields"] = ["instruction_section"]
    return protocol_v3.parse_capabilities(info)


def test_discovered_provider_is_not_a_bind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.local import provider_installations as installations

    dummy = _dummy_provider(tmp_path)
    _remember("claude-code", dummy, source=installations.SOURCE_DISCOVERED)

    def boom(_path: Path) -> protocol_v3.ProviderCapabilities:
        raise AssertionError("discovered is not a bind")

    monkeypatch.setattr("ai_stp_cli.provider.attested_bind.inspect_provider", boom)
    result = drain({"harness_id": "claude-code"})
    assert result.outcome is None
    assert result.questions[0].question_id == "provider-too-old"


def test_remembered_provider_without_patch_stays_too_old(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.local import provider_installations as installations
    from ai_stp_cli.provider import attested_bind

    dummy = _dummy_provider(tmp_path)
    _remember("claude-code", dummy, source=installations.SOURCE_CHOSEN)

    def inspect(_path: Path) -> protocol_v3.ProviderCapabilities:
        return _capabilities(patch=False, section=False)

    monkeypatch.setattr(attested_bind, "inspect_provider", inspect)
    result = drain({"harness_id": "claude-code"})
    assert result.outcome is None
    assert result.questions[0].question_id == "provider-too-old"


def test_remembered_provider_without_instruction_section_stays_too_old(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.local import provider_installations as installations
    from ai_stp_cli.provider import attested_bind

    dummy = _dummy_provider(tmp_path)
    _remember("claude-code", dummy, source=installations.SOURCE_CHOSEN)

    def inspect(_path: Path) -> protocol_v3.ProviderCapabilities:
        return _capabilities(patch=True, section=False)

    monkeypatch.setattr(attested_bind, "inspect_provider", inspect)
    result = drain({"harness_id": "claude-code"})
    assert result.outcome is None
    assert result.questions[0].question_id == "provider-too-old"


def test_bound_provider_declaring_both_invokes_the_region_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.application import initialize as initialize_service
    from ai_stp_cli.local import provider_installations as installations
    from ai_stp_cli.provider import attested_bind

    dummy = _dummy_provider(tmp_path)
    _remember("claude-code", dummy, source=installations.SOURCE_CHOSEN)

    def inspect(_path: Path) -> protocol_v3.ProviderCapabilities:
        return _capabilities(patch=True, section=True)

    called: list[str] = []

    def patcher(
        harness_id: str, section: str, capabilities: protocol_v3.ProviderCapabilities
    ) -> PatchObservation:
        called.append(harness_id)
        assert PATCH_OPERATION in capabilities.operations
        assert "instruction_section" in capabilities.plan_request_fields
        return PatchObservation(section_digest=section_digest(section), wrote=True)

    monkeypatch.setattr(attested_bind, "inspect_provider", inspect)
    monkeypatch.setattr(initialize_service, "invoke_region_patch", patcher)
    result = drain({"harness_id": "claude-code"})
    assert called == ["claude-code"]
    assert result.outcome is not None
    assert result.outcome.wrote is True
    assert result.outcome.surface == "CLAUDE.md"


def test_invoke_region_patch_sends_instruction_section_when_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import Sequence

    from ai_stp_cli.application import initialize as initialize_service
    from ai_stp_cli.application.initialize import invoke_region_patch
    from ai_stp_cli.local import cache
    from ai_stp_cli.provider import invocation, operation_v3, release
    from ai_stp_cli.provider.conformance import Invoker
    from ai_stp_foundation.canonical import JsonValue

    captured: list[tuple[str, tuple[str, ...]]] = []
    section = wrap_section(harness_id="claude-code")

    def fake_invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        captured.append((command, tuple(arguments)))
        if command == "status":
            return {"target_digest": "sha256:" + "d" * 64}
        return {"state": "planned"}

    def fake_invoker(*_args: object, **_kwargs: object) -> Invoker:
        return fake_invoke

    def fake_plan(*_args: object, **_kwargs: object) -> operation_v3.ProviderPlan:
        return operation_v3.ProviderPlan(
            artifact={"format": "ai-stp-provider-plan/3"},
            digest="sha256:" + "e" * 64,
            effects=("patch instruction region at CLAUDE.md",),
        )

    def fake_applied(*_args: object, **_kwargs: object) -> str:
        return "ok"

    def fake_store(*_args: object, **_kwargs: object) -> Path:
        return tmp_path / "plan.json"

    def fake_identity(_path: Path) -> tuple[str, int]:
        return ("sha256:" + "a" * 64, 1)

    dummy = _dummy_provider(tmp_path)

    def bound(_harness: str) -> Path:
        return dummy

    monkeypatch.setattr(initialize_service, "bound_executable", bound)
    monkeypatch.setattr(invocation, "provider_invoker", fake_invoker)
    monkeypatch.setattr(operation_v3, "require_plan", fake_plan)
    monkeypatch.setattr(operation_v3, "require_applied", fake_applied)
    monkeypatch.setattr(cache, "store_provider_plan", fake_store)
    monkeypatch.setattr(release, "artifact_identity", fake_identity)

    observation = invoke_region_patch(
        "claude-code", section, _capabilities(patch=True, section=True)
    )
    assert observation.wrote is True
    planned = next(item for item in captured if item[0] == "plan-operation")
    argv = planned[1]
    assert "--instruction-section" in argv
    assert argv[argv.index("--instruction-section") + 1] == section


def _debug_provider(binary: str) -> Path | None:
    if binary == "cursor-setup-system":
        raw = os.environ.get("AI_STP_DEBUG_CURSOR_PROVIDER", "")
        if raw:
            place = Path(raw)
            return place if place.is_file() else None
    from ai_stp_cli.agy_qualify import host_home

    named = os.environ.get("AI_STP_DEBUG_PROVIDERS", "").strip()
    root = (
        Path(named)
        if named
        else host_home() / "Developer" / "nddev" / "setup-systems" / "target" / "debug"
    )
    place = root / binary
    return place if place.is_file() else None


def _iso_image() -> str | None:
    image = os.environ.get("AI_STP_QUALIFY_DOCKER_IMAGE", "ai-stp-iso:local")
    if shutil.which("docker") is None:
        return None
    held = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        check=False,
    )
    return image if held.returncode == 0 else None


@pytest.mark.parametrize(
    ("harness_id", "binary"),
    [
        ("cursor", "cursor-setup-system"),
        ("claude-code", "claude-setup-system"),
        ("codex", "codex-setup-system"),
        ("pi", "pi-setup-system"),
        ("opencode", "opencode-setup-system"),
        ("grok-build", "grok-setup-system"),
    ],
)
def test_debug_provider_declares_the_optional_patch(harness_id: str, binary: str) -> None:
    provider = _debug_provider(binary)
    if provider is None:
        pytest.skip(f"debug {binary} is not on this machine")
    from ai_stp_cli.provider.attested_bind import inspect_provider

    capabilities = inspect_provider(provider)
    assert capabilities.harness_id == harness_id
    assert PATCH_OPERATION in capabilities.operations
    assert "instruction_section" in capabilities.plan_request_fields


def test_debug_antigravity_does_not_declare_the_optional_patch() -> None:
    provider = _debug_provider("antigravity-setup-system")
    if provider is None:
        pytest.skip("debug antigravity-setup-system is not on this machine")
    from ai_stp_cli.provider.attested_bind import inspect_provider

    capabilities = inspect_provider(provider)
    assert capabilities.harness_id == "antigravity"
    assert PATCH_OPERATION not in capabilities.operations
    assert "instruction_section" in capabilities.plan_request_fields


@pytest.mark.parametrize(
    ("harness_id", "binary"),
    [
        ("cursor", "cursor-setup-system"),
        ("claude-code", "claude-setup-system"),
        ("codex", "codex-setup-system"),
        ("pi", "pi-setup-system"),
        ("opencode", "opencode-setup-system"),
        ("grok-build", "grok-setup-system"),
    ],
)
def test_docker_initialize_writes_the_catalogued_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harness_id: str, binary: str
) -> None:
    """Bound debug provider under privileged Docker. Does not tag or overwrite 0.0.72."""
    provider = _debug_provider(binary)
    image = _iso_image()
    if provider is None:
        pytest.skip(f"debug {binary} is not on this machine")
    if image is None:
        pytest.skip("privileged image ai-stp-iso:local is not on this machine")

    import shlex

    from ai_stp_cli.agy_qualify import docker_cli_command, repo_root
    from ai_stp_cli.config import set_values

    root = tmp_path / "ws"
    home = root / "home"
    project = root / "project"
    home.mkdir(parents=True)
    project.mkdir()
    bound = root / binary
    shutil.copy2(provider, bound)
    bound.chmod(bound.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    monkeypatch.delenv("CURSOR_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    set_values({f"provider.paths.{harness_id}": str(bound)})

    facts = project / "init.json"
    facts.write_text(json.dumps({"harness_id": harness_id}), encoding="utf-8")
    runner = root / "run-cli"
    runner.write_text(
        "#!/bin/sh\n"
        f"export HOME={shlex.quote(str(home))}\n"
        f"export USERPROFILE={shlex.quote(str(home))}\n"
        f"export XDG_CONFIG_HOME={shlex.quote(str(home / 'config'))}\n"
        f"export XDG_DATA_HOME={shlex.quote(str(home / 'data'))}\n"
        + docker_cli_command(
            image,
            root=root,
            repo=repo_root(),
            project=project,
        ),
        encoding="utf-8",
    )
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
    held = subprocess.run(
        [
            str(runner),
            "task",
            "start",
            "--intent",
            "initialize",
            "--idempotency-key",
            f"init-bridge-{harness_id}-01",
            "--input",
            "init.json",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert held.returncode == 0, held.stderr + held.stdout
    envelope = json.loads(held.stdout)
    assert envelope.get("ok") is True, held.stdout
    data = envelope.get("data") or {}
    assert data.get("state") == "completed", held.stdout
    assert data.get("goal_satisfied") is True
    outcome = data.get("outcome") or {}
    assert outcome.get("kind") == "initialize"
    assert outcome.get("harness_id") == harness_id
    assert outcome.get("wrote") is True
    assert outcome.get("surface") == surface_relative(harness_id)
    written = instruction_path(harness_id)
    assert written is not None
    text = written.read_text(encoding="utf-8")
    assert SECTION_BEGIN in text
    assert SECTION_END in text
    if harness_id == "cursor":
        assert text.startswith("---\n")
        assert "alwaysApply: true" in text[: text.index(SECTION_BEGIN)]
        assert "alwaysApply: true" not in (extract_section(text) or "")
    else:
        assert extract_section(text) is not None
        assert SECTION_BEGIN in text
