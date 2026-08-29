"""Probe a live HTTP rate limiter with a sequential burst.

Stdlib only: run against a local docker API without the workspace venv.

  python scripts/probe_http_rate_limit.py \\
      --url http://127.0.0.1:8000/v1/health/live \\
      --burst 110 --expect-limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

Fetch = Callable[[str, float], tuple[int, dict[str, str], bytes]]


def _get(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return int(response.status), headers, response.read()
    except urllib.error.HTTPError as error:
        headers = {key.lower(): value for key, value in error.headers.items()}
        return int(error.code), headers, error.read()


def _error_code(body: bytes) -> str | None:
    try:
        payload: Any = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def probe(
    *,
    url: str,
    burst: int,
    expect_limit: int,
    expect_code: str,
    timeout: float,
    slack: int,
    fetch: Fetch | None = None,
) -> dict[str, Any]:
    get = _get if fetch is None else fetch
    statuses: list[int] = []
    first_limited: int | None = None
    limited_code: str | None = None
    retry_after: str | None = None
    for index in range(1, burst + 1):
        status, headers, body = get(url, timeout)
        statuses.append(status)
        if status == 429 and first_limited is None:
            first_limited = index
            limited_code = _error_code(body)
            retry_after = headers.get("retry-after")
    admitted = sum(1 for status in statuses if status == 200)
    limited = sum(1 for status in statuses if status == 429)
    latest_ok = expect_limit + slack
    earliest_ok = max(0, expect_limit - slack)
    ok = (
        first_limited is not None
        and first_limited <= latest_ok
        and earliest_ok <= admitted <= latest_ok
        and limited > 0
        and limited_code == expect_code
        and bool(retry_after)
    )
    return {
        "url": url,
        "burst": burst,
        "expect_limit": expect_limit,
        "admitted_200": admitted,
        "limited_429": limited,
        "first_limited_at": first_limited,
        "limited_code": limited_code,
        "retry_after": retry_after,
        "ok": ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/health/live")
    parser.add_argument("--burst", type=int, default=110)
    parser.add_argument(
        "--expect-limit",
        type=int,
        required=True,
        help="configured maximum that must trip inside this burst",
    )
    parser.add_argument("--expect-code", default="AI_STP_RATE_LIMITED")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--slack",
        type=int,
        default=1,
        help="extra 200s allowed for a concurrent healthcheck sharing the budget",
    )
    args = parser.parse_args(argv)
    if args.burst <= args.expect_limit:
        parser.error("--burst must be greater than --expect-limit")
    report = probe(
        url=args.url,
        burst=args.burst,
        expect_limit=args.expect_limit,
        expect_code=args.expect_code,
        timeout=args.timeout,
        slack=args.slack,
    )
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
