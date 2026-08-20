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

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.json_schema import JsonSchemaValue

from ai_stp_foundation.ids import stable_id_pattern

type RequestId = Annotated[str, Field(pattern=stable_id_pattern("request"))]
type OperationId = Annotated[str, Field(pattern=stable_id_pattern("operation"))]


def _open_wire_object(schema: JsonSchemaValue) -> None:
    """Envelope wire policy: all declared fields present, additions tolerated."""
    properties = schema.get("properties", {})
    schema["required"] = sorted(properties)
    schema["additionalProperties"] = True


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


class ErrorEnvelope(BaseModel):
    """The single JSON object of a failed or partial machine invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_open_wire_object)

    schema_version: Literal[1] = 1
    ok: Literal[False] = False
    request_id: RequestId
    operation_id: OperationId | None = None
    error: CliError
    next_actions: list[str] = Field(default_factory=list)


class CliErrorReader(CliError):
    """Compatible consumer parser for the error payload."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class SuccessEnvelopeReader(SuccessEnvelope):
    """Compatible consumer parser: unknown optional fields are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class ErrorEnvelopeReader(ErrorEnvelope):
    """Compatible consumer parser: unknown optional fields are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    # Narrowing to the tolerant reader is safe: the models are frozen, so the
    # invariant-override concern about later widening writes does not apply.
    error: CliErrorReader  # pyright: ignore[reportIncompatibleVariableOverride]
