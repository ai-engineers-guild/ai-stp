"""Corporate invitation mail service (#201).

Three replaceable pieces so the service can grow without touching callers:

- ``CorporateMailTemplateLoader`` — reads the message template from the S3
  asset bucket and falls back to the embedded default. Templates are plain
  text; a leading ``Subject:`` line becomes the subject, ``{{name}}``
  placeholders are substituted by name.
- ``CorporateMailPort`` — the delivery port. ``ResendCorporateMailPort`` talks
  to Resend over HTTP from a dedicated corporate sender; the recording port
  keeps sends in memory for tests and unconfigured deployments.
- ``corporate_mail_delivery`` rows — the ledger. One row per invitation is
  created in the API transaction and settled by the worker handler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from ai_stp_platform.mail import SmtpConfig
from ai_stp_platform.storage.object_store import ObjectClient

DEFAULT_TEMPLATE_KEY = "mail/corporate-invitation.txt"
DEFAULT_CONFIRM_TEMPLATE_KEY = "mail/corporate-invitation-confirm.txt"

DEFAULT_TEMPLATE = (
    "Subject: {{organization_name}} invitation\n"
    "\n"
    "Hello {{display_name}},\n"
    "\n"
    "You have been invited to join {{organization_name}} as {{role}}.\n"
    "\n"
    "Accept the invitation: {{accept_url}}\n"
    "\n"
    "The link carries a one-time token in its fragment and expires at "
    "{{expires_at}}.\n"
)

DEFAULT_CONFIRM_TEMPLATE = (
    "Subject: Confirm your {{organization_name}} membership\n"
    "\n"
    "Hello {{display_name}},\n"
    "\n"
    "A membership in {{organization_name}} was claimed for this address.\n"
    "\n"
    "Confirm it to activate your access: {{confirm_url}}\n"
    "\n"
    "If you did not expect this, ignore this mail. The link expires at "
    "{{expires_at}}.\n"
)

_PLACEHOLDER = re.compile(r"{{\s*([a-z_]+)\s*}}")


def render_template(template: str, values: dict[str, str]) -> tuple[str, str]:
    """Split a template into (subject, body) and substitute ``{{name}}`` marks."""
    lines = template.splitlines()
    subject = "Invitation"
    body_lines = lines
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or subject
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)

    def render(text: str) -> str:
        return _PLACEHOLDER.sub(lambda mark: values.get(mark.group(1), mark.group(0)), text)

    return render(subject), render("\n".join(body_lines))


@dataclass
class CorporateMailTemplateLoader:
    """Load the corporate invitation template from object storage."""

    client: ObjectClient | None = None
    bucket: str = ""
    key: str = DEFAULT_TEMPLATE_KEY
    fallback: str = DEFAULT_TEMPLATE

    async def load(self) -> tuple[str, str]:
        """Return (template_source_label, template_text), embedded fallback."""
        if self.client is not None and self.bucket:
            payload = await self.client.get_object_bytes(bucket=self.bucket, key=self.key)
            if payload:
                return self.key, payload.decode("utf-8")
        return "embedded", self.fallback


class CorporateMailPort(Protocol):
    """Send one corporate invitation mail from the dedicated sender."""

    def send_invitation(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> str | None:
        """Deliver one rendered mail; return the provider message id if any."""


@dataclass
class RecordingCorporateMailPort:
    """In-memory corporate mail port for tests and local dev."""

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
        subject: str,
        text: str,
    ) -> str | None:
        if self._failures_left > 0:
            self._failures_left -= 1
            msg = "transient corporate mail failure"
            raise RuntimeError(msg)
        self.sent.append({"to_email": to_email, "subject": subject})
        return None


@dataclass(frozen=True)
class ResendCorporateMailPort:
    """Resend HTTP adapter on a dedicated corporate sender address/domain."""

    api_key: str
    from_address: str
    api_base: str = "https://api.resend.com"

    def send_invitation(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> str | None:
        if not self.api_key:
            return None
        # Lazy import keeps platform unit tests free of a network client.
        import json
        import urllib.error
        import urllib.request

        body = json.dumps(
            {
                "from": self.from_address,
                "to": [to_email],
                "subject": subject,
                "text": text,
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
                payload = json.loads(response.read() or b"{}")
        except urllib.error.URLError as exc:
            msg = "resend transport failure"
            raise RuntimeError(msg) from exc
        message_id = payload.get("id")
        return message_id if isinstance(message_id, str) else None


@dataclass(frozen=True)
class SmtpCorporateMailPort:
    """SMTP adapter on the dedicated corporate sender — the company
    mailbox's SMTP, a self-hosted MTA, or a dev catch-all; the endpoint
    shape lives in SmtpConfig. SMTP yields no provider message id."""

    smtp: SmtpConfig
    from_address: str

    def send_invitation(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> str | None:
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text)
        self.smtp.send(message)
        return None
