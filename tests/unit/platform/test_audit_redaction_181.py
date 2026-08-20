"""Audit redaction covers invitation/token/diagnostics keys (SPEC-026)."""

from __future__ import annotations

from ai_stp_api.audit import redact_payload

pytestmark = __import__("pytest").mark.platform


def test_redaction_drops_invitation_and_diagnostics_secrets() -> None:
    cleaned = redact_payload(
        {
            "invitation_id": "invite_1",
            "accept_token": "raw-secret",
            "invitation_token": "raw-secret-2",
            "email_body": "hello token",
            "diagnostics": "HOME=/Users/me",
            "attestation_signature": "sig",
            "stable_id": "component_1",
        }
    )
    assert cleaned == {"invitation_id": "invite_1", "stable_id": "component_1"}
