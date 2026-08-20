"""Queued github_archive jobs remain compatible as a no-op (SPEC-049)."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.queue.states import JobType
from ai_stp_worker.handlers import REGISTRY
from ai_stp_worker.handlers.github_archive import handle_github_archive


@pytest.mark.asyncio
async def test_old_github_archive_jobs_complete_without_github() -> None:
    await handle_github_archive(
        cast(AsyncSession, _Session()),
        {"repository": "https://github.com/acme/tool"},
    )
    assert JobType.GITHUB_ARCHIVE.value == "github_archive"
    assert REGISTRY[JobType.GITHUB_ARCHIVE] is handle_github_archive


class _Session:
    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("archive no-op must not touch storage")
