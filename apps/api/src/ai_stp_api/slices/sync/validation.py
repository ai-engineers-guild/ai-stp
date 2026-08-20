"""Canonical revision validation and allowlist policy (SPEC-025 REQ-2501).

Pure functions: no I/O. Reject forbidden payload classes before any write.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from ai_stp_contracts.sync_payload import SyncPayloadRejection, check_sync_payload
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.revisions import is_valid_revision_id, revision_id

ALLOWED_ENTITY_KINDS: Final[frozenset[str]] = frozenset(
    {
        "developer_passport",
        "device_summary",
        "component_private",
        "setup_private",
        "unverified_consent",
    }
)

_ENTITY_PREFIX: Final[dict[str, str]] = {
    "developer_passport": "developer",
    "device_summary": "device",
    "component_private": "component",
    "setup_private": "setup",
    "unverified_consent": "account",
}

_FORBIDDEN_PAYLOAD_KINDS: Final[frozenset[str]] = frozenset(
    {
        "device",
        "project",
        "DevicePassport",
        "ProjectPassport",
        "ProjectIndex",
    }
)


class SyncValidationError(ValueError):
    """Event fails mechanical validation before ledger application."""


def request_fingerprint(event_payload: dict[str, object]) -> str:
    """Stable fingerprint of one event for idempotency conflict detection."""
    digest = digest_canonical("ai-stp:revision:v1", cast(JsonValue, event_payload))
    return digest.removeprefix("sha256:")


def seal_revision_document(
    *,
    entity_id: str,
    entity_kind: str,
    parent_revision_ids: list[str],
    operation: str,
    payload: Mapping[str, object],
    device_id: str,
    actor_id: str,
    created_at: str,
) -> dict[str, JsonValue]:
    """Canonical fields sealed into the content-addressed revision id."""
    document: dict[str, JsonValue] = {
        "schema_version": 1,
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "parent_revision_ids": list(parent_revision_ids),
        "operation": operation,
        "payload": cast(JsonValue, dict(payload)),
        "device_id": device_id,
        "actor_id": actor_id,
        "created_at": created_at,
    }
    return document


def expected_revision_id(document: dict[str, JsonValue]) -> str:
    """Derive the content-addressed revision id for a sealed document."""
    return revision_id(document)


def expected_content_digest(payload: Mapping[str, object]) -> str:
    """Digest of the revision payload body alone."""
    return digest_canonical("ai-stp:revision:v1", cast(JsonValue, dict(payload)))


def can_accept_head_transition(
    *,
    current_head: str | None,
    expected_head: str | None,
    parent_revision_ids: list[str],
) -> bool:
    """Allow only an initial revision or a fast-forward from the current head."""
    is_initial = current_head is None and not parent_revision_ids and expected_head is None
    is_fast_forward = (
        current_head is not None
        and expected_head == current_head
        and current_head in parent_revision_ids
    )
    return is_initial or is_fast_forward


def _scan_kinds(value: object) -> None:
    """Refuse a payload that declares itself one of the kinds that never sync.

    Separate from the field policy rather than folded into it: that one is about
    what a key may be called, this one is about what a document says it is. They
    happen to protect the same objects and are not the same rule.
    """
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            names_kind = isinstance(key, str) and key.lower() == "kind"
            if names_kind and isinstance(item, str) and item in _FORBIDDEN_PAYLOAD_KINDS:
                raise SyncValidationError(f"forbidden payload kind: {item}")
            _scan_kinds(item)
        return
    if isinstance(value, list):
        for item in cast(list[object], value):
            _scan_kinds(item)


def _scan_forbidden(value: object) -> None:
    """Apply the shared payload policy, plus the kind rule this side owns.

    The field policy has one owner in `ai_stp_contracts.sync_payload`, and this
    is the server half applying it. Both halves used to carry a byte-identical
    fragment list, and only the client grew the `required_env` carve-out — so a
    complete canonical passport passed the half that was optional and was
    refused by the half that decides. That is what a rule stated twice does.
    """
    _scan_kinds(value)
    try:
        check_sync_payload(value)
    except SyncPayloadRejection as rejection:
        raise SyncValidationError(f"{rejection.reason} at {rejection.path}") from rejection


def validate_entity_identity(*, entity_kind: str, entity_id: str, device_id: str) -> None:
    """Check entity kind allowlist and id prefix / device binding."""
    if entity_kind not in ALLOWED_ENTITY_KINDS:
        raise SyncValidationError(f"entity_kind not allowed: {entity_kind}")
    prefix = _ENTITY_PREFIX[entity_kind]
    if entity_kind == "unverified_consent":
        # Consent is scoped to the account; wire id may be account or opaque consent.
        if not (is_valid_id(entity_id, "account") or entity_id.startswith("consent_")):
            raise SyncValidationError("unverified_consent entity_id is invalid")
        return
    if not is_valid_id(entity_id, prefix):
        raise SyncValidationError(f"entity_id must be a valid {prefix} id")
    if entity_kind == "device_summary" and entity_id != device_id:
        raise SyncValidationError("device_summary entity_id must match the session device")


def validate_parents(parent_revision_ids: list[str], *, operation: str) -> None:
    """Mechanical parent rules before graph checks against the ledger."""
    if len(parent_revision_ids) != len(set(parent_revision_ids)):
        raise SyncValidationError("parent_revision_ids must be unique")
    for parent in parent_revision_ids:
        if not is_valid_revision_id(parent):
            raise SyncValidationError("parent_revision_ids contain an invalid revision id")
    if operation == "tombstone" and not parent_revision_ids:
        raise SyncValidationError("tombstone requires at least one parent")
    if len(parent_revision_ids) > 2:
        raise SyncValidationError("at most two parents are supported")


def validate_event_document(
    *,
    entity_id: str,
    entity_kind: str,
    revision_id_value: str,
    parent_revision_ids: list[str],
    operation: str,
    content_digest: str,
    payload: Mapping[str, object],
    device_id: str,
    actor_id: str,
    created_at: str,
) -> dict[str, JsonValue]:
    """Full pre-persistence validation; returns the sealed document."""
    validate_entity_identity(entity_kind=entity_kind, entity_id=entity_id, device_id=device_id)
    validate_parents(parent_revision_ids, operation=operation)
    if not is_valid_revision_id(revision_id_value):
        raise SyncValidationError("revision_id form is invalid")
    if not is_valid_id(device_id, "device"):
        raise SyncValidationError("device_id is invalid")
    if not is_valid_id(actor_id, "account"):
        raise SyncValidationError("actor_id is invalid")
    _scan_forbidden(payload)
    document = seal_revision_document(
        entity_id=entity_id,
        entity_kind=entity_kind,
        parent_revision_ids=parent_revision_ids,
        operation=operation,
        payload=payload,
        device_id=device_id,
        actor_id=actor_id,
        created_at=created_at,
    )
    sealed = expected_revision_id(document)
    if sealed != revision_id_value:
        raise SyncValidationError("revision_id does not match canonical content")
    digest = expected_content_digest(payload)
    if digest != content_digest:
        raise SyncValidationError("content_digest does not match payload")
    return document
