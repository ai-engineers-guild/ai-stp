"""Invitation email delivery port (SPEC-010 REQ-1009, SPEC-026)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from types import TracebackType
from typing import Protocol


class _SmtpClient(Protocol):
    """The slice of smtplib.SMTP the delivery path uses (test-fakeable)."""

    def __enter__(self) -> _SmtpClient: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def starttls(self) -> object: ...

    def login(self, user: str, password: str) -> object: ...

    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]: ...


@dataclass(frozen=True)
class SmtpConfig:
    """SMTP relay connection shared by the mail ports (#201).

    One shape covers every non-HTTP delivery path: the mailbox already
    serving the organization's domain, a self-hosted MTA (Mailcow/Postal),
    or a dev catch-all such as Mailpit. Port plus TLS flags follow the
    endpoint — implicit TLS on 465, STARTTLS on 587, or a plain listener
    with both flags off.
    """

    host: str
    port: int = 25
    username: str = ""
    password: str = ""
    use_tls: bool = False
    use_starttls: bool = True
    timeout: float = 15.0
    # Tests inject a fake client; production resolves smtplib lazily.
    client_factory: Callable[[], _SmtpClient] | None = field(
        default=None, compare=False, repr=False
    )

    def send(self, message: EmailMessage) -> None:
        """Transmit one message; raise RuntimeError on transport failure or
        a refused recipient."""
        factory = self.client_factory
        if factory is None:
            # Lazy import keeps platform unit tests free of the smtplib module.
            import smtplib

            cls = smtplib.SMTP_SSL if self.use_tls else smtplib.SMTP

            def _open() -> _SmtpClient:
                return cls(self.host, self.port, timeout=self.timeout)

            factory = _open
        try:
            with factory() as client:
                if not self.use_tls and self.use_starttls:
                    client.starttls()
                if self.username:
                    client.login(self.username, self.password)
                refused = client.send_message(message)
        except OSError as exc:
            msg = f"smtp transport failure: {exc}"
            raise RuntimeError(msg) from exc
        if refused:
            msg = f"smtp refused recipients: {sorted(refused)}"
            raise RuntimeError(msg)


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
        import urllib.error
        import urllib.request

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
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status >= 400:
                    msg = f"resend status {response.status}"
                    raise RuntimeError(msg)
        except urllib.error.URLError as exc:
            msg = "resend transport failure"
            raise RuntimeError(msg) from exc


@dataclass(frozen=True)
class SmtpMailPort:
    """SMTP adapter for invitation mail — company SMTP, a self-hosted MTA,
    or a local catch-all like Mailpit; the endpoint lives in SmtpConfig."""

    smtp: SmtpConfig
    from_address: str = "noreply@ai-stp.invalid"
    accept_base_url: str = ""

    def send_invitation(
        self,
        *,
        to_email: str,
        invitation_id: str,
        object_stable_id: str,
        major: int,
        accept_token: str,
    ) -> None:
        accept_url = (
            f"{self.accept_base_url.rstrip('/')}/invitations/{invitation_id}#token={accept_token}"
            if self.accept_base_url
            else f"{invitation_id}#token={accept_token}"
        )
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = to_email
        message["Subject"] = f"ai_stp access invitation: {object_stable_id} {major}.*"
        message.set_content(
            "You have been invited to access "
            f"{object_stable_id} major {major}.\n\n"
            f"Accept the invitation: {accept_url}\n\n"
            "The link carries a one-time token in its fragment; it is "
            "never sent to our servers."
        )
        self.smtp.send(message)
