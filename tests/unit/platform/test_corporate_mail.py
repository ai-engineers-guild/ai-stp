"""Corporate invitation mail service coverage (#201)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ai_stp_platform.corporate_mail import (
    DEFAULT_TEMPLATE,
    CorporateMailTemplateLoader,
    RecordingCorporateMailPort,
    render_template,
)
from ai_stp_platform.organization_models import CorporateMailDelivery
from ai_stp_platform.queue.states import PermanentJobFailure
from ai_stp_worker.handlers import deliver_corporate_invitation as handler


def test_render_template_extracts_subject_and_substitutes() -> None:
    subject, text = render_template(
        "Subject: Hi {{display_name}}\n\nBody for {{display_name}} at {{organization_name}}.",
        {"display_name": "Ada", "organization_name": "Corp"},
    )
    assert subject == "Hi Ada"
    assert "Ada" in text
    assert "Corp" in text


def test_render_template_default_subject_and_unknown_marks() -> None:
    subject, text = render_template("no subject, {{unknown}} stays", {})
    assert subject == "Invitation"
    assert "{{unknown}}" in text


def test_render_template_embedded_default() -> None:
    subject, text = render_template(
        DEFAULT_TEMPLATE,
        {
            "display_name": "Ada",
            "organization_name": "Corp",
            "role": "staff",
            "accept_url": "https://x/inv#token=t",
            "expires_at": "2030-01-01",
        },
    )
    assert "Corp" in subject
    assert "inv#token=t" in text


async def test_template_loader_falls_back_to_embedded() -> None:
    loader = CorporateMailTemplateLoader(client=None, bucket="mail")
    source, template = await loader.load()
    assert source == "embedded"
    assert template == DEFAULT_TEMPLATE


async def test_template_loader_reads_object_storage() -> None:
    class FakeClient:
        async def get_object_bytes(self, *, bucket: str, key: str) -> bytes | None:
            assert bucket == "mail"
            assert key == "tpl.txt"
            return b"Subject: S3 {{display_name}}\n\nHi"

    loader = CorporateMailTemplateLoader(
        client=FakeClient(),  # type: ignore[arg-type]
        bucket="mail",
        key="tpl.txt",
    )
    source, template = await loader.load()
    assert source == "tpl.txt"
    assert template.startswith("Subject: S3")


def test_recording_port_sends_and_fails() -> None:
    port = RecordingCorporateMailPort()
    port.arm_failures(1)
    with pytest.raises(RuntimeError):
        port.send_invitation(to_email="a@b.c", subject="s", text="t")
    port.send_invitation(to_email="a@b.c", subject="s", text="t")
    assert port.sent == [{"to_email": "a@b.c", "subject": "s"}]


def _payload() -> dict[str, object]:
    return {
        "delivery_id": "mail_1",
        "invitation_id": "invite_1",
        "to_email": "a@b.c",
        "display_name": "Ada",
        "organization_name": "Corp",
        "role": "staff",
        "expires_at": "2030-01-01",
        "accept_token": "secret",
    }


def _delivery() -> CorporateMailDelivery:
    return CorporateMailDelivery(
        id="mail_1",
        organization_id="org_1",
        invitation_id="invite_1",
        to_email_normalized="a@b.c",
        display_name="Ada",
        template_key="",
        state="queued",
        attempts=0,
    )


def _session(delivery: CorporateMailDelivery | None) -> AsyncMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=delivery)
    return session


async def test_handler_sends_and_settles_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    port = RecordingCorporateMailPort()
    monkeypatch.setattr(handler, "MAIL_PORT", port)
    monkeypatch.setattr(handler, "ACCEPT_BASE_URL", "https://app.example/en")
    delivery = _delivery()
    await handler.handle_deliver_corporate_invitation(_session(delivery), _payload())
    assert delivery.state == "sent"
    assert delivery.sent_at is not None
    assert delivery.attempts == 1
    assert delivery.template_key == "embedded"
    assert port.sent[0]["to_email"] == "a@b.c"


async def test_handler_marks_failed_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    port = RecordingCorporateMailPort()
    port.arm_failures(1)
    monkeypatch.setattr(handler, "MAIL_PORT", port)
    delivery = _delivery()
    session = _session(delivery)
    with pytest.raises(RuntimeError):
        await handler.handle_deliver_corporate_invitation(session, _payload())
    assert delivery.state == "failed"
    assert delivery.error
    session.commit.assert_awaited()


async def test_handler_rejects_missing_delivery() -> None:
    session = _session(None)
    with pytest.raises(PermanentJobFailure):
        await handler.handle_deliver_corporate_invitation(session, _payload())


async def test_handler_requires_all_fields() -> None:
    payload = _payload()
    payload["accept_token"] = ""
    with pytest.raises(PermanentJobFailure):
        await handler.handle_deliver_corporate_invitation(AsyncMock(), payload)
