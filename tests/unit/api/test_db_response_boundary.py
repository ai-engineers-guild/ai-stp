"""A successful HTTP response must never acknowledge an unfinished transaction."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, cast

import pytest
from fastapi import Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Message, Receive, Scope, Send
from tests.support.api_settings import make_settings

from ai_stp_api.app import create_app
from ai_stp_api.deps import Db, get_db
from ai_stp_api.errors import register_exception_handlers

pytestmark = pytest.mark.platform


class Transaction:
    def __init__(self, *, fail: bool) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.fail = fail
        self.committed = False
        self.events: list[str] = []

    async def commit(self) -> None:
        self.events.append("commit_started")
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("private transaction failure detail")
        self.committed = True
        self.events.append("committed")

    async def rollback(self) -> None:
        self.events.append("rolled_back")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        self.events.append("opened")
        try:
            yield cast(AsyncSession, self)
        finally:
            self.events.append("closed")


async def same_database(db: Db) -> AsyncSession:
    return db


@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_commit_completes_before_any_response_frame(*, fail: bool, stream: bool) -> None:
    transaction = Transaction(fail=fail)
    app = FastAPI()
    app.state.sessionmaker = transaction.session
    register_exception_handlers(app)

    @app.post("/write", response_model=None)
    async def write(db: Db, same: Annotated[AsyncSession, Depends(same_database)]) -> Response:
        assert db is same is cast(AsyncSession, transaction)
        transaction.events.append("write")
        if stream:
            return StreamingResponse(iter((b"accepted",)))
        return JSONResponse({"accepted": True})

    messages: list[Message] = []

    async def observed(scope: Scope, receive: Receive, send: Send) -> None:
        async def forward(message: Message) -> None:
            messages.append(message)
            transaction.events.append(message["type"])
            await send(message)

        await app(scope, receive, forward)

    async with AsyncClient(
        transport=ASGITransport(app=observed, raise_app_exceptions=False),
        base_url="https://api.test",
    ) as client:
        request = asyncio.create_task(client.post("/write"))
        try:
            await asyncio.wait_for(transaction.started.wait(), timeout=5)
            assert not messages, "HTTP acknowledgement escaped while commit was blocked"
        finally:
            transaction.release.set()
            response = await asyncio.wait_for(request, timeout=5)
    assert transaction.events.count("opened") == 1
    assert transaction.events.index("closed") < transaction.events.index("http.response.start")
    if fail:
        assert response.status_code == 500
        assert not transaction.committed
        assert transaction.events.index("rolled_back") < transaction.events.index("closed")
        assert "private transaction failure detail" not in response.text
        assert not any(message.get("status") == 200 for message in messages)
    else:
        assert response.status_code == 200 and transaction.committed
        assert "rolled_back" not in transaction.events
        assert transaction.events.index("committed") < transaction.events.index("closed")
        assert response.content == (b"accepted" if stream else b'{"accepted":true}')


def test_all_mounted_database_dependencies_share_the_pre_response_lifetime(
    tmp_path: Path,
) -> None:
    # Cover actual route/auth wiring, so a new request-scoped get_db consumer
    # cannot silently split the cached transaction or bypass the response fence.
    app = create_app(make_settings(tmp_path))
    checked: set[tuple[str, str]] = set()

    def walk(dependency: Dependant, path: str) -> None:
        if dependency.call is get_db:
            assert dependency.scope == "function", path
            assert dependency.use_cache, path
            checked.add((path, dependency.name or ""))
        for child in dependency.dependencies:
            walk(child, path)

    for route in app.routes:
        if isinstance(route, APIRoute):
            walk(route.dependant, route.path)
    assert len(checked) > 100, "the audit must inspect mounted product routes"
    assert any(path == "/v1/corporate/bootstrap" for path, _ in checked)
