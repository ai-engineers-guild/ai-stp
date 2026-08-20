from __future__ import annotations

import os
from collections.abc import Mapping

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.repository_metrics import refresh_github_stars


async def handle_repository_metrics(session: AsyncSession, payload: Mapping[str, object]) -> None:
    repository = payload.get("repository")
    if not isinstance(repository, str):
        raise ValueError("repository_metrics requires repository")
    token = os.environ.get("AI_STP_WORKER_GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        await refresh_github_stars(session, repository, client=client)
