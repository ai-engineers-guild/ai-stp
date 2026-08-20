"""Unit tests for readiness reporting (SPEC-017 REQ-1708)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from ai_stp_platform.readiness import (
    DEPENDENCIES,
    check_database,
    check_migrations,
    check_storage,
    not_ready,
    readiness_report,
)
from ai_stp_platform.settings import StorageSettings

pytestmark = pytest.mark.platform


def test_not_ready_lists_missing_in_declared_order() -> None:
    report = {"database": True, "migrations": False, "storage": False}
    assert not_ready(report) == ["migrations", "storage"]


def test_not_ready_empty_when_all_ready() -> None:
    assert not_ready(dict.fromkeys(DEPENDENCIES, True)) == []


def test_not_ready_treats_absent_keys_as_not_ready() -> None:
    # Breakage: missing probe keys treated as ready and omitted from the list.
    assert not_ready({}) == list(DEPENDENCIES)


class FakeResult:
    def __init__(self, revision: str | None) -> None:
        self._revision = revision

    def scalar_one_or_none(self) -> str | None:
        return self._revision


class FakeSession:
    def __init__(self, revision: str | None, *, fail: bool = False) -> None:
        self._revision = revision
        self._fail = fail

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    async def execute(self, statement: object) -> FakeResult:
        if self._fail:
            raise RuntimeError("database unavailable")
        return FakeResult(self._revision)


class FakeSessionmaker:
    def __init__(self, revision: str | None, *, fail: bool = False) -> None:
        self._revision = revision
        self._fail = fail

    def __call__(self) -> FakeSession:
        return FakeSession(self._revision, fail=self._fail)


def _storage() -> StorageSettings:
    return StorageSettings(
        endpoint="http://127.0.0.1:9",
        bucket="ai-stp-test",
        access_key_id="test-access",
        secret_access_key="test-secret",
    )


@pytest.mark.asyncio
async def test_check_migrations_true_only_at_alembic_head() -> None:
    """The head is read from the migration tree, not pinned to a literal.

    The invariant is "at head → ready, behind head → not ready". Hard-coding the
    revision made every new migration fail this test for a reason unrelated to
    readiness, and the standing fix was to retype the string.
    """
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = script.get_heads()
    assert len(heads) == 1, f"branched migration history: {sorted(heads)}"
    head = heads[0]

    previous = script.get_revision(head).down_revision
    assert isinstance(previous, str), "the head must have exactly one parent to test staleness"

    current = cast("Any", FakeSessionmaker(head))
    stale = cast("Any", FakeSessionmaker(previous))

    assert await check_migrations(current) is True
    assert await check_migrations(stale) is False


@pytest.mark.asyncio
async def test_check_database_collapses_connection_failures() -> None:
    # Breakage: database exceptions bubble and break the readiness endpoint.
    failing = cast("Any", FakeSessionmaker(None, fail=True))
    assert await check_database(failing) is False


@pytest.mark.asyncio
async def test_check_migrations_collapses_probe_exceptions() -> None:
    failing = cast("Any", FakeSessionmaker(None, fail=True))
    assert await check_migrations(failing) is False


@pytest.mark.asyncio
async def test_check_storage_reports_reachable_and_failure_paths() -> None:
    settings = _storage()

    class _OkClient:
        async def __aenter__(self) -> _OkClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> httpx.Response:
            del url
            return httpx.Response(200)

    class _FailClient:
        async def __aenter__(self) -> _FailClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> httpx.Response:
            del url
            raise httpx.ConnectError("unreachable")

    with patch("ai_stp_platform.readiness.httpx.AsyncClient", return_value=_OkClient()):
        assert await check_storage(settings) is True

    with patch("ai_stp_platform.readiness.httpx.AsyncClient", return_value=_FailClient()):
        assert await check_storage(settings) is False


@pytest.mark.asyncio
async def test_readiness_report_skips_migrations_when_database_is_down() -> None:
    # Breakage: migrations probed (and possibly hanging) after database is already down.
    failing = cast("Any", FakeSessionmaker(None, fail=True))
    with patch(
        "ai_stp_platform.readiness.check_storage",
        new=AsyncMock(return_value=True),
    ):
        report = await readiness_report(sessionmaker=failing, storage=_storage())
    assert report == {"database": False, "migrations": False, "storage": True}
