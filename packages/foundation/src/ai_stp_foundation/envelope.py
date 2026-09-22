"""Machine output envelope (docs/contracts/cli-json.md).

Machine mode prints exactly one JSON object. A warning never flips ``ok``;
a partial mutating operation returns an error envelope with an operation ID
instead of masking itself as a warning. Error codes are stable machine
identifiers of the form ``AI_STP_*``.

Wire constraints are regex patterns so generated schemas reject the same
values the Python models reject.

Compatibility is directional (docs/engineering/schema-evolution.md): producers
construct through the strict models and never emit unknown fields, while the
wire schema requires every declared field to be present yet tolerates unknown
optional additions within the supported major. Consumers parse through the
``*Reader`` variants, which ignore unknown optional fields instead of failing.
"""

import shlex
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.json_schema import JsonSchemaValue

from ai_stp_foundation.ids import stable_id_pattern

type RequestId = Annotated[str, Field(pattern=stable_id_pattern("request"))]
type OperationId = Annotated[str, Field(pattern=stable_id_pattern("operation"))]

#: Additive envelope fields introduced after the 1.0 required set. An older
#: producer omits them; the wire schema must still accept that document.
_ADDITIVE_OPTIONAL_FIELDS: frozenset[str] = frozenset({"continuations"})
_ADDITIVE_CONTINUATION_FIELDS: frozenset[str] = frozenset({"argv", "actor"})


type ContinuationActor = Literal["human", "agent", "cli", "external"]


def _open_wire_object(schema: JsonSchemaValue) -> None:
    """Envelope wire policy: declared 1.0 fields present, additions tolerated."""
    properties = schema.get("properties", {})
    schema["required"] = sorted(
        name for name in properties if name not in _ADDITIVE_OPTIONAL_FIELDS
    )
    schema["additionalProperties"] = True


def _open_continuation(schema: JsonSchemaValue) -> None:
    """Continuation wire: kind/path required; argv and actor are additive."""
    properties = schema.get("properties", {})
    schema["required"] = sorted(
        name
        for name in properties
        if name not in _ADDITIVE_CONTINUATION_FIELDS and name not in {"arguments", "missing"}
    )
    schema["additionalProperties"] = True


class Continuation(BaseModel):
    """One next step with bound values, and the names still missing.

    ``argv`` is the execution form. ``continuation_command`` is a quoted display
    string and is never eval input. ``next_actions`` remains that display string
    for older callers.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_open_continuation)

    kind: Literal["retry", "advance", "inspect", "blocked", "terminal"]
    path: Annotated[list[str], Field(min_length=1)]
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    argv: list[str] = Field(default_factory=list)
    actor: ContinuationActor = "cli"


def continuation_argv(item: Continuation) -> list[str]:
    """Executable tokens for one continuation, never passed through a shell."""
    if item.argv:
        return list(item.argv)
    if item.missing:
        return ["help", "--path", " ".join(item.path), "--json"]
    tokens = list(item.path)
    for name, value in item.arguments.items():
        tokens.extend(_argument_tokens(name, value))
    if "json" not in item.arguments:
        tokens.append("--json")
    return tokens


def bound_continuation(item: Continuation) -> Continuation:
    """Fill ``argv`` so a caller can exec the list without re-deriving it."""
    tokens = continuation_argv(item)
    if list(item.argv) == tokens:
        return item
    return item.model_copy(update={"argv": tokens})


def _argument_tokens(name: str, value: JsonValue) -> list[str]:
    flag = f"--{name}"
    if value == "" or value is True:
        return [flag]
    if value is False:
        return []
    if isinstance(value, list):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_flag_value(flag, str(item)))
        return tokens
    return _flag_value(flag, str(value))


def _flag_value(flag: str, text: str) -> list[str]:
    if text.startswith("-"):
        return [f"{flag}={text}"]
    return [flag, text]


def continuation_command(item: Continuation) -> str:
    """Quoted display of ``continuation_argv``. Not an eval input."""
    return " ".join(shlex.quote(token) for token in continuation_argv(item))


class CliError(BaseModel):
    """Typed error payload with a stable machine code."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_open_wire_object)

    code: Annotated[str, Field(pattern=r"^AI_STP_[A-Z0-9]+(_[A-Z0-9]+)*$")]
    message: str
    retryable: bool
    details: dict[str, JsonValue] = Field(default_factory=dict)


class SuccessEnvelope(BaseModel):
    """The single JSON object of a fully successful machine invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_open_wire_object)

    schema_version: Literal[1] = 1
    ok: Literal[True] = True
    request_id: RequestId
    operation_id: OperationId | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    continuations: list[Continuation] = Field(default_factory=list[Continuation])


class ErrorEnvelope(BaseModel):
    """The single JSON object of a failed or partial machine invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_open_wire_object)

    schema_version: Literal[1] = 1
    ok: Literal[False] = False
    request_id: RequestId
    operation_id: OperationId | None = None
    error: CliError
    next_actions: list[str] = Field(default_factory=list)
    continuations: list[Continuation] = Field(default_factory=list[Continuation])


class ContinuationReader(Continuation):
    """Compatible consumer parser for one continuation."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class CliErrorReader(CliError):
    """Compatible consumer parser for the error payload."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class SuccessEnvelopeReader(SuccessEnvelope):
    """Compatible consumer parser: unknown optional fields are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    continuations: list[ContinuationReader] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=list[ContinuationReader]
    )


class ErrorEnvelopeReader(ErrorEnvelope):
    """Compatible consumer parser: unknown optional fields are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    # Narrowing to the tolerant reader is safe: the models are frozen, so the
    # invariant-override concern about later widening writes does not apply.
    error: CliErrorReader  # pyright: ignore[reportIncompatibleVariableOverride]
    continuations: list[ContinuationReader] = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=list[ContinuationReader]
    )
