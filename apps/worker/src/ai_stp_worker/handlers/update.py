"""Update handler stub (SPEC-018).

Records intent to push an update. The real update application and the S3 signing
step arrive with #79/#81.
"""

from __future__ import annotations

from collections.abc import Mapping


async def handle_update(payload: Mapping[str, object]) -> None:
    """Handle an update job; a stub that proves the queue path."""
    _ = payload
    # Stub: the update application and S3 signing step land with #79/#81.
