"""Append-only audit events with secret redaction (SPEC-002 privacy)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.models import AuditEvent
from ai_stp_platform.tenant_scope import set_tenant_scope

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
        cleaned[key] = _redact_value(value)
    return cleaned


def _redact_value(value: Any) -> object:
    if isinstance(value, Mapping):
        return redact_payload(cast(Mapping[str, Any], value))
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_redact_value(item) for item in cast(Sequence[Any], value)]
    return value


async def emit_audit(
    db: AsyncSession,
    *,
    actor_account_id: str | None,
    organization_id: str | None = None,
    action: str,
    target_table: str,
    target_id: str,
    reason: str | None = None,
    outcome: str = "succeeded",
    request_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
) -> AuditEvent:
    """Persist one audit row. Payload is redacted before storage."""
    if organization_id is not None:
        await set_tenant_scope(db, organization_id)
    effective_role_bindings: list[dict[str, str]] = []
    resolved_actor_type = actor_type or ("user" if actor_account_id is not None else "system")
    resolved_actor_id = actor_id or actor_account_id
    if organization_id is not None and resolved_actor_id is not None:
        from ai_stp_platform.organization_models import CorporateRoleBinding

        principal_filter = (
            CorporateRoleBinding.account_id == resolved_actor_id
            if resolved_actor_type == "user"
            else CorporateRoleBinding.service_principal_id == resolved_actor_id
        )
        bindings = (
            await db.scalars(
                select(CorporateRoleBinding).where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.principal_type == resolved_actor_type,
                    principal_filter,
                    CorporateRoleBinding.state == "active",
                )
            )
        ).all()
        effective_role_bindings = [
            {
                "role": binding.role,
                "scope_kind": binding.scope_kind,
                "scope_id": binding.scope_id,
            }
            for binding in bindings
        ]
    event = AuditEvent(
        actor_account_id=actor_account_id,
        actor_type=resolved_actor_type,
        actor_id=resolved_actor_id,
        effective_role_bindings=effective_role_bindings,
        organization_id=organization_id,
        action=action,
        target_table=target_table,
        target_id=target_id,
        reason=reason,
        outcome=outcome,
        request_id=request_id,
        payload=redact_payload(payload),
    )
    db.add(event)
    await db.flush()
    return event
