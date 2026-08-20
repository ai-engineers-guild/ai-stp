"""Upload handler stub (SPEC-018).

Validates the visibility parameter and records intent. The real object write and
the S3 signing step arrive with #79/#81; here the handler only proves the queue
path end to end.
"""

from __future__ import annotations

from collections.abc import Mapping

from ai_stp_platform.queue.states import Visibility


class InvalidJobPayload(ValueError):
    """The job payload is missing or has an invalid required field."""


async def handle_upload(payload: Mapping[str, object]) -> None:
    """Handle an upload job; requires a valid visibility parameter."""
    raw = payload.get("visibility")
    if not isinstance(raw, str):
        raise InvalidJobPayload("upload requires a visibility parameter")
    try:
        Visibility(raw)
    except ValueError as exc:
        raise InvalidJobPayload("upload visibility must be public or private") from exc
    # Stub: the object write and S3 signing step land with #79/#81.
