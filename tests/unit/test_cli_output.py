"""Two output modes, one envelope: machine stdout carries exactly one JSON object."""

import io
import json

from ai_stp_cli.errors import CliFailure, internal_failure, unknown_command
from ai_stp_cli.output import (
    new_request_id,
    render_failure,
    render_success,
    wants_machine_mode,
)
from ai_stp_contracts.machine_help import VersionReport

PAYLOAD = VersionReport(
    cli_version="1.2.3",
    python_version="3.12.13",
    contract_digest="sha256:" + "0" * 64,
)

#: The envelope enforces the typed-id pattern, so a placeholder will not do.
REQUEST_ID = new_request_id()


def test_machine_mode_is_recognised_from_argv_before_parsing() -> None:
    # Read from argv rather than from parsed options: an unknown flag aborts
    # parsing, and that is exactly when a machine caller needs its envelope.
    assert wants_machine_mode(["version", "--json"])
    assert wants_machine_mode(["--json", "version"])
    assert not wants_machine_mode(["version"])
    assert not wants_machine_mode(["version", "--jsonish"])


def test_a_success_is_one_json_line_with_the_payload_inside() -> None:
    stream = io.StringIO()
    render_success(PAYLOAD, machine=True, request_id=REQUEST_ID, stream=stream, next_actions=["d"])
    written = stream.getvalue()
    assert written.endswith("\n")
    assert written.count("\n") == 1
    envelope = json.loads(written)
    assert envelope["ok"] is True
    assert envelope["request_id"] == REQUEST_ID
    assert envelope["data"]["cli_version"] == "1.2.3"
    assert envelope["next_actions"] == ["d"]


def test_a_failure_is_one_json_line_and_returns_the_contract_exit_class() -> None:
    stream = io.StringIO()
    code = render_failure(
        CliFailure("AI_STP_NOT_FOUND", "nothing here", details={"path": "x"}),
        machine=True,
        request_id=REQUEST_ID,
        stream=stream,
    )
    envelope = json.loads(stream.getvalue())
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "AI_STP_NOT_FOUND"
    assert envelope["error"]["details"] == {"path": "x"}
    assert code == 2


def test_machine_output_carries_no_escape_sequences() -> None:
    stream = io.StringIO()
    render_success(PAYLOAD, machine=True, request_id=REQUEST_ID, stream=stream)
    assert "\x1b" not in stream.getvalue()


def test_human_success_is_plain_text_and_not_json() -> None:
    stream = io.StringIO()
    render_success(PAYLOAD, machine=False, request_id=REQUEST_ID, stream=stream)
    written = stream.getvalue()
    assert "cli_version: 1.2.3" in written
    assert not written.startswith("{")


def test_human_failure_prints_the_code_and_the_message() -> None:
    stream = io.StringIO()
    code = render_failure(
        CliFailure("AI_STP_VALIDATION_ERROR", "bad flag"),
        machine=False,
        request_id=REQUEST_ID,
        stream=stream,
    )
    assert stream.getvalue() == "AI_STP_VALIDATION_ERROR: bad flag\n"
    assert code == 2


def test_nested_and_empty_values_render_readably() -> None:
    stream = io.StringIO()
    render_success(
        _Nested(),
        machine=False,
        request_id=REQUEST_ID,
        stream=stream,
    )
    written = stream.getvalue()
    assert "flag: yes" in written
    assert "missing: -" in written
    assert "empty: -" in written
    assert "items:" in written
    assert "  name: a" in written


def test_every_request_id_is_new_and_typed() -> None:
    first, second = new_request_id(), new_request_id()
    assert first != second
    assert first.startswith("request_")


def test_an_internal_failure_names_the_type_and_leaks_nothing_else() -> None:
    # `SPEC-011` REQ-1108: an exception message may carry a path, an argument or
    # an environment value, so only the type is safe to publish.
    failure = internal_failure(ValueError("/home/someone/secret/token=abc"))
    assert failure.details == {"exception": "ValueError"}
    assert "secret" not in failure.message
    assert failure.exit_code == 70


def test_an_unknown_command_points_at_the_machine_registry() -> None:
    failure = unknown_command("No such command 'nope'.")
    assert failure.next_actions == ["help --agent --json"]
    assert failure.exit_code == 2


class _Nested(VersionReport):
    """A payload with the shapes the plain-text renderer has to handle."""

    cli_version: str = "1.0.0"
    python_version: str = "3.12.0"
    contract_digest: str = "sha256:" + "0" * 64
    flag: bool = True
    missing: str | None = None
    empty: list[str] = []  # noqa: RUF012
    items: list[dict[str, str]] = [{"name": "a"}]  # noqa: RUF012
