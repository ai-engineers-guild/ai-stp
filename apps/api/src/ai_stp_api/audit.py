"""Append-only audit events with secret redaction (SPEC-002 privacy)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.models import AuditEvent

# Keys whose values must never leave the process via audit payloads.
_REDACT_KEYS = frozenset(
    {
        "token",
        "session",
        "session_token",
        "session_id",
        "raw_token",
        "nonce",
        "code",
        "code_verifier",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "authorization",
        "cookie",
        "csrf",
        "csrf_token",
        "signature",
        "private_key",
        "cursor",
        "raw_cursor",
        "payload",
        "document",
        "revision_document",
        "secret",
        "password",
        "env",
        "environment",
        "accept_token",
        "invitation_token",
        "email_body",
        "diagnostics",
        "attestation_signature",
    }
)


def redact_payload(payload: Mapping[str, Any] | None) -> dict[str, object]:
    """Return a copy of payload with sensitive keys removed (recursive)."""
    if not payload:
        return {}
    cleaned: dict[str, object] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if lowered in _REDACT_KEYS or any(part in lowered for part in _REDACT_KEYS):
            continue
        if isinstance(value, Mapping):
            cleaned[key] = redact_payload(value)  # type: ignore[arg-type]
        else:
            cleaned[key] = value
    return cleaned


async def emit_audit(
    db: AsyncSession,
    *,
    actor_account_id: str | None,
    action: str,
    target_table: str,
    target_id: str,
    reason: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Persist one audit row. Payload is redacted before storage."""
    event = AuditEvent(
        actor_account_id=actor_account_id,
        action=action,
        target_table=target_table,
        target_id=target_id,
        reason=reason,
        payload=redact_payload(payload),
    )
    db.add(event)
    await db.flush()
    return event
