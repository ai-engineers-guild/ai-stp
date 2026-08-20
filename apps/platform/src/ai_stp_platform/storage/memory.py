"""In-memory S3-compatible object client for tests and local isolation."""

from __future__ import annotations


class MemoryObjectClient:
    """Records put/head operations without network I/O."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.put_count = 0

    async def head_object(self, *, bucket: str, key: str) -> dict[str, object] | None:
        return self.objects.get((bucket, key))

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        metadata: dict[str, str],
    ) -> None:
        self.put_count += 1
        self.objects[(bucket, key)] = {
            "body": body,
            "metadata": dict(metadata),
            "size_bytes": len(body),
        }

    async def get_object_bytes(self, *, bucket: str, key: str) -> bytes | None:
        item = self.objects.get((bucket, key))
        if item is None:
            return None
        body = item.get("body")
        return body if isinstance(body, bytes) else None
