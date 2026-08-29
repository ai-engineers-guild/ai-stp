"""What the API says about itself must be true of the build that is running."""

from __future__ import annotations

from importlib.metadata import version as installed_version
from pathlib import Path

import pytest

from ai_stp_api.rate_limit import SlidingWindowLimiter, build_http_rate_gate
from ai_stp_api.settings import (
    RATE_LIMIT_IP_REQUESTS,
    RATE_LIMIT_IP_WINDOW_SECONDS,
    RATE_LIMIT_MAX_KEYS,
    RATE_LIMIT_OVERALL_REQUESTS,
    RATE_LIMIT_OVERALL_WINDOW_SECONDS,
    ServiceSettings,
)

_ROOT = Path(__file__).resolve().parents[3]


def _assignment_map(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key] = value
    return values


def _documented_rate_limit_policy() -> dict[str, str]:
    return {
        "AI_STP_API_RATE_LIMIT_OVERALL_REQUESTS": str(RATE_LIMIT_OVERALL_REQUESTS),
        "AI_STP_API_RATE_LIMIT_OVERALL_WINDOW_SECONDS": str(RATE_LIMIT_OVERALL_WINDOW_SECONDS),
        "AI_STP_API_RATE_LIMIT_IP_REQUESTS": str(RATE_LIMIT_IP_REQUESTS),
        "AI_STP_API_RATE_LIMIT_IP_WINDOW_SECONDS": str(RATE_LIMIT_IP_WINDOW_SECONDS),
        "AI_STP_API_RATE_LIMIT_MAX_KEYS": str(RATE_LIMIT_MAX_KEYS),
    }


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
    example = _ROOT / ".env.prod.example"
    assert "AI_STP_API_VERSION" not in example.read_text(encoding="utf-8")


def test_dev_and_prod_env_examples_name_the_dual_window_policy() -> None:
    """Operators copy these files; a missing key leaves them on a silent default."""
    expected = _documented_rate_limit_policy()
    for name in (".env.dev.example", ".env.prod.example"):
        values = _assignment_map(_ROOT / name)
        missing = {key: expected[key] for key in expected if values.get(key) != expected[key]}
        assert not missing, f"{name} disagrees with ServiceSettings defaults: {missing}"
        assert "AI_STP_API_RATE_LIMIT_REQUESTS" not in values
        assert "AI_STP_API_RATE_LIMIT_WINDOW_SECONDS" not in values


def test_dev_compose_names_the_dual_window_policy() -> None:
    """The self-contained stack has no .env.dev; the policy still has to be named."""
    text = (_ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
    for key, value in _documented_rate_limit_policy().items():
        needle = f'{key}: "{value}"'
        assert needle in text, needle


def test_service_settings_read_the_documented_env_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A renamed env key would leave compose and the examples talking to nobody."""
    monkeypatch.setenv("AI_STP_API_RATE_LIMIT_OVERALL_REQUESTS", "7")
    monkeypatch.setenv("AI_STP_API_RATE_LIMIT_OVERALL_WINDOW_SECONDS", "9")
    monkeypatch.setenv("AI_STP_API_RATE_LIMIT_IP_REQUESTS", "11")
    monkeypatch.setenv("AI_STP_API_RATE_LIMIT_IP_WINDOW_SECONDS", "13")
    monkeypatch.setenv("AI_STP_API_RATE_LIMIT_MAX_KEYS", "17")
    service = ServiceSettings()
    assert service.rate_limit_overall_requests == 7
    assert service.rate_limit_overall_window_seconds == 9
    assert service.rate_limit_ip_requests == 11
    assert service.rate_limit_ip_window_seconds == 13
    assert service.rate_limit_max_keys == 17


def test_the_rate_limit_does_not_fail_open_when_nobody_sets_it() -> None:
    """A missing variable left the public API with no limit at all.

    `SlidingWindowLimiter.allow` returns `True` unconditionally when `maximum`
    is `0`, and `0` was the default. So an environment that simply never
    mentioned the rate-limit variables got a limiter that admitted everything —
    the protection was opt-in, and absence looked identical to a deliberate
    decision to switch it off.

    Measured on the deployed environment before the first fail-closed default:
    150 requests to `/v1/system/version` in one burst returned 150 x 200.

    `0` stays a meaningful value — it is how a test or a local run turns a
    dimension off on purpose — but it now has to be asked for. Absence gets the
    two-window policy `SPEC-010` `REQ-1015` names.
    """
    service = ServiceSettings()
    assert service.rate_limit_overall_requests == RATE_LIMIT_OVERALL_REQUESTS
    assert service.rate_limit_overall_window_seconds == RATE_LIMIT_OVERALL_WINDOW_SECONDS
    assert service.rate_limit_ip_requests == RATE_LIMIT_IP_REQUESTS
    assert service.rate_limit_ip_window_seconds == RATE_LIMIT_IP_WINDOW_SECONDS

    gate = build_http_rate_gate(
        overall_requests=service.rate_limit_overall_requests,
        overall_window_seconds=service.rate_limit_overall_window_seconds,
        ip_requests=service.rate_limit_ip_requests,
        ip_window_seconds=service.rate_limit_ip_window_seconds,
        max_keys=service.rate_limit_max_keys,
    )
    assert gate.allow("probe", now=0), "the default policy still admits a first request"
    for index in range(1, service.rate_limit_overall_requests):
        assert gate.allow(f"peer-{index}", now=0)
    assert not gate.allow("overflow", now=0)

    hourly = build_http_rate_gate(
        overall_requests=service.rate_limit_overall_requests,
        overall_window_seconds=service.rate_limit_overall_window_seconds,
        ip_requests=service.rate_limit_ip_requests,
        ip_window_seconds=service.rate_limit_ip_window_seconds,
        max_keys=service.rate_limit_max_keys,
    )
    step = service.rate_limit_ip_window_seconds / service.rate_limit_ip_requests
    for index in range(service.rate_limit_ip_requests):
        assert hourly.allow("one", now=index * step)
    assert not hourly.allow("one", now=(service.rate_limit_ip_requests - 1) * step + 1)


def test_retired_rate_limit_env_does_not_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """The old single-window name is not an alias; leftover `0` must not disable."""
    monkeypatch.setenv("AI_STP_API_RATE_LIMIT_REQUESTS", "0")
    monkeypatch.setenv("AI_STP_API_RATE_LIMIT_WINDOW_SECONDS", "1")
    service = ServiceSettings()
    assert service.rate_limit_overall_requests == RATE_LIMIT_OVERALL_REQUESTS
    assert service.rate_limit_ip_requests == RATE_LIMIT_IP_REQUESTS


def test_zero_remains_the_explicit_way_to_turn_the_limiter_off() -> None:
    """Raising the default must not remove the opt-out it replaced."""
    limiter = SlidingWindowLimiter(maximum=0, window_seconds=60, max_keys=8)

    assert all(limiter.allow("probe") for _ in range(500))

    gate = build_http_rate_gate(
        overall_requests=0,
        overall_window_seconds=60,
        ip_requests=0,
        ip_window_seconds=3600,
        max_keys=8,
    )
    assert all(gate.allow("probe", now=float(index)) for index in range(500))
