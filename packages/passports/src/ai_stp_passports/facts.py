"""Facts with two independent axes (ADR-0021, docs/contracts/passport-envelope.md).

``origin`` records where a value came from; ``confirmation`` records whether
the user confirmed it. Confirmation never erases origin, and a materially
changed re-observation resets confirmation to ``none`` at the writing layer.
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ai_stp_foundation.timestamps import TIMESTAMP_PATTERN

type FactOrigin = Literal["declared", "observed", "derived", "imported"]
type FactConfirmation = Literal["none", "user_confirmed"]
type Timestamp = Annotated[str, Field(pattern=TIMESTAMP_PATTERN)]

# The contract bounds source_refs without fixing a number; this is the chosen
# implementation bound, shared with the generated schema.
MAX_SOURCE_REFS: Final[int] = 16


class Fact(BaseModel):
    """One passport fact: value, provenance axes and bounded source links."""

    model_config = ConfigDict(extra="allow", frozen=True)

    value: JsonValue
    origin: FactOrigin
    confirmation: FactConfirmation
    source_refs: Annotated[list[str], Field(max_length=MAX_SOURCE_REFS)] = Field(
        default_factory=list
    )
    observed_at: Timestamp | None = None
    confirmed_at: Timestamp | None = None
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = None

    @model_validator(mode="after")
    def _consistent_axes(self) -> "Fact":
        if self.confirmation == "none" and self.confirmed_at is not None:
            raise ValueError("confirmed_at requires confirmation user_confirmed")
        if self.confidence is not None and self.origin != "observed":
            raise ValueError("confidence is allowed only for observed facts")
        return self
