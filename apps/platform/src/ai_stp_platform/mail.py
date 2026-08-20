"""Invitation email delivery port (SPEC-010 REQ-1009, SPEC-026)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class MailPort(Protocol):
    """Send invitation mail without becoming an identity source."""

    def send_invitation(
        self,
        *,
        to_email: str,
        invitation_id: str,
        object_stable_id: str,
        major: int,
        accept_token: str,
    ) -> None:
        """Deliver one invitation. Must not log the token."""


@dataclass
class RecordingMailPort:
    """In-memory mail port for tests and local dev."""

    sent: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    fail_times: int = 0
    _failures_left: int = 0

    def __post_init__(self) -> None:
        self._failures_left = self.fail_times

    def arm_failures(self, count: int) -> None:
        """Configure the next ``count`` sends to fail (tests)."""
        self.fail_times = count
        self._failures_left = count

    def send_invitation(
        self,
        *,
        to_email: str,
        invitation_id: str,
        object_stable_id: str,
        major: int,
        accept_token: str,
    ) -> None:
        if self._failures_left > 0:
            self._failures_left -= 1
            msg = "transient mail failure"
            raise RuntimeError(msg)
        # Store only a redacted receipt — never the raw token.
        self.sent.append(
            {
                "to_email": to_email,
                "invitation_id": invitation_id,
                "object_stable_id": object_stable_id,
                "major": major,
                "token_present": bool(accept_token),
            }
        )


@dataclass(frozen=True)
class ResendMailPort:
    """Resend HTTP adapter shell. Real network call only when api_key set."""

    api_key: str
    from_address: str = "noreply@ai-stp.invalid"
    api_base: str = "https://api.resend.com"

    def send_invitation(
        self,
        *,
        to_email: str,
        invitation_id: str,
        object_stable_id: str,
        major: int,
        accept_token: str,
    ) -> None:
        if not self.api_key:
            # No key configured: treat as dry-run success for non-prod.
            return
        # Avoid importing httpx at module level so platform unit tests need no client.
        import urllib.error
        import urllib.request

        body = (
            f'{{"from":"{self.from_address}","to":["{to_email}"],'
            f'"subject":"ai_stp access invitation",'
            f'"text":"Invitation {invitation_id} for {object_stable_id} major {major}. '
            f'Token is delivered out of band to the owner flow."}}'
        )
        # Token is intentionally not included in the body above for safe defaults;
        # production templates would use a one-time accept URL owned by web.
        del accept_token
        request = urllib.request.Request(
            f"{self.api_base.rstrip('/')}/emails",
            data=body.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status >= 400:
                    msg = f"resend status {response.status}"
                    raise RuntimeError(msg)
        except urllib.error.URLError as exc:
            msg = "resend transport failure"
            raise RuntimeError(msg) from exc
