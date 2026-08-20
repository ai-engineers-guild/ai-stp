"""Facts: two independent axes, bounded refs, consistent optional fields.

`SPEC-003` REQ-303: origin is `declared`, `observed`, `derived` or `imported`
and confirmation is `none` or `user_confirmed`, as two axes that do not derive
from one another, alongside bounded source references and the observation and
confirmation times.
"""

import pytest
from pydantic import ValidationError

from ai_stp_passports import Fact


def test_observed_fact_with_confidence_and_confirmation() -> None:
    fact = Fact(
        value="Python 3.12",
        origin="observed",
        confirmation="user_confirmed",
        source_refs=["pyproject.toml"],
        observed_at="2026-08-05T10:00:00.000Z",
        confirmed_at="2026-08-05T10:05:00.000Z",
        confidence=0.9,
    )
    assert fact.origin == "observed"


def test_confirmed_at_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        Fact(
            value=1,
            origin="declared",
            confirmation="none",
            confirmed_at="2026-08-05T10:05:00.000Z",
        )


def test_confidence_is_only_for_observed() -> None:
    with pytest.raises(ValidationError):
        Fact(value=1, origin="declared", confirmation="none", confidence=0.5)


def test_source_refs_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Fact(
            value=1,
            origin="observed",
            confirmation="none",
            source_refs=[f"ref-{index}" for index in range(17)],
        )


@pytest.mark.parametrize("bad_origin", ["inferred", "guessed", ""])
def test_unknown_origin_fails_closed(bad_origin: str) -> None:
    with pytest.raises(ValidationError):
        Fact.model_validate({"value": 1, "origin": bad_origin, "confirmation": "none"})
