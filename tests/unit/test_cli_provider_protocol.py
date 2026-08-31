"""Protocol v1 is frozen, and the conformance kit actually catches a breach."""

import os
import re
import sys
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.commands import install, select
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import conformance, protocol
from ai_stp_foundation.canonical import JsonValue

CONTRACT = Path("docs/contracts/provider-protocol.md")
OPERATION = Path("docs/contracts/operation.md")
NETWORK_ADR = Path("docs/adr/ADR-0047-provider-network-capability.md")


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else {}


def test_windows_provider_argv_distinguishes_python_scripts_and_native_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "provider-script"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    native = tmp_path / "provider.exe"
    native.write_bytes(b"MZ")

    monkeypatch.setattr(os, "name", "nt")
    assert conformance._executable_argv(  # pyright: ignore[reportPrivateUsage]
        str(script)
    ) == [sys.executable, str(script)]
    assert conformance._executable_argv(  # pyright: ignore[reportPrivateUsage]
        str(native)
    ) == [str(native)]
    assert conformance._executable_argv(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "missing")
    ) == [str(tmp_path / "missing")]
    monkeypatch.setattr(os, "name", "posix")
    assert conformance._executable_argv(  # pyright: ignore[reportPrivateUsage]
        str(script)
    ) == [str(script)]


def _arguments(arguments: Sequence[str]) -> dict[str, str]:
    return dict(zip(arguments[::2], arguments[1::2], strict=True))


def _bundle_echo(arguments: Sequence[str]) -> dict[str, JsonValue]:
    values = _arguments(arguments)
    return {
        "bundle_format": values["--bundle-format"],
        "bundle_digest": values["--bundle-digest"],
        "artifact_digest": values["--artifact-digest"],
        "bundle_size": int(values["--bundle-size"]),
    }


def _corpus_case(arguments: Sequence[str]) -> str:
    return Path(_arguments(arguments)["--bundle"]).parent.name


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows CreateProcess does not map shebang/non-exec into the typed CLI failure",
)
def test_a_non_executable_provider_is_typed_before_spawn(tmp_path: Path) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("print('not reached')\n", encoding="utf-8")

    with pytest.raises(CliFailure) as conformance_failure:
        select.provider_conformance(
            {"harness": "claude-code", "executable": str(provider), "target": str(tmp_path)}
        )
    with pytest.raises(CliFailure) as install_failure:
        install._executable({"provider": str(provider)})  # pyright: ignore[reportPrivateUsage]

    assert conformance_failure.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert install_failure.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def _conforming(**broken: JsonValue) -> conformance.Invoker:
    """A stub provider that conforms, unless a test breaks one thing.

    One stub with one lever rather than a family of them: a test that changes a
    single answer says exactly what the kit is sensitive to, and a second stub
    could differ in ways nobody noticed.
    """
    info: dict[str, JsonValue] = {
        "protocol_version": protocol.VERSION,
        "harness_id": "claude-code",
        "provider_version": "1.0.0",
        "supported_actions": list(protocol.COMMANDS),
        "bundle_formats": ["ai-stp-bundle/1"],
        "supported_os": ["linux", "macos"],
        "supported_arch": ["x86_64", "arm64"],
        "limits": {"max_files": 2000},
    }
    # `state` is answered by `status`, not by `provider-info`; everything else a
    # test passes here overrides the field of that name.
    info.update({name: value for name, value in broken.items() if name != "state"})

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        if command == "provider-info":
            return info
        if command == "validate-bundle":
            case = _corpus_case(arguments)
            if case == "valid":
                return {**_bundle_echo(arguments), "valid": True}
            reasons = {item.name: item.refusal for item in conformance.MALICIOUS_BUNDLES}
            return {**_bundle_echo(arguments), "rejected": True, "reason": reasons[case]}
        if command == "plan-bundle":
            values = _arguments(arguments)
            return {
                **_bundle_echo(arguments[:-2]),
                "state": "planned",
                "expected_target_digest": values["--expected-target-digest"],
                "plan_digest": "sha256:" + "2" * 64,
                "effects": ["write conformance target"],
            }
        if command == "status":
            return {"state": broken.get("state", "verified")}
        return {"answered": command}

    return invoke


def test_a_conforming_provider_passes_every_case() -> None:
    report = conformance.run(_conforming(), harness_id="claude-code")
    assert report.conforms, [case.detail for case in report.failures]
    assert report.protocol_version == protocol.VERSION
    assert report.harness_id == "claude-code"


def test_cli_conformance_sends_literal_zip_paths_to_a_real_provider(tmp_path: Path) -> None:
    trace = tmp_path / "bundle-paths"
    reasons = {item.name: item.refusal for item in conformance.MALICIOUS_BUNDLES}
    executable = _writing(
        tmp_path,
        "literal-provider",
        "import json, pathlib, sys\n"
        "command = sys.argv[1]\n"
        "args = sys.argv[2:]\n"
        "values = dict(zip(args[::2], args[1::2], strict=True))\n"
        f"reasons = {reasons!r}\n"
        "if command == 'provider-info':\n"
        "  answer = {'protocol_version': 1, 'harness_id': 'claude-code', "
        "'provider_version': '1.0.0', 'supported_actions': "
        "['provider-info', 'software-status', 'software-plan', 'validate-bundle', "
        "'plan-bundle', 'status'], 'bundle_formats': ['ai-stp-bundle/1'], "
        "'supported_os': ['linux'], 'supported_arch': ['x86_64'], 'limits': {}}\n"
        "elif command in {'validate-bundle', 'plan-bundle'}:\n"
        "  path = pathlib.Path(values['--bundle'])\n"
        f"  with open({str(trace)!r}, 'a', encoding='utf-8') as held:\n"
        "    held.write(str(path) + '\\n')\n"
        "  assert path.is_absolute() and path.is_file() and path.suffix == '.zip'\n"
        "  answer = {'bundle_format': values['--bundle-format'], "
        "'bundle_digest': values['--bundle-digest'], "
        "'artifact_digest': values['--artifact-digest'], "
        "'bundle_size': int(values['--bundle-size'])}\n"
        "  case = path.parent.name\n"
        "  if case != 'valid': answer.update(rejected=True, reason=reasons[case])\n"
        "  elif command == 'validate-bundle': answer['valid'] = True\n"
        "  else: answer.update(state='planned', "
        "expected_target_digest=values['--expected-target-digest'], "
        "plan_digest='sha256:' + '2' * 64, effects=['write disposable target'])\n"
        "elif command == 'status': answer = {'state': 'verified'}\n"
        "else: answer = {'answered': command}\n"
        "print(json.dumps(answer, sort_keys=True))\n",
    )

    answer = select.provider_conformance(
        {"harness": "claude-code", "executable": executable, "target": str(tmp_path)}
    )

    assert answer.payload.conforms
    observed = [Path(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert observed and all(not path.exists() for path in observed)


def test_conformance_never_invokes_an_effect_or_launch_on_the_selected_target() -> None:
    seen: list[str] = []

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        seen.append(command)
        return _conforming()(command, arguments)

    report = conformance.run(invoke, harness_id="claude-code")

    assert report.conforms
    assert not set(seen) & (set(protocol.APPLY_COMMANDS) | {"launch"})


# Each of these is the kit proving it would catch a real breach. A kit that
# passes everything proves only that it runs.
def test_a_missing_provider_info_field_fails() -> None:
    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        answer = _conforming()(command, arguments)
        if command == "provider-info" and isinstance(answer, dict):
            return {name: value for name, value in answer.items() if name != "limits"}
        return answer

    failed = {case.name for case in conformance.run(invoke, harness_id="claude-code").failures}
    assert "provider_info_complete" in failed


def test_an_unknown_protocol_version_fails() -> None:
    report = conformance.run(
        _conforming(protocol_version=protocol.VERSION + 1), harness_id="claude-code"
    )
    assert "protocol_version_spoken" in {case.name for case in report.failures}


def test_a_provider_for_another_harness_fails() -> None:
    report = conformance.run(_conforming(), harness_id="codex")
    assert "harness_matches" in {case.name for case in report.failures}


def test_a_command_the_protocol_has_no_name_for_fails() -> None:
    report = conformance.run(
        _conforming(supported_actions=[*protocol.COMMANDS, "install-everything"]),
        harness_id="claude-code",
    )
    assert "actions_within_protocol" in {case.name for case in report.failures}


def test_declaring_an_action_that_does_not_answer_fails() -> None:
    """The omission is visible; the claim is not, until something depends on it."""

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        if command == "software-plan":
            return {"unsupported": True}
        return _conforming()(command, arguments)

    report = conformance.run(invoke, harness_id="claude-code")
    assert "declared_safe_actions_answer" in {case.name for case in report.failures}


def test_a_state_that_maps_to_nothing_fails() -> None:
    report = conformance.run(_conforming(state="mostly_fine"), harness_id="claude-code")
    assert "state_is_mapped" in {case.name for case in report.failures}


def test_a_read_that_answers_differently_twice_fails() -> None:
    """Not proof it wrote, but a read whose answer moved has done something."""
    seen: list[int] = []

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        if command == "software-status":
            seen.append(1)
            return {"calls": len(seen)}
        return _conforming()(command, arguments)

    report = conformance.run(invoke, harness_id="claude-code")
    assert "reads_are_repeatable" in {case.name for case in report.failures}


@pytest.mark.parametrize(
    "malicious",
    conformance.MALICIOUS_BUNDLES,
    ids=lambda item: item.name,
)
def test_accepting_any_malicious_bundle_fails(
    malicious: conformance.MaliciousBundle,
) -> None:
    """`REQ-804`: one case per class, and each one proves the kit is sensitive."""

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        if command == "validate-bundle" and _corpus_case(arguments) == malicious.name:
            return {"rejected": False}
        return _conforming()(command, arguments)

    report = conformance.run(invoke, harness_id="claude-code")
    assert f"rejects_{malicious.name}" in {case.name for case in report.failures}


def test_the_corpus_covers_every_rejection_class() -> None:
    assert {item.refusal for item in conformance.MALICIOUS_BUNDLES} == protocol.BUNDLE_REJECTIONS
    names = [item.name for item in conformance.MALICIOUS_BUNDLES]
    assert len(names) == len(set(names))
    assert {"symbolic_link_not_allowed", "hard_link_not_allowed"} <= set(names)


# The frozen declaration itself.
def test_the_twelve_commands_match_the_contract() -> None:
    block = re.search(r"```text\n(.*?)```", CONTRACT.read_text("utf-8"), re.S)
    assert block is not None
    assert tuple(block.group(1).split()) == protocol.COMMANDS
    assert len(protocol.COMMANDS) == 12


def test_every_command_is_either_a_read_or_an_apply_or_a_plan() -> None:
    """A command in neither set is one nobody decided the effect of."""
    classified = protocol.READ_COMMANDS | protocol.APPLY_COMMANDS
    unclassified = set(protocol.COMMANDS) - classified
    assert unclassified == {"software-plan", "launch"}, (
        "a plan has no effect of its own and launch runs the harness; "
        "anything else unclassified is an effect nobody decided"
    )


def test_the_state_mapping_matches_the_contract() -> None:
    text = CONTRACT.read_text("utf-8")
    for reported, mapped in protocol.STATE_MAP.items():
        assert f"| `{reported}` | `{mapped}` |" in text


def test_every_provider_state_maps_to_a_declared_operation_state() -> None:
    block = re.search(r"```text\n(.*?)```", OPERATION.read_text("utf-8"), re.S)
    assert block is not None
    declared = set(block.group(1).split())
    assert set(protocol.STATE_MAP.values()) <= declared
    assert declared >= protocol.OPERATION_ONLY_STATES


@pytest.mark.parametrize("state", sorted(protocol.OPERATION_ONLY_STATES))
def test_a_provider_cannot_report_an_operation_only_state(state: str) -> None:
    """`approved` is the user's decision; `cancelled` is stopping before an effect."""
    with pytest.raises(KeyError):
        protocol.operation_state(state)


def test_an_unmapped_state_is_refused_rather_than_passed_through() -> None:
    with pytest.raises(KeyError):
        protocol.operation_state("mostly_fine")


def test_applied_is_not_success() -> None:
    """`REQ-809`: a target changed and not verified has not succeeded."""
    assert protocol.operation_state("applied_unverified") != protocol.SUCCESS_STATE
    assert protocol.SUCCESS_STATE == "verified"


def test_the_boundary_is_declared_as_values_rather_than_advice() -> None:
    boundary = protocol.BOUNDARY
    assert boundary.argument_array and not boundary.shell
    assert boundary.absolute_target and boundary.exact_executable
    assert boundary.timeout_seconds > 0
    assert boundary.output_limit_bytes > 0
    assert "PATH" in boundary.environment_allowlist


def test_the_environment_allowlist_carries_nothing_that_looks_like_a_secret() -> None:
    for name in protocol.BOUNDARY.environment_allowlist:
        assert not any(mark in name.upper() for mark in ("TOKEN", "KEY", "SECRET", "PASSWORD"))


def test_only_this_version_is_spoken() -> None:
    assert protocol.speaks(protocol.VERSION)
    assert not protocol.speaks(protocol.VERSION + 1)
    assert not protocol.speaks(protocol.VERSION - 1)


def test_network_policy_does_not_silently_widen_frozen_v1() -> None:
    """`#184` needs v2; adding fields to v1 would only rename the gap."""
    assert protocol.VERSION == 1
    assert not {field.name for field in fields(protocol.Boundary)} & {
        "network_requirement",
        "network_enforcement",
    }

    contract = CONTRACT.read_text(encoding="utf-8")
    decision = NETWORK_ADR.read_text(encoding="utf-8")
    assert "protocol v1 declares no network requirement" in contract
    for value in ("none", "artifact_download", "runtime_external"):
        assert f"`network_requirement = {value}`" in decision
    for value in ("enforced", "unavailable", "not_requested"):
        assert f"`network_enforcement = {value}`" in decision
    assert "`VERSION = 1`" in decision


def test_the_environment_allowlist_passes_real_values_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An allowlist lets these names through; it does not blank them.

    Passing them empty is a different thing entirely: a provider with no `PATH`
    cannot start at all, and the failure reads as a broken provider rather than
    as a broken caller. Found by a provider stub that would not run.
    """
    import stat

    place = tmp_path / "echo-env"
    place.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os\n"
        "print(json.dumps({'path': os.environ.get('PATH', '')}))\n",
        encoding="utf-8",
    )
    place.chmod(place.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setenv("AI_STP_SECRET_THING", "must-not-cross")
    invoke = conformance.subprocess_invoker(str(place), str(tmp_path))
    answer = _object(invoke("provider-info", ()))
    assert answer.get("path"), "PATH crossed with a real value"


def test_the_environment_allowlist_drops_everything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stat

    place = tmp_path / "echo-all"
    place.write_text(
        "#!/usr/bin/env python3\nimport json, os\nprint(json.dumps(sorted(os.environ)))\n",
        encoding="utf-8",
    )
    place.chmod(place.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setenv("AI_STP_SECRET_THING", "must-not-cross")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-cross")
    reported = conformance.subprocess_invoker(str(place), str(tmp_path))("provider-info", ())
    answer = (
        [str(item) for item in cast(list[JsonValue], reported)]
        if isinstance(reported, list)
        else []
    )

    # Asserting an exact subset would be asserting something else: CPython adds
    # `LC_CTYPE` to its own child on some platforms, and that is the
    # interpreter's doing rather than ours. What must hold is that nothing the
    # caller was carrying crossed.
    crossed = set(answer) - set(protocol.BOUNDARY.environment_allowlist)
    assert "AI_STP_SECRET_THING" not in answer
    assert "AWS_SECRET_ACCESS_KEY" not in answer
    assert not any(
        mark in name.upper() for name in crossed for mark in ("TOKEN", "KEY", "SECRET", "PASSWORD")
    )


# The output-volume class of `#184`, which the boundary declared and did not keep.
def _writing(tmp_path: Path, name: str, body: str) -> str:
    import stat

    place = tmp_path / name
    place.write_text(f"#!/usr/bin/env python3\n{body}", encoding="utf-8")
    place.chmod(place.stat().st_mode | stat.S_IXUSR)
    return str(place)


def test_a_provider_that_floods_stdout_is_stopped_rather_than_read(tmp_path: Path) -> None:
    """The limit has to bound what is read, not what is kept afterwards.

    `capture_output` reads to end of file and truncates after: a provider
    emitting 64 MiB grew this process by 183 MiB and ran to completion while the
    boundary said 1 MiB the whole time. The marker file is the evidence — if the
    child reaches it, nothing stopped it.
    """
    marker = tmp_path / "ran-to-completion"
    executable = _writing(
        tmp_path,
        "flood",
        "import sys\n"
        "chunk = 'x' * (1024 * 1024)\n"
        "for _ in range(8):\n"
        "    sys.stdout.write(chunk)\n"
        "sys.stdout.flush()\n"
        f"open({str(marker)!r}, 'w').write('done')\n",
    )

    answer = conformance.subprocess_invoker(executable, "project_x:claude-code")("status", ())
    assert isinstance(answer, dict)
    assert "past the output limit" in str(answer.get("error"))
    assert not marker.exists(), "the child ran to completion, so nothing bounded it"


def test_an_answer_inside_the_limit_is_read_normally(tmp_path: Path) -> None:
    """Otherwise the check above would be indistinguishable from refusing everything."""
    executable = _writing(
        tmp_path, "polite", "import json\nprint(json.dumps({'state': 'verified'}))\n"
    )
    answer = conformance.subprocess_invoker(executable, "project_x:claude-code")("status", ())
    assert answer == {"state": "verified"}


def test_a_provider_that_never_answers_is_killed_and_raises_the_timeout(
    tmp_path: Path,
) -> None:
    """Driven through the helper, because the frozen limit is two minutes.

    The exception matters as much as the kill: `install apply` catches it and
    records `partial`, and a call that did not come back does not prove that
    nothing happened.
    """
    import os
    import subprocess

    marker = tmp_path / "woke-up"
    executable = _writing(
        tmp_path, "asleep", f"import time\ntime.sleep(30)\nopen({str(marker)!r}, 'w').write('x')\n"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        conformance._bounded_output(  # pyright: ignore[reportPrivateUsage]
            [executable, "status", "--target", "project_x:claude-code"],
            limit=protocol.BOUNDARY.output_limit_bytes,
            timeout_seconds=0.5,
            environment={"PATH": os.environ.get("PATH", "")},
        )
    assert not marker.exists(), "the child outlived its own time limit"


def test_the_provider_is_started_with_an_argument_array_and_not_a_string(
    tmp_path: Path,
) -> None:
    """A string command has to be split by something, and that something is a shell."""
    executable = _writing(
        tmp_path, "reporter", "import json, sys\nprint(json.dumps({'argv': sys.argv}))\n"
    )
    answer = conformance.subprocess_invoker(executable, "project_x:claude-code")("status", ())
    assert isinstance(answer, dict)
    argv = cast(list[str], answer["argv"])
    assert argv[1:] == ["status", "--target", "project_x:claude-code"]
