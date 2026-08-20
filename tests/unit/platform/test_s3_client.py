from __future__ import annotations

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage import s3

pytestmark = pytest.mark.platform


class _Body:
    async def __aenter__(self) -> _Body:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def read(self) -> bytes:
        return b"payload"


class _Client:
    def __init__(self) -> None:
        self.put: dict[str, object] | None = None
        self.head_error: ClientError | None = None
        self.get_error: ClientError | None = None
        self.bucket_error: ClientError | None = None
        self.created_bucket: str | None = None

    async def head_bucket(self, **kwargs: object) -> None:
        del kwargs
        if self.bucket_error:
            raise self.bucket_error

    async def create_bucket(self, **kwargs: object) -> None:
        self.created_bucket = str(kwargs["Bucket"])

    async def head_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        if self.head_error:
            raise self.head_error
        return {"Metadata": {"digest": 123}, "ContentLength": 7}

    async def put_object(self, **kwargs: object) -> None:
        self.put = kwargs

    async def get_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        if self.get_error:
            raise self.get_error
        return {"Body": _Body()}


class _ClientContext:
    def __init__(self, client: _Client) -> None:
        self.client = client
        self.exited: tuple[object, ...] | None = None

    async def __aenter__(self) -> _Client:
        return self.client

    async def __aexit__(self, *args: object) -> None:
        self.exited = args


class _Session:
    def __init__(self, context: _ClientContext) -> None:
        self.context = context

    def create_client(self, *_args: object, **_kwargs: object) -> _ClientContext:
        return self.context


def _error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "ObjectOperation")


@pytest.mark.asyncio
async def test_s3_client_requires_context_and_closes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _Client()
    context = _ClientContext(remote)
    session = _Session(context)

    def get_session() -> _Session:
        return session

    monkeypatch.setattr(s3, "get_session", get_session)
    client = s3.S3ObjectClient(
        StorageSettings(
            endpoint="https://storage.example",
            bucket="bucket",
            access_key_id="access",
            secret_access_key="secret",
        )
    )

    with pytest.raises(RuntimeError, match="not entered"):
        await client.head_object(bucket="bucket", key="key")
    async with client as entered:
        assert entered is client
        assert await client.head_object(bucket="bucket", key="key") == {
            "metadata": {"digest": "123"},
            "size_bytes": 7,
        }
        await client.put_object(
            bucket="bucket", key="key", body=b"body", metadata={"digest": "value"}
        )
        assert remote.put == {
            "Bucket": "bucket",
            "Key": "key",
            "Body": b"body",
            "Metadata": {"digest": "value"},
        }
        assert await client.get_object_bytes(bucket="bucket", key="key") == b"payload"
    assert context.exited is not None


@pytest.mark.asyncio
async def test_s3_client_maps_only_not_found_errors_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = _Client()
    context = _ClientContext(remote)
    session = _Session(context)

    def get_session() -> _Session:
        return session

    monkeypatch.setattr(s3, "get_session", get_session)
    settings = StorageSettings(
        endpoint="https://storage.example",
        bucket="bucket",
        access_key_id="access",
        secret_access_key="secret",
    )
    async with s3.S3ObjectClient(settings) as client:
        for code in ("404", "NoSuchKey", "NotFound", "404 Not Found"):
            remote.head_error = _error(code)
            assert await client.head_object(bucket="bucket", key="missing") is None
            remote.get_error = _error(code)
            assert await client.get_object_bytes(bucket="bucket", key="missing") is None
        remote.head_error = _error("AccessDenied")
        with pytest.raises(ClientError):
            await client.head_object(bucket="bucket", key="forbidden")
        remote.get_error = _error("AccessDenied")
        with pytest.raises(ClientError):
            await client.get_object_bytes(bucket="bucket", key="forbidden")


@pytest.mark.asyncio
async def test_s3_client_ensures_bucket_and_preserves_access_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = _Client()
    context = _ClientContext(remote)
    monkeypatch.setattr(s3, "get_session", lambda: _Session(context))
    settings = StorageSettings(
        endpoint="https://storage.example",
        bucket="bucket",
        access_key_id="access",
        secret_access_key="secret",
    )

    async with s3.S3ObjectClient(settings) as client:
        await client.ensure_bucket()
        assert remote.created_bucket is None

        remote.bucket_error = _error("NoSuchBucket")
        await client.ensure_bucket()
        assert remote.created_bucket == "bucket"

        remote.bucket_error = _error("AccessDenied")
        with pytest.raises(ClientError):
            await client.ensure_bucket()
