"""Invitation email delivery port (SPEC-010 REQ-1009, SPEC-026)."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so credentials never follow a Location header."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


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
    """Resend HTTP adapter. Real network call only when api_key set."""

    api_key: str
    from_address: str = "noreply@ai-stp.invalid"
    api_base: str = "https://api.resend.com"
    # Public web origin for the one-time accept link; the token travels in the
    # URL fragment so servers and proxies never see it (REQ-2714, ADR-0047).
    accept_base_url: str = ""

    def __post_init__(self) -> None:
        # The request carries a Bearer credential and a one-time token, so the
        # origin must be a plain https host: no redirect following (a 307/308
        # would re-POST both to an arbitrary Location), no credentials or
        # extra parts smuggled into the base URL itself.
        parsed = urllib.parse.urlsplit(self.api_base)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            msg = "resend api_base must be a plain https origin"
            raise ValueError(msg)

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
        import json

        accept_url = (
            f"{self.accept_base_url.rstrip('/')}/invitations/{invitation_id}#token={accept_token}"
            if self.accept_base_url
            else f"{invitation_id}#token={accept_token}"
        )
        body = json.dumps(
            {
                "from": self.from_address,
                "to": [to_email],
                "subject": f"ai_stp access invitation: {object_stable_id} {major}.*",
                "text": (
                    "You have been invited to access "
                    f"{object_stable_id} major {major}.\n\n"
                    f"Accept the invitation: {accept_url}\n\n"
                    "The link carries a one-time token in its fragment; it is "
                    "never sent to our servers."
                ),
            }
        )
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
            opener = urllib.request.build_opener(_NoRedirects)
            with opener.open(request, timeout=15) as response:
                if response.status >= 400:
                    msg = f"resend status {response.status}"
                    raise RuntimeError(msg)
        except urllib.error.URLError as exc:
            msg = "resend transport failure"
            raise RuntimeError(msg) from exc
