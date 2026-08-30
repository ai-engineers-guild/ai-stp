"""One-shot deploy importer: GET state, POST snapshot (SPEC-054)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import cast

from ai_stp_contracts.content import ContentRepositoryImportRequest
from ai_stp_foundation.canonical import JsonValue

_TRANSIENT_STATUS = frozenset({502, 503, 504})
_DEFAULT_ATTEMPTS = 8
_DEFAULT_RETRY_SECONDS = 1.0


class _Transient(Exception):
    """API was unreachable or not ready. Safe to retry; state is unchanged."""

    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code
        super().__init__(code)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _as_object(value: object | None) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _error_code(payload: dict[str, object]) -> str:
    return str(_as_object(payload.get("error")).get("code") or "")


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("expected int")
    return value


def _attempts() -> int:
    raw = os.environ.get("AI_STP_CONTENT_IMPORT_ATTEMPTS", str(_DEFAULT_ATTEMPTS))
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_ATTEMPTS


def _retry_seconds() -> float:
    raw = os.environ.get("AI_STP_CONTENT_IMPORT_RETRY_SECONDS", str(_DEFAULT_RETRY_SECONDS))
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_RETRY_SECONDS


def _request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    data = None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            loaded: object = json.loads(response.read().decode("utf-8"))
            return int(response.status), _as_object(loaded)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        status = int(error.code)
        body = _as_object(parsed)
        if status in _TRANSIENT_STATUS:
            raise _Transient(status, _error_code(body) or "unavailable") from error
        return status, body
    except urllib.error.URLError as error:
        raise _Transient(0, "unreachable") from error


def _with_retry(
    op: str, send: Callable[[], tuple[int, dict[str, object]]]
) -> tuple[int, dict[str, object]] | None:
    last: _Transient | None = None
    delay = _retry_seconds()
    for attempt in range(_attempts()):
        try:
            return send()
        except _Transient as error:
            last = error
            if attempt + 1 >= _attempts():
                break
            _sleep(delay)
    assert last is not None
    sys.stderr.write(f"{op}_failed status={last.status} code={last.code}\n")
    return None


def main() -> int:
    token = os.environ.get("AI_STP_CONTENT_IMPORT_TOKEN", "")
    if not token:
        sys.stderr.write("AI_STP_CONTENT_IMPORT_FORBIDDEN\n")
        return 1
    base = os.environ.get("AI_STP_API_BASE_URL", "http://api:8000").rstrip("/")
    snapshot_path = Path(os.environ.get("AI_STP_CONTENT_SNAPSHOT", "/app/content-snapshot.json"))
    if not snapshot_path.is_file():
        sys.stderr.write("snapshot file is missing\n")
        return 1
    snapshot = ContentRepositoryImportRequest.model_validate_json(
        snapshot_path.read_text(encoding="utf-8")
    )
    state_call = _with_retry(
        "state",
        lambda: _request("GET", f"{base}/v1/content/repository/state", token),
    )
    if state_call is None:
        return 1
    status, state = state_call
    if status != 200:
        sys.stderr.write(f"state_failed status={status} code={_error_code(state)}\n")
        return 1
    payload: dict[str, object] = dict(snapshot.model_dump(mode="json"))
    payload["expected_generation"] = _as_int(state["generation"])
    import_call = _with_retry(
        "import",
        lambda: _request("POST", f"{base}/v1/content/repository/import", token, payload),
    )
    if import_call is None:
        return 1
    status, body = import_call
    if status != 200:
        sys.stderr.write(f"import_failed status={status} code={_error_code(body)}\n")
        return 1
    report: dict[str, JsonValue] = {
        "outcome": "accepted",
        "commit": snapshot.commit,
        "generation": _as_int(body["generation"]),
        "snapshot_digest": str(body["snapshot_digest"]),
        "created": _as_int(body["created"]),
        "activated": _as_int(body["activated"]),
        "removed": _as_int(body["removed"]),
        "unchanged": _as_int(body["unchanged"]),
    }
    sys.stdout.write(json.dumps(report) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
