"""The shared `/v1` fixture corpus (issue #71).

One corpus, two consumers. The CLI drives its tests through a mock transport
built from these cases; the platform's contract tests replay the same cases
against a real implementation. If each side wrote its own examples they would
agree only by luck, and the first divergence would surface as a live bug rather
than a red test.

The corpus therefore ships **inside the package**, not under `tests/`: the
platform track imports `ai_stp_contracts.fixtures`, and a corpus it cannot
import is not shared.

Three kinds of case, because "negative" alone hides which side is at fault:

- `positive` — a request a conforming server answers with this exact response;
- `rejected_request` — a request a conforming server must refuse, with the
  stable error code it must answer;
- `invalid_response` — a body a conforming **client** must refuse. These are the
  ones that prove the CLI does not quietly accept a broken server, and they have
  no equivalent in a request-only corpus;
- `example` — a valid body that no request can select, because it depends on
  server state rather than on the call. Readiness is the case in point: the same
  probe answers `ready` or `not_ready` depending on the deployment, so the
  not-ready body must be validated without being replayable. Calling it
  `positive` would make the mock ambiguous and the corpus order-dependent.

Case content is language-neutral by rule: identifiers and tokens, never a
sentence in Russian or English. A fixture that reads as prose invites being
translated, and a translated fixture no longer matches the bytes it pins.
"""

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

CORPUS_DIR: Final[Path] = Path(__file__).parent / "v1"

type CaseKind = Literal["positive", "example", "rejected_request", "invalid_response"]


class FixtureRequest(BaseModel):
    """What the caller sends."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path_params: Mapping[str, str] = Field(default_factory=dict[str, str])
    query: Mapping[str, object] = Field(default_factory=dict[str, object])
    body: Mapping[str, object] | None = None
    headers: Mapping[str, str] = Field(default_factory=dict[str, str])


class FixtureCase(BaseModel):
    """One replayable exchange.

    `error_code` is required exactly for `rejected_request` and forbidden
    elsewhere: a rejection without its stable code would let two implementations
    fail differently and both look correct.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: Annotated[str, Field(pattern=r"^[a-zA-Z]+\.[a-zA-Z0-9-]+$")]
    operation_id: Annotated[str, Field(pattern=r"^[a-zA-Z]+$")]
    kind: CaseKind
    why: Annotated[str, Field(min_length=1)]
    request: FixtureRequest
    status: Annotated[int, Field(ge=100, le=599)]
    body: Mapping[str, object] | None = None
    error_code: str | None = None


class Corpus(BaseModel):
    """One corpus file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    cases: Annotated[list[FixtureCase], Field(min_length=1)]


@lru_cache(maxsize=1)
def load_cases() -> tuple[FixtureCase, ...]:
    """Every case of the corpus, ordered by case id."""
    cases: list[FixtureCase] = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        corpus = Corpus.model_validate_json(path.read_text(encoding="utf-8"))
        cases.extend(corpus.cases)
    return tuple(sorted(cases, key=lambda case: case.case_id))


def cases_of_kind(kind: CaseKind) -> tuple[FixtureCase, ...]:
    """Every case of one kind."""
    return tuple(case for case in load_cases() if case.kind == kind)


def case(case_id: str) -> FixtureCase:
    """One case by id."""
    for candidate in load_cases():
        if candidate.case_id == case_id:
            return candidate
    raise KeyError(f"unknown fixture case: {case_id!r}")
