"""Async S3-compatible client for RustFS/S3 via aiobotocore (SPEC-020)."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self, cast

from aiobotocore.session import get_session  # type: ignore[import-untyped]

from ai_stp_platform.settings import StorageSettings


class S3ObjectClient:
    """Long-lived async S3 client bound to StorageSettings."""

    def __init__(self, settings: StorageSettings) -> None:
        self._settings = settings
        self._session: Any = get_session()
        self._cm: Any | None = None
        self._client: Any | None = None

    async def __aenter__(self) -> Self:
        self._cm = self._session.create_client(
            "s3",
            region_name=self._settings.region,
            aws_access_key_id=self._settings.access_key_id,
            aws_secret_access_key=self._settings.secret_access_key,
            endpoint_url=self._settings.endpoint,
        )
        assert self._cm is not None
        self._client = await self._cm.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        cm = self._cm
        if cm is not None:
            await cm.__aexit__(exc_type, exc, tb)
        self._client = None
        self._cm = None

    def _require(self) -> Any:
        if self._client is None:
            raise RuntimeError("S3ObjectClient is not entered")
        return self._client

    async def ensure_bucket(self) -> None:
        """Create the configured bucket when a fresh RustFS/S3 instance has none.

        Raises ClientError with a clearer message when credentials are rejected
        (typical rustfs misconfig: container started without RUSTFS_ACCESS_KEY
        and fell back to built-in defaults while the API still uses compose keys).
        """
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        client = self._require()
        try:
            await client.head_bucket(Bucket=self._settings.bucket)
            return
        except ClientError as exc:
            err = cast(dict[str, Any], getattr(exc, "response", {}))
            code = str(err.get("Error", {}).get("Code", ""))
            http_status = err.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchBucket", "NotFound"} or http_status == 404:
                pass
            elif code in {"403", "AccessDenied", "Forbidden"} or http_status == 403:
                # Distinguish auth failure from "bucket missing" so startup logs
                # point at credential/env mismatch rather than a silent retry loop.
                raise ClientError(
                    {
                        "Error": {
                            "Code": "AccessDenied",
                            "Message": (
                                f"HeadBucket forbidden for bucket "
                                f"{self._settings.bucket!r} at "
                                f"{self._settings.endpoint}. Check that object-store "
                                f"credentials match the storage service "
                                f"(RUSTFS_ACCESS_KEY / AI_STP_STORAGE_ACCESS_KEY_ID)."
                            ),
                        },
                        "ResponseMetadata": err.get("ResponseMetadata", {}),
                    },
                    "HeadBucket",
                ) from exc
            else:
                raise
        await client.create_bucket(Bucket=self._settings.bucket)

    async def head_object(self, *, bucket: str, key: str) -> dict[str, object] | None:
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        client = self._require()
        try:
            response = cast(dict[str, Any], await client.head_object(Bucket=bucket, Key=key))
        except ClientError as exc:
            err = cast(dict[str, Any], getattr(exc, "response", {}))
            code = str(err.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound", "404 Not Found"}:
                return None
            raise
        raw_meta = response.get("Metadata")
        meta_out: dict[str, str] = {}
        if isinstance(raw_meta, dict):
            for key_obj, value_obj in cast(dict[object, object], raw_meta).items():
                meta_out[str(key_obj)] = str(value_obj)
        return {
            "metadata": meta_out,
            "size_bytes": int(response.get("ContentLength") or 0),
        }

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        metadata: dict[str, str],
    ) -> None:
        client = self._require()
        await client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            Metadata=metadata,
        )

    async def get_object_bytes(self, *, bucket: str, key: str) -> bytes | None:
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        client = self._require()
        try:
            response = cast(dict[str, Any], await client.get_object(Bucket=bucket, Key=key))
        except ClientError as exc:
            err = cast(dict[str, Any], getattr(exc, "response", {}))
            code = str(err.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound", "404 Not Found"}:
                return None
            raise
        body = response["Body"]
        async with body as stream:
            data = await stream.read()
        return cast(bytes, data)
