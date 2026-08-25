"""What the API says about itself must be true of the build that is running."""

from __future__ import annotations

from importlib.metadata import version as installed_version
from pathlib import Path

import pytest

from ai_stp_api.rate_limit import SlidingWindowLimiter
from ai_stp_api.settings import ServiceSettings


def test_the_advertised_version_is_the_installed_one() -> None:
    """`/v1/system/version` must not name a release that does not exist.

    The default used to be the literal `0.1.0` while every package in the
    workspace was `0.0.1`, so the deployed API advertised a version nothing had
    ever built — observed live at `https://nddev.asia/v1/system/version`.
    Nothing kept the two in step and no test compared them.
    """
    assert ServiceSettings().version == installed_version("ai-stp-api")


def test_no_environment_variable_can_contradict_the_installed_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The test above passed while production served the wrong number anyway.

    Removing the literal left the field on `env_prefix`, so
    `AI_STP_API_VERSION` still outranked the distribution — and
    `.env.prod.example` instructed the operator to set it, to the same dead
    `0.1.0` the fix had just deleted. Production answered `0.1.0` for another
    day while `importlib.metadata` inside that very container said `0.0.2`.

    The version of a running build is a fact of the build. Configuration that
    can disagree with it is a second source of truth for something that has
    one, so this asserts the environment is not consulted at all rather than
    that some particular value wins.
    """
    monkeypatch.setenv("AI_STP_API_VERSION", "0.1.0")
    assert ServiceSettings().version == installed_version("ai-stp-api")


def test_the_deployment_environment_file_does_not_name_a_version() -> None:
    """The instruction that caused it, removed where operators read it."""
    example = Path(__file__).resolve().parents[3] / ".env.prod.example"
    assert "AI_STP_API_VERSION" not in example.read_text(encoding="utf-8")


def test_the_rate_limit_does_not_fail_open_when_nobody_sets_it() -> None:
    """A missing variable left the public API with no limit at all.

    `SlidingWindowLimiter.allow` returns `True` unconditionally when `maximum`
    is `0`, and `0` was the default. So an environment that simply never
    mentioned `AI_STP_API_RATE_LIMIT_REQUESTS` got a limiter that admitted
    everything — the protection was opt-in, and absence looked identical to a
    deliberate decision to switch it off.

    Measured on the deployed environment before this change: 150 requests to
    `/v1/system/version` in one burst returned 150 x 200. After supplying the
    variable, the same burst returned 119 x 200 and 31 x 429.

    `0` stays a meaningful value — it is how a test or a local run turns the
    limiter off on purpose — but it now has to be asked for. Absence gets the
    single-node MVP policy `SPEC-010` names, which is the value the shipped
    `.env.prod.example` has carried all along.
    """
    service = ServiceSettings()

    assert service.rate_limit_requests == 120, "absence must not mean unlimited"
    assert SlidingWindowLimiter(
        maximum=service.rate_limit_requests,
        window_seconds=service.rate_limit_window_seconds,
        max_keys=service.rate_limit_max_keys,
    ).allow("probe"), "the default policy still admits a first request"


def test_zero_remains_the_explicit_way_to_turn_the_limiter_off() -> None:
    """Raising the default must not remove the opt-out it replaced."""
    limiter = SlidingWindowLimiter(maximum=0, window_seconds=60, max_keys=8)

    assert all(limiter.allow("probe") for _ in range(500))
