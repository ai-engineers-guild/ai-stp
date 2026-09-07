"""Bounded binary request bodies for authenticated media routes."""

from __future__ import annotations

from fastapi import Request

from ai_stp_api.errors import ApiError, ErrorCategory


async def read_media_upload(request: Request, *, max_bytes: int) -> tuple[bytes, str]:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if not content_type or content_type.startswith("multipart/"):
        raise ApiError(ErrorCategory.VALIDATION, "a binary image or video content-type is required")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except ValueError as exc:
            raise ApiError(ErrorCategory.VALIDATION, "invalid content-length") from exc
        if size <= 0 or size > max_bytes:
            raise ApiError(
                ErrorCategory.VALIDATION, "media payload exceeds its byte limit or is empty"
            )
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > max_bytes:
            raise ApiError(ErrorCategory.VALIDATION, "media payload exceeds its byte limit")
        payload.extend(chunk)
    if not payload:
        raise ApiError(ErrorCategory.VALIDATION, "empty media payload")
    return bytes(payload), content_type
