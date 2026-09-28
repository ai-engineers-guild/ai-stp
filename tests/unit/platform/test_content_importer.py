# pyright: reportPrivateUsage=false
"""One-shot deploy importer talks only to the API (SPEC-054 REQ-5404)."""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from tests.unit.platform.article_fixtures import pair_snapshot

from ai_stp_platform.content import importer

pytestmark = pytest.mark.platform


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.Client]:
    """The same client policy the importer uses, over an in-process transport."""
    return lambda: httpx.Client(
        transport=httpx.MockTransport(handler),
        timeout=60,
        follow_redirects=False,
        trust_env=False,
    )


def _payload(request: httpx.Request) -> dict[str, Any] | None:
    if not request.content:
        return None
    parsed: object = json.loads(request.content)
    assert isinstance(parsed, dict)
    return cast("dict[str, Any]", parsed)


def test_importer_posts_expected_generation_from_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = pair_snapshot()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(snapshot.model_dump_json(), encoding="utf-8")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url), _payload(request)))
        if request.method == "GET":
            return httpx.Response(
                200, json={"generation": 3, "snapshot_digest": None, "commit": None}
            )
        return httpx.Response(
            200,
            json={
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
    monkeypatch.setattr(importer, "_client", _mock_client(handler))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert importer.main() == 0
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert calls[1][2] is not None
    assert calls[1][2]["expected_generation"] == 3
    assert "entries" in (calls[1][2] or {})


def test_importer_builds_missing_snapshot_from_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    git_dir = repository / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True)
    commit = "c" * 40
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs" / "heads" / "main").write_text(f"{commit}\n", encoding="utf-8")
    snapshot_path = tmp_path / "runtime" / "snapshot.json"
    expected = pair_snapshot()
    resolved: list[str] = []

    monkeypatch.setenv("AI_STP_CONTENT_HUB", str(repository))
    monkeypatch.setenv("AI_STP_CONTENT_REPOSITORY", str(repository))
    monkeypatch.delenv("AI_STP_API_GIT_COMMIT", raising=False)

    def fake_build(_hub: Path, *, commit: str) -> object:
        resolved.append(commit)
        return expected

    monkeypatch.setattr(importer, "build_repository_snapshot", fake_build)

    loaded = importer._load_snapshot(snapshot_path)

    assert loaded is expected
    assert resolved == [commit]
    assert snapshot_path.is_file()


def test_importer_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_STP_CONTENT_IMPORT_TOKEN", "")
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    assert importer.main() == 1


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

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and remaining_failures["n"]:
            remaining_failures["n"] -= 1
            raise httpx.ConnectError("connection refused", request=request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"generation": 1, "snapshot_digest": None, "commit": None}
            )
        return httpx.Response(
            200,
            json={
                "generation": 2,
                "snapshot_digest": pair_snapshot().snapshot_digest,
                "created": 0,
                "activated": 0,
                "removed": 0,
                "unchanged": 2,
            },
        )

    monkeypatch.setattr(importer, "_client", _mock_client(handler))
    assert importer.main() == 0
    assert remaining_failures["n"] == 0
    assert sleeps == [0.25, 0.25]


def test_importer_retries_transient_http_on_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps, _stderr = _prepare_importer(tmp_path, monkeypatch)
    remaining_failures = {"n": 1}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json={"generation": 1, "snapshot_digest": None, "commit": None}
            )
        if remaining_failures["n"]:
            remaining_failures["n"] -= 1
            return httpx.Response(503, json={"error": {"code": "unavailable"}})
        return httpx.Response(
            200,
            json={
                "generation": 2,
                "snapshot_digest": pair_snapshot().snapshot_digest,
                "created": 0,
                "activated": 0,
                "removed": 0,
                "unchanged": 2,
            },
        )

    monkeypatch.setattr(importer, "_client", _mock_client(handler))
    assert importer.main() == 0
    assert remaining_failures["n"] == 0
    assert sleeps == [0.25]


def test_importer_does_not_retry_client_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps, stderr = _prepare_importer(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json={"generation": 1, "snapshot_digest": None, "commit": None}
            )
        return httpx.Response(400, json={"error": {"code": "AI_STP_CONTENT_INVALID"}})

    monkeypatch.setattr(importer, "_client", _mock_client(handler))
    assert importer.main() == 1
    assert sleeps == []
    assert "AI_STP_CONTENT_INVALID" in stderr.getvalue()


def test_importer_exhausted_retries_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps, stderr = _prepare_importer(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(importer, "_client", _mock_client(handler))
    assert importer.main() == 1
    assert sleeps == [0.25, 0.25]
    assert "state_failed" in stderr.getvalue()


def test_importer_never_follows_redirects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps, stderr = _prepare_importer(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            # Even pointing at the same host, a redirect answer is a refusal:
            # following it would re-issue the Bearer header to the new origin.
            return httpx.Response(302, headers={"location": "https://api.test:8000/state"})
        raise AssertionError("the import POST must never run after a redirect")

    monkeypatch.setattr(importer, "_client", _mock_client(handler))
    assert importer.main() == 1
    assert sleeps == []
    assert "state_failed" in stderr.getvalue()


def test_importer_caps_oversized_responses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps, stderr = _prepare_importer(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=b"x" * (5 * 1024 * 1024))
        raise AssertionError("the import POST must never run on an unreadable state")

    monkeypatch.setattr(importer, "_client", _mock_client(handler))
    assert importer.main() == 1
    assert sleeps == []
    assert "state_failed" in stderr.getvalue()
