"""Rendering the two output modes (docs/contracts/cli-json.md, issue #72).

Machine mode prints exactly one JSON object and a trailing newline on stdout —
no colour, no escape sequence, no extra line. Human mode prints plain text.
There is no third mode and no partially machine-readable output: a caller that
has to guess which it received cannot parse either reliably.

Human output is deliberately plain. The agent is the primary consumer
(`docs/product/vision.md`), and a rendering library able to emit control
sequences would be one accident away from putting them on the stdout a machine
reads.
"""

import json
import sys
from typing import Final, TextIO, cast

from pydantic import BaseModel

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.envelope import CliError, ErrorEnvelope, SuccessEnvelope
from ai_stp_foundation.ids import new_id

#: The flag that selects machine mode. Recognised before the parser runs as
#: well, so a failure while parsing is still reported in the mode the caller
#: asked for rather than as library noise.
JSON_FLAG: Final[str] = "--json"


def wants_machine_mode(argv: list[str]) -> bool:
    """Whether this invocation asked for machine output.

    Read straight from argv rather than from parsed options: an unknown option
    aborts parsing, and that is exactly the moment a machine caller most needs
    its envelope instead of a usage message.
    """
    return JSON_FLAG in argv


def new_request_id() -> str:
    """One correlation id per invocation."""
    return new_id("request")


def render_success(
    payload: BaseModel,
    *,
    machine: bool,
    request_id: str,
    next_actions: list[str] | None = None,
    warnings: list[str] | None = None,
    stream: TextIO | None = None,
) -> None:
    """Write a successful result in the requested mode.

    A warning does not change `ok`: the caller asked for something and got it.
    It travels inside the one JSON object rather than on the error stream,
    because machine mode promises exactly one object on stdout and an empty
    stderr — a warning written to stderr would break the very contract that
    makes the output parseable. That is the channel `ADR-0058` uses to say a
    secret went to a file instead of the operating system store.
    """
    out = stream if stream is not None else sys.stdout
    data = cast(dict[str, JsonValue], payload.model_dump(mode="json"))
    if machine:
        envelope = SuccessEnvelope(
            request_id=request_id,
            data=data,
            warnings=warnings or [],
            next_actions=next_actions or [],
        )
        out.write(json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return
    for warning in warnings or []:
        out.write(f"warning: {warning}\n")
    out.write(_as_text(data) + "\n")


def render_failure(
    failure: CliFailure,
    *,
    machine: bool,
    request_id: str,
    stream: TextIO | None = None,
) -> int:
    """Write a failure and return the exit code the contract assigns it.

    A failure goes to stdout in machine mode, like a success: it is the result
    of the invocation, and a caller reading one stream must not have to merge
    two to learn the outcome. Only a crash before an envelope can be built uses
    the error stream, which is what `cli-json.md` reserves it for.
    """
    out = stream if stream is not None else (sys.stdout if machine else sys.stderr)
    if machine:
        envelope = ErrorEnvelope(
            request_id=request_id,
            error=CliError(
                code=failure.code,
                message=failure.message,
                retryable=failure.retryable,
                details=dict(failure.details),
            ),
            next_actions=failure.next_actions,
        )
        out.write(json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False) + "\n")
    else:
        out.write(f"{failure.code}: {failure.message}\n")
    return failure.exit_code


def _as_text(value: JsonValue, indent: int = 0) -> str:
    """Render a JSON-shaped value as flat, readable lines.

    Not a table and not a tree drawing: enough for a person to read an answer
    that was designed for a machine.
    """
    pad = "  " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, dict | list) and item:
                lines.append(f"{pad}{key}:")
                lines.append(_as_text(item, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        return "\n".join(_as_text(item, indent) for item in value)
    return f"{pad}{_scalar(value)}"


def _scalar(value: JsonValue) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list) and not value:
        return "-"
    return str(value)
