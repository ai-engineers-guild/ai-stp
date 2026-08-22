"""Which environments want the development fixture corpus, and which do not.

`REQ-2110` binds the first-party seed to its environment. It was written when
Sprint-1 had no validation pipeline and nothing real to publish, so the seed was
the catalogue. That era ended: the corpus is published through the ordinary
authenticated pipeline now, and a serving environment that also runs the seed
puts twenty-two invented objects — `fixture-component`, `river-*`,
`northwind-*` — on a public site beside the real ones.

Production did exactly that on every deploy, because `docker-compose.prod.yml`
runs the seed unconditionally.
"""

from __future__ import annotations

import pytest

from ai_stp_platform.seed_cli import fixtures_wanted


@pytest.mark.parametrize("environment", ["prod", "PROD", "staging", "preview"])
def test_a_named_environment_that_serves_people_gets_no_fixtures(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AI_STP_SEED_FIXTURES", raising=False)
    monkeypatch.setenv("AI_STP_API_ENVIRONMENT", environment)

    assert fixtures_wanted() is False


def test_development_still_gets_them(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without fixtures a fresh development catalogue is empty and unusable."""
    monkeypatch.delenv("AI_STP_SEED_FIXTURES", raising=False)
    monkeypatch.setenv("AI_STP_API_ENVIRONMENT", "dev")

    assert fixtures_wanted() is True


def test_an_unnamed_environment_is_treated_as_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A checkout with nothing set is somebody's machine, not a served site."""
    monkeypatch.delenv("AI_STP_SEED_FIXTURES", raising=False)
    monkeypatch.delenv("AI_STP_API_ENVIRONMENT", raising=False)

    assert fixtures_wanted() is True


@pytest.mark.parametrize(
    ("override", "wanted"),
    [("1", True), ("true", True), ("on", True), ("0", False), ("false", False), ("", False)],
)
def test_the_override_decides_in_either_direction(
    override: str, wanted: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A disposable environment calling itself `prod` is a real case.

    Guessing at it is not, so the override is read before the name and answers
    both ways — including switching fixtures *off* in a development checkout.
    """
    monkeypatch.setenv("AI_STP_API_ENVIRONMENT", "prod" if wanted else "dev")
    monkeypatch.setenv("AI_STP_SEED_FIXTURES", override)

    assert fixtures_wanted() is wanted
