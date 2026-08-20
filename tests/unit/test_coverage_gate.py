"""The coverage gate must compare at the precision it claims.

A threshold is a promise about a number. `coverage` keeps that promise only to
the precision it was configured with, and its default silently widens the gate
by half a point — a run then prints its own failure and exits zero. The tests
here pin the configuration that closes that gap, and state the mechanism
executably so a change in `coverage` fails here rather than in a release.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from coverage.results import should_fail_under

ROOT = Path(__file__).resolve().parents[2]


def _pyproject() -> dict[str, Any]:
    """The parsed manifest. Callers narrow to a scalar, never to another table.

    Narrowing an indexed value to `int` or `str` is exact; narrowing it to
    `dict` would only produce a table of unknowns and buy nothing here.
    """
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_coverage_compares_a_rounded_total() -> None:
    """The premise of the whole gate, stated where it can fail.

    `should_fail_under` evaluates `round(total, precision) < fail_under`, so at
    precision zero a gate of 95 admits anything from 94.5 up. This is not a
    hypothetical: `letya999@6a41c28` measured 94.55% in CI, printed
    `FAIL Required test coverage of 95% not reached`, and reported success at
    step, job and run level.
    """
    assert should_fail_under(94.55, 95, 0) is False
    assert should_fail_under(94.55, 95, 2) is True
    # The band is exactly the rounding interval, not an arbitrary tolerance.
    assert should_fail_under(94.49, 95, 0) is True


def test_the_repository_pins_a_precision_that_makes_the_threshold_mean_itself() -> None:
    precision = _pyproject()["tool"]["coverage"]["report"]["precision"]
    assert isinstance(precision, int)
    # Two decimals narrow the blind band from half a point to 0.005. Zero would
    # restore the defect; the value is a floor, not an exact match, so raising
    # it stays allowed.
    assert precision >= 2


def test_the_recipe_rereads_the_recorded_data_with_an_explicit_precision() -> None:
    """`pytest`'s exit code is not the only thing the gate rests on.

    The second call reads the data that was actually written and refuses on its
    own. It carries `--precision` explicitly because a bare `--fail-under`
    would inherit the same default that caused the incident.
    """
    recipe = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "coverage report --precision=2 --fail-under=90" in recipe

    addopts = _pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert isinstance(addopts, str)
    assert "--cov-fail-under=90" in addopts
