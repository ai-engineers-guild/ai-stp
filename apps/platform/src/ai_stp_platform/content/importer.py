"""One-shot deploy importer: GET state, POST snapshot (SPEC-054)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx

from ai_stp_contracts.content import ContentRepositoryImportRequest
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.snapshot import (
    build_repository_snapshot,
    resolve_repository_commit,
    snapshot_as_json,
)

_TRANSIENT_STATUS = frozenset({502, 503, 504})
_DEFAULT_ATTEMPTS = 8
_DEFAULT_RETRY_SECONDS = 1.0
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


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


def _load_snapshot(snapshot_path: Path) -> ContentRepositoryImportRequest:
    if snapshot_path.is_file():
        return ContentRepositoryImportRequest.model_validate_json(
            snapshot_path.read_text(encoding="utf-8")
        )

    hub_value = os.environ.get("AI_STP_CONTENT_HUB", "").strip()
    if not hub_value:
        raise ContentError("AI_STP_CONTENT_INVALID", "content hub is not configured")
    repository_value = os.environ.get("AI_STP_CONTENT_REPOSITORY", "").strip()
    commit = os.environ.get("AI_STP_API_GIT_COMMIT", "").strip()
    if not commit:
        if not repository_value:
            raise ContentError("AI_STP_CONTENT_INVALID", "repository checkout is not configured")
        commit = resolve_repository_commit(Path(repository_value))
    snapshot = build_repository_snapshot(Path(hub_value), commit=commit)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(canonize(dict(snapshot_as_json(snapshot))))
    return snapshot


def _client() -> httpx.Client:
    """The one transport policy the importer uses (also the test seam).

    `follow_redirects=False` is the security boundary: a redirect would carry
    the Bearer token to whatever origin `Location` names.
    """
    return httpx.Client(timeout=60, follow_redirects=False, trust_env=False)


def _request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        with (
            _client() as client,
            client.stream(method, url, headers=headers, json=payload) as response,
        ):
            status = int(response.status_code)
            # A redirect is never followed: it would carry the Bearer
            # token to whatever origin Location names.
            body = bytearray()
            too_large = False
            if not 300 <= status < 400:
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_RESPONSE_BYTES:
                        too_large = True
                        break
    except httpx.HTTPError as error:
        raise _Transient(0, "unreachable") from error
    if too_large:
        # A fake failure status keeps the answer out of the 200-path: the cap
        # is a refusal to trust the body, not a version of it.
        return 0, {"error": {"code": "response_too_large"}}
    try:
        parsed: object = json.loads(body.decode("utf-8"))
    except ValueError:
        parsed = {}
    decoded = _as_object(parsed)
    if status in _TRANSIENT_STATUS:
        raise _Transient(status, _error_code(decoded) or "unavailable")
    return status, decoded


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
    parsed_base = urllib.parse.urlsplit(base)
    if (
        parsed_base.scheme not in {"http", "https"}
        or not parsed_base.hostname
        or parsed_base.username
        or parsed_base.password
        or parsed_base.query
        or parsed_base.fragment
    ):
        # The cleartext http default is deliberate: it names a service on the
        # deploy-internal compose network. Anything outside a plain http(s)
        # origin is refused rather than interpreted.
        sys.stderr.write("AI_STP_CONTENT_INVALID: malformed AI_STP_API_BASE_URL\n")
        return 1
    snapshot_path = Path(os.environ.get("AI_STP_CONTENT_SNAPSHOT", "/app/content-snapshot.json"))
    try:
        snapshot = _load_snapshot(snapshot_path)
    except ContentError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
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
