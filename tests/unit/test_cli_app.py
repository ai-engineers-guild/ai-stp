"""Dispatch: every way an invocation ends maps to a registered code and exit class."""

import io
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, cast

import click
import pytest
from pydantic import BaseModel, Field, ValidationError

from ai_stp_cli import app
from ai_stp_cli.errors import invalid_parameters


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = app.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _envelope(out: str) -> dict[str, object]:
    assert out.count("\n") == 1, out
    return json.loads(out)


@pytest.mark.parametrize(
    "argv",
    [
        ["version"],
        ["doctor"],
        ["capabilities"],
        ["config", "show"],
        ["help", "--agent"],
    ],
)
def test_every_command_succeeds_in_both_modes(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 0
    assert out and not err

    code, out, err = _run([*argv, "--json"], capsys)
    assert code == 0
    assert not err
    assert _envelope(out)["ok"] is True


def test_the_flag_may_be_written_before_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run(["--json", "config", "show"], capsys)
    assert code == 0
    assert _envelope(out)["ok"] is True


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--json"], "no command given"),
        (["registry", "show", "--json"], "Missing option"),
        (["nope", "--json"], "No such command"),
        (["version", "--nosuch", "--json"], "No such option"),
        (["config", "--json"], "Missing command"),
        (["--help", "--json"], "usage text is not machine readable"),
    ],
)
def test_a_refused_invocation_is_a_validation_error_with_exit_class_two(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    if "--json" in argv:
        envelope = _envelope(out)
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
        assert message in envelope["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]
        assert not err
    else:
        assert message in err
        assert not out


def test_a_machine_failure_goes_to_stdout_so_one_stream_carries_the_outcome(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A caller reading stdout must not have to merge stderr to learn what
    # happened. Only a crash before an envelope exists uses the error stream.
    code, out, err = _run(["nope", "--json"], capsys)
    assert code == 2
    assert json.loads(out)["ok"] is False
    assert err == ""


def test_target_readiness_rejects_environment_values_without_leaking_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "this-must-never-appear"
    code, out, err = _run(
        [
            "target",
            "status",
            "--project",
            "project_test",
            "--harness",
            "claude-code",
            "--requires-env",
            f"OPENAI_API_KEY={secret}",
            "--json",
        ],
        capsys,
    )

    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
    assert secret not in out


def test_a_human_failure_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(["nope"], capsys)
    assert code == 2
    assert out == ""
    assert err.startswith("AI_STP_VALIDATION_ERROR: ")


def test_human_help_is_click_s_own_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run(["--help"], capsys)
    assert code == 0
    assert "Usage: ai-stp" in out
    assert "--json" in out


def test_an_empty_human_invocation_opens_first_run_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run([], capsys)
    assert code == 0
    assert err == ""
    assert "Usage: ai-stp" in out
    assert "ai-stp doctor --json" in out
    assert "ai-stp help --agent --json" in out


def test_auth_help_teaches_both_supported_login_flows(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(["auth", "--help"], capsys)
    assert code == 0
    assert err == ""
    assert "ai-stp auth login --provider google" in out
    assert "ai-stp auth login --provider github" in out
    assert "ai-stp auth complete" in out
    assert "ai-stp auth status" in out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["auth", "login"], "requires --provider with google or github"),
        (["auth", "login", "--google"], "requires --provider with google or github"),
        (
            ["auth", "login", "--provider", "gitlab"],
            "invalid auth provider; expected google or github",
        ),
        (["auth", "google", "login"], "auth commands start with 'auth login'"),
    ],
)
def test_common_auth_spelling_errors_explain_the_exact_correction(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(argv, capsys)
    assert code == 2
    assert out == ""
    assert message in err

    code, out, err = _run([*argv, "--json"], capsys)
    assert code == 2
    assert err == ""
    envelope = _envelope(out)
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]
    assert message in envelope["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]
    assert envelope["next_actions"] == [  # pyright: ignore[reportIndexIssue]
        "auth login --provider google --json",
        "auth login --provider github --json",
    ]


def test_an_unexpected_exception_becomes_the_internal_class_and_leaks_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("/home/someone/.config/token=abc")

    monkeypatch.setattr(app, "build_group", explode)
    code, out, _err = _run(["version", "--json"], capsys)
    assert code == 70
    envelope = _envelope(out)
    assert envelope["error"]["code"] == "AI_STP_INTERNAL"  # pyright: ignore[reportIndexIssue]
    assert envelope["error"]["details"] == {"exception": "RuntimeError"}  # pyright: ignore[reportIndexIssue]
    assert "token" not in out


@pytest.mark.parametrize("error", [KeyboardInterrupt, click.Abort])
def test_an_interruption_is_the_shell_s_convention_and_not_an_internal_failure(
    error: type[BaseException], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(app, "build_group", interrupt)
    assert app.main(["version"]) == 130


def test_every_invocation_carries_its_own_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    first = _envelope(_run(["version", "--json"], capsys)[1])["request_id"]
    second = _envelope(_run(["version", "--json"], capsys)[1])["request_id"]
    assert first != second


def test_the_console_entrypoint_exits_with_the_dispatch_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ai-stp", "nope"])
    with pytest.raises(SystemExit) as raised:
        app.run()
    assert raised.value.code == 2


def test_a_valued_option_reaches_its_handler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A declared parameter that is neither a flag nor required takes the branch
    # `_require_declared_flags` skips, and its value has to arrive intact.
    from ai_stp_cli.answer import Answer
    from ai_stp_cli.registry import COMMANDS, Command
    from ai_stp_contracts.machine_help import CommandParameter, VersionReport

    seen: dict[str, object] = {}

    def handler(parameters: Mapping[str, object]) -> Answer[VersionReport]:
        seen.update(parameters)
        return Answer(VersionReport(cli_version="9.9.9", python_version="3.12.0"))

    descriptor = COMMANDS[0].descriptor.model_copy(
        update={
            "path": ["probe"],
            "parameters": [
                CommandParameter(
                    name="thing",
                    kind="option",
                    value_type="string",
                    required=False,
                    repeatable=False,
                    summary="A declared value.",
                )
            ],
        }
    )
    # The handler is named rather than referenced, so the stub is installed
    # where the name resolves rather than passed in.
    from ai_stp_cli.commands import version as version_command

    monkeypatch.setattr(version_command, "run", handler)
    monkeypatch.setattr(app, "COMMANDS", (Command(descriptor, "version:run"),))

    code, out, _err = _run(["probe", "--thing", "value", "--json"], capsys)
    assert code == 0
    assert seen == {"thing": "value"}
    assert _envelope(out)["data"]["cli_version"] == "9.9.9"  # pyright: ignore[reportIndexIssue]


def test_a_hyphenated_option_reaches_its_handler_under_its_declared_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The declared name is the one the handler asks for, hyphens and all.

    Click derives its own key from the flag it parsed, so `--two-words` arrives
    as `two_words` while `registry.py` — the owner of the name, and the one
    machine help publishes — calls it `two-words`. A handler asking for the
    declared name would find nothing, and finding nothing is exactly what an
    omitted option looks like: the command would not fail, it would quietly do
    something else. This goes through real Click so that the assertion is about
    what Click does rather than about what we assume it does.
    """
    from ai_stp_cli.answer import Answer
    from ai_stp_cli.registry import COMMANDS, Command
    from ai_stp_contracts.machine_help import CommandParameter, VersionReport

    seen: dict[str, object] = {}

    def handler(parameters: Mapping[str, object]) -> Answer[VersionReport]:
        seen.update(parameters)
        return Answer(VersionReport(cli_version="9.9.9", python_version="3.12.0"))

    descriptor = COMMANDS[0].descriptor.model_copy(
        update={
            "path": ["probe"],
            "parameters": [
                CommandParameter(
                    name="two-words",
                    kind="option",
                    value_type="string",
                    required=False,
                    repeatable=False,
                    summary="A declared value whose name has a hyphen.",
                )
            ],
        }
    )
    # The handler is named rather than referenced, so the stub is installed
    # where the name resolves rather than passed in.
    from ai_stp_cli.commands import version as version_command

    monkeypatch.setattr(version_command, "run", handler)
    monkeypatch.setattr(app, "COMMANDS", (Command(descriptor, "version:run"),))

    code, _out, _err = _run(["probe", "--two-words", "value", "--json"], capsys)
    assert code == 0
    assert seen == {"two-words": "value"}


def test_a_required_hyphenated_boolean_is_checked_under_its_declared_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ai_stp_cli.answer import Answer
    from ai_stp_cli.registry import COMMANDS, Command
    from ai_stp_contracts.machine_help import CommandParameter, VersionReport

    def handler(_parameters: Mapping[str, object]) -> Answer[VersionReport]:
        return Answer(VersionReport(cli_version="9.9.9", python_version="3.12.0"))

    descriptor = COMMANDS[0].descriptor.model_copy(
        update={
            "path": ["probe"],
            "parameters": [
                CommandParameter(
                    name="for-publication",
                    kind="option",
                    value_type="boolean",
                    required=True,
                    repeatable=False,
                    summary="Select one explicit validation profile.",
                )
            ],
        }
    )
    # The handler is named rather than referenced, so the stub is installed
    # where the name resolves rather than passed in.
    from ai_stp_cli.commands import version as version_command

    monkeypatch.setattr(version_command, "run", handler)
    monkeypatch.setattr(app, "COMMANDS", (Command(descriptor, "version:run"),))

    assert _run(["probe", "--for-publication", "--json"], capsys)[0] == 0
    code, out, _err = _run(["probe", "--json"], capsys)
    assert code == 2
    assert _envelope(out)["error"]["code"] == "AI_STP_VALIDATION_ERROR"  # pyright: ignore[reportIndexIssue]


def test_every_declared_option_arrives_under_the_name_it_was_declared_with() -> None:
    """Swept over the real registry, because one worked and ten did not.

    `--plan-digest` was read as `plan-digest` and delivered as `plan_digest`,
    which made an approved plan unreachable from the command line; one other
    option had the mismatch the other way round and happened to work. Neither
    is visible from reading a single command, so this asks all of them.
    """
    from ai_stp_cli.registry import COMMANDS

    for command in COMMANDS:
        parameters = command.descriptor.parameters
        # Keyed the way Click keys them, which the test above pins to reality.
        given = {item.name.replace("-", "_"): f"value of {item.name}" for item in parameters}
        arrived = app._as_declared(command, given)  # pyright: ignore[reportPrivateUsage]
        for item in parameters:
            assert arrived.get(item.name) == f"value of {item.name}", (
                f"{' '.join(command.descriptor.path)} --{item.name}"
            )


#: Declared parameters no handler reads, each for a stated reason. An entry here
#: is a claim; the test below is what keeps it honest.
UNREAD_BY_DESIGN: dict[str, str] = {
    "help --agent": "names the caller; the registry is the command's only answer either way",
    "component passport validate --for-publication": (
        "names the only profile the command has; accepted so an older spelling still parses"
    ),
}


def _handler_sources(handler: Callable[..., object]) -> str:
    """The handler's module and the `ai_stp_cli` modules it imports, as text."""
    import inspect
    import sys

    place = inspect.getsourcefile(handler)
    if place is None:
        return ""
    text = Path(place).read_text("utf-8")
    module = sys.modules.get(getattr(handler, "__module__", ""))
    for value in vars(module or object()).values():
        name = getattr(value, "__name__", "")
        if not name.startswith("ai_stp_cli"):
            continue
        nested = getattr(value, "__file__", None)
        if nested:
            text += Path(nested).read_text("utf-8")
    return text


def test_every_declared_option_is_read_by_the_handler_that_declares_it() -> None:
    """A declared option nobody reads does nothing, and says nothing about it.

    From the outside this is indistinguishable from the hyphen mismatch that
    made ten options dead: the command accepts the flag, exits zero and ignores
    it. `_as_declared` fixes how a name *arrives*; this asks whether anybody is
    there to receive it.

    Matched on the quoted name rather than on one access shape — handlers read
    through `parameters.get`, `parameters[...]` and a shared
    `_required(parameters, name)` helper, and a check that knew only the first
    would fail seven honest commands.

    Read across one level of delegation, not the handler's file alone. When the
    release-trust helpers moved out of `commands.install` so the harness program
    path could stop spawning providers it had not verified, three options that
    `install plan` genuinely reads went unread here — the reader had moved one
    import away. Following the `ai_stp_cli` modules a handler imports keeps the
    question "is anybody receiving this" answerable when the answer is a shared
    module, without naming that module and turning a mechanism into a list.
    """

    from ai_stp_cli.registry import COMMANDS

    unread: list[str] = []
    for command in COMMANDS:
        source = _handler_sources(command.handler)
        for parameter in command.descriptor.parameters:
            named = f'"{parameter.name}"' in source or f"'{parameter.name}'" in source
            if not named:
                unread.append(f"{' '.join(command.descriptor.path)} --{parameter.name}")

    assert sorted(unread) == sorted(UNREAD_BY_DESIGN), f"declared and unread: {sorted(unread)}"


def test_every_exemption_names_a_parameter_that_exists() -> None:
    """An exemption for a parameter nobody declares hides the next real one."""
    from ai_stp_cli.registry import COMMANDS

    declared = {
        f"{' '.join(command.descriptor.path)} --{parameter.name}"
        for command in COMMANDS
        for parameter in command.descriptor.parameters
    }
    assert set(UNREAD_BY_DESIGN) <= declared


def test_an_override_travels_from_the_command_line_into_the_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _err = _run(
        [
            "config",
            "show",
            "--set",
            "search.result_limit=7",
            "--set",
            "sync.enabled=true",
            "--json",
        ],
        capsys,
    )
    assert code == 0
    data = cast(dict[str, list[dict[str, object]]], _envelope(out)["data"])
    values = {str(item["path"]): item for item in data["values"]}
    assert values["search.result_limit"]["value"] == 7
    assert values["search.result_limit"]["source"] == "command_argument"
    assert values["sync.enabled"]["value"] is True


def test_a_malformed_override_is_refused_rather_than_ignored(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _err = _run(["config", "show", "--set", "search.result_limit", "--json"], capsys)
    assert code == 2
    assert "path=value" in _envelope(out)["error"]["message"]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]


def test_a_missing_confirmation_is_a_decision_not_a_validation_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _err = _run(["device", "reset", "--json"], capsys)
    assert code == 4
    envelope = _envelope(out)
    assert envelope["error"]["code"] == "AI_STP_USER_DECISION_REQUIRED"  # pyright: ignore[reportIndexIssue]
    assert envelope["next_actions"] == ["device reset --confirm --json"]


def test_a_fallback_warning_reaches_the_envelope_and_leaves_ok_true(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A warning does not make the call unsuccessful, and it must not go to
    # stderr: machine mode promises one object on stdout and an empty stderr.
    code, out, err = _run(["device", "init", "--json"], capsys)
    assert code == 0
    assert err == ""
    envelope = _envelope(out)
    assert envelope["ok"] is True
    assert envelope["warnings"] and "owner-only file" in envelope["warnings"][0]  # pyright: ignore[reportIndexIssue, reportOperatorIssue]


def test_a_warning_is_visible_in_human_mode_too(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run(["device", "init"], capsys)
    assert code == 0
    assert out.startswith("warning: ")


def test_a_refused_parameter_is_a_validation_error_not_an_internal_one() -> None:
    """A request model refusing a caller's value is bad input, not a fault.

    `registry search --query ""` answered `AI_STP_INTERNAL: unexpected internal
    failure` with an empty `next_actions`, because pydantic's `ValidationError`
    reached the generic handler. That tells an agent the CLI is broken when the
    truth is that `q` may not be empty.
    """

    class Request(BaseModel):
        q: Annotated[str, Field(min_length=1)]

    try:
        Request(q="")
    except ValidationError as error:
        failure = invalid_parameters(error)
    else:  # pragma: no cover - the model must refuse an empty value
        raise AssertionError("the model accepted an empty value")

    assert failure.code == "AI_STP_VALIDATION_ERROR"
    assert failure.details == {"fields": "q"}
    assert failure.next_actions == ["help --agent --json"]


def test_a_refused_value_never_reaches_the_message_or_details() -> None:
    """`SPEC-011` REQ-1108: a caller's value may be the credential they mistyped."""
    secret = "sk-live-must-never-appear"

    class Request(BaseModel):
        token: Annotated[str, Field(max_length=4)]

    try:
        Request(token=secret)
    except ValidationError as error:
        failure = invalid_parameters(error)
    else:  # pragma: no cover - the model must refuse an over-long value
        raise AssertionError("the model accepted an over-long value")

    assert secret not in failure.message
    assert secret not in str(failure.details)
    assert failure.details == {"fields": "token"}


def test_output_survives_a_stream_that_defaults_to_a_legacy_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Machine mode emits real characters, so the stream has to accept them.

    JSON is written with `ensure_ascii=False` on purpose: a passport carries the
    characters its author wrote rather than their escapes. On a host whose
    standard streams default to a legacy code page — Windows, before UTF-8 mode
    became the interpreter default — that write raises `UnicodeEncodeError` and
    the invocation dies inside its own success path, reporting an internal
    failure that says nothing about encoding.

    Measured rather than imagined: `toolchain profile` exited 70 with
    `details.exception = UnicodeEncodeError` on `windows-latest` while passing
    on Linux and macOS, which is what a cross-platform CI is for.
    """
    raw = io.BytesIO()
    legacy = io.TextIOWrapper(raw, encoding="cp1252", newline="")
    monkeypatch.setattr(sys, "stdout", legacy)

    code = app.main(["toolchain", "profile", "--json"])
    legacy.flush()

    assert code == 0
    written = raw.getvalue()
    assert written, "the command wrote nothing"
    # Decodes as UTF-8, which cp1252 output would not.
    envelope = json.loads(written.decode("utf-8"))
    assert envelope["ok"] is True


def test_a_damaged_registry_is_named_not_reported_as_an_internal_fault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Corruption of the local store is the operator's state, not our bug.

    Measured: a registry file truncated mid-byte answered every read and write
    with `AI_STP_INTERNAL: unexpected internal failure` — no file named, no
    hint that local state (not the tool) is damaged, and `internal` telling an
    agent to retry the same dead end. sqlite reports this as its own error
    class; the answer must carry the registry path and read as state to
    reconcile.
    """
    from ai_stp_cli.local.database import configured_path

    place = configured_path()
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_bytes(b"this is not a database, and it is short")

    code = app.main(["component", "find", "--prefix", "component", "--json"])
    answer = json.loads(capsys.readouterr().out)

    assert answer["ok"] is False
    assert answer["error"]["code"] == "AI_STP_PRECONDITION_FAILED"
    assert "registry" in answer["error"]["details"]
    assert code == 4
