"""The load probe must not call a live stack green when the limiter never trips."""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from ai_stp_api.errors import CATEGORY_CODE, ErrorCategory

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "probe_http_rate_limit.py"
_LIMITED = CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
Fetch = Callable[[str, float], tuple[int, dict[str, str], bytes]]


def _load() -> ModuleType:
    spec = spec_from_file_location("probe_http_rate_limit", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ok(status: int) -> tuple[int, dict[str, str], bytes]:
    return status, {}, b"{}"


def _limited(
    *,
    code: str = _LIMITED,
    retry_after: str | None = "3600",
) -> tuple[int, dict[str, str], bytes]:
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    body = json.dumps({"error": {"code": code}}).encode()
    return 429, headers, body


def _scripted(responses: list[tuple[int, dict[str, str], bytes]]) -> Fetch:
    leftover = iter(responses)

    def fetch(_url: str, _timeout: float) -> tuple[int, dict[str, str], bytes]:
        return next(leftover)

    return fetch


def _report(
    responses: list[tuple[int, dict[str, str], bytes]],
    *,
    expect_limit: int,
    slack: int = 1,
) -> dict[str, object]:
    module = _load()
    return module.probe(  # type: ignore[no-untyped-call]
        url="http://127.0.0.1:8000/v1/health/live",
        burst=len(responses),
        expect_limit=expect_limit,
        expect_code=_LIMITED,
        timeout=5.0,
        slack=slack,
        fetch=_scripted(responses),
    )


def test_probe_accepts_a_burst_that_trips_on_the_configured_cap() -> None:
    """Eight admitted then 429 is the isolated IP-window shape the docker probe expects."""
    cap = 8
    responses = [_ok(200)] * cap + [_limited()] * 4
    report = _report(responses, expect_limit=cap)
    assert report["ok"] is True
    assert report["admitted_200"] == cap
    assert report["limited_429"] == 4
    assert report["first_limited_at"] == cap + 1
    assert report["limited_code"] == _LIMITED
    assert report["retry_after"] == "3600"


def test_probe_accepts_one_stolen_slot_inside_slack() -> None:
    """A compose healthcheck sharing the budget must not fail a correct limiter."""
    cap = 8
    responses = [_ok(200)] * (cap - 1) + [_limited()] * 5
    report = _report(responses, expect_limit=cap, slack=1)
    assert report["ok"] is True
    assert report["admitted_200"] == cap - 1
    assert report["first_limited_at"] == cap


def test_probe_rejects_a_burst_that_never_trips() -> None:
    report = _report([_ok(200)] * 12, expect_limit=8)
    assert report["ok"] is False
    assert report["limited_429"] == 0
    assert report["first_limited_at"] is None


def test_probe_rejects_an_already_exhausted_budget() -> None:
    """All 429s would pass a one-sided 'did we see a 429' check."""
    report = _report([_limited()] * 12, expect_limit=8)
    assert report["ok"] is False
    assert report["admitted_200"] == 0
    assert report["first_limited_at"] == 1


def test_probe_rejects_a_429_without_the_contract_envelope() -> None:
    cap = 8
    wrong_code = CATEGORY_CODE[ErrorCategory.DEPENDENCY]
    bad_code = [_ok(200)] * cap + [_limited(code=wrong_code)] * 4
    assert _report(bad_code, expect_limit=cap)["ok"] is False
    missing_retry = [_ok(200)] * cap + [_limited(retry_after=None)] * 4
    assert _report(missing_retry, expect_limit=cap)["ok"] is False
