"""One-shot deploy importer talks only to the API (SPEC-054 REQ-5404)."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from tests.unit.platform.article_fixtures import pair_snapshot

from ai_stp_platform.content import importer

pytestmark = pytest.mark.platform


class _Response:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_importer_posts_expected_generation_from_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = pair_snapshot()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(snapshot.model_dump_json(), encoding="utf-8")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        del timeout
        method = request.get_method()
        url = request.full_url
        payload = None
        if request.data:
            payload = json.loads(request.data.decode("utf-8"))
        calls.append((method, url, payload))
        if method == "GET":
            return _Response(200, {"generation": 3, "snapshot_digest": None, "commit": None})
        return _Response(
            200,
            {
                "generation": 4,
                "snapshot_digest": snapshot.snapshot_digest,
                "created": 2,
                "activated": 2,
                "removed": 0,
                "unchanged": 0,
            },
        )

    monkeypatch.setenv("AI_STP_CONTENT_IMPORT_TOKEN", "token")
    monkeypatch.setenv("AI_STP_API_BASE_URL", "http://api.test:8000")
    monkeypatch.setenv("AI_STP_CONTENT_SNAPSHOT", str(snapshot_path))
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert importer.main() == 0
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert calls[1][2] is not None
    assert calls[1][2]["expected_generation"] == 3
    assert "entries" in (calls[1][2] or {})


def test_importer_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_STP_CONTENT_IMPORT_TOKEN", "")
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    assert importer.main() == 1


def _http_error(url: str, status: int, payload: dict[str, Any]) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps(payload).encode("utf-8"))
    return urllib.error.HTTPError(url, status, "error", Message(), body)


def _prepare_importer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[float], io.StringIO]:
    snapshot = pair_snapshot()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(snapshot.model_dump_json(), encoding="utf-8")
    sleeps: list[float] = []

    def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    stderr = io.StringIO()
    monkeypatch.setenv("AI_STP_CONTENT_IMPORT_TOKEN", "token")
    monkeypatch.setenv("AI_STP_API_BASE_URL", "http://api.test:8000")
    monkeypatch.setenv("AI_STP_CONTENT_SNAPSHOT", str(snapshot_path))
    monkeypatch.setenv("AI_STP_CONTENT_IMPORT_ATTEMPTS", "3")
    monkeypatch.setenv("AI_STP_CONTENT_IMPORT_RETRY_SECONDS", "0.25")
    monkeypatch.setattr(importer, "_sleep", record_sleep)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", stderr)
    return sleeps, stderr


def test_importer_retries_unreachable_state_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps, _stderr = _prepare_importer(tmp_path, monkeypatch)
    remaining_failures = {"n": 2}

    def fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        del timeout
        method = request.get_method()
        if method == "GET" and remaining_failures["n"]:
            remaining_failures["n"] -= 1
            raise urllib.error.URLError("connection refused")
        if method == "GET":
            return _Response(200, {"generation": 1, "snapshot_digest": None, "commit": None})
        return _Response(
            200,
            {
                "generation": 2,
                "snapshot_digest": pair_snapshot().snapshot_digest,
                "created": 0,
                "activated": 0,
                "removed": 0,
                "unchanged": 2,
            },
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert importer.main() == 0
    assert remaining_failures["n"] == 0
    assert sleeps == [0.25, 0.25]


def test_importer_retries_transient_http_on_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps, _stderr = _prepare_importer(tmp_path, monkeypatch)
    remaining_failures = {"n": 1}

    def fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        del timeout
        method = request.get_method()
        if method == "GET":
            return _Response(200, {"generation": 1, "snapshot_digest": None, "commit": None})
        if remaining_failures["n"]:
            remaining_failures["n"] -= 1
            raise _http_error(request.full_url, 503, {"error": {"code": "unavailable"}})
        return _Response(
            200,
            {
                "generation": 2,
                "snapshot_digest": pair_snapshot().snapshot_digest,
                "created": 0,
                "activated": 0,
                "removed": 0,
                "unchanged": 2,
            },
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert importer.main() == 0
    assert remaining_failures["n"] == 0
    assert sleeps == [0.25]


def test_importer_does_not_retry_client_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps, stderr = _prepare_importer(tmp_path, monkeypatch)

    def fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        del timeout
        if request.get_method() == "GET":
            return _Response(200, {"generation": 1, "snapshot_digest": None, "commit": None})
        raise _http_error(
            request.full_url,
            400,
            {"error": {"code": "AI_STP_CONTENT_INVALID"}},
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert importer.main() == 1
    assert sleeps == []
    assert "AI_STP_CONTENT_INVALID" in stderr.getvalue()


def test_importer_exhausted_retries_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps, stderr = _prepare_importer(tmp_path, monkeypatch)

    def fake_urlopen(request: Any, timeout: int = 0) -> _Response:
        del timeout
        del request
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert importer.main() == 1
    assert sleeps == [0.25, 0.25]
    assert "state_failed" in stderr.getvalue()
