"""Deliver corporate invitation email job (#201).

The ledger row in ``corporate_mail_delivery`` is the service's own record:
created ``queued`` by the API, settled ``sent``/``failed`` here. The one-time
token lives only in the job payload until the mail goes out — the ledger and
the audit trail never see it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.corporate_mail import (
    DEFAULT_CONFIRM_TEMPLATE,
    DEFAULT_CONFIRM_TEMPLATE_KEY,
    CorporateMailTemplateLoader,
    RecordingCorporateMailPort,
    render_template,
)
from ai_stp_platform.organization_models import CorporateMailDelivery
from ai_stp_platform.queue.states import PermanentJobFailure

# Process-wide defaults; __main__ replaces them from settings and tests may
# replace them. ACCEPT_BASE_URL builds the fragment-token accept link.
MAIL_PORT = RecordingCorporateMailPort()
TEMPLATE_LOADER = CorporateMailTemplateLoader()
CONFIRM_TEMPLATE_LOADER = CorporateMailTemplateLoader(
    key=DEFAULT_CONFIRM_TEMPLATE_KEY, fallback=DEFAULT_CONFIRM_TEMPLATE
)
ACCEPT_BASE_URL = ""


def _require_str(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        msg = f"deliver_corporate_invitation requires {name}"
        raise PermanentJobFailure(msg)
    return value


async def handle_deliver_corporate_invitation(
    session: AsyncSession, payload: Mapping[str, object]
) -> None:
    delivery_id = _require_str(payload, "delivery_id")
    invitation_id = _require_str(payload, "invitation_id")
    to_email = _require_str(payload, "to_email")
    display_name = _require_str(payload, "display_name")
    organization_name = _require_str(payload, "organization_name")
    role = _require_str(payload, "role")
    expires_at = _require_str(payload, "expires_at")

    delivery = await session.get(CorporateMailDelivery, delivery_id)
    if delivery is None:
        msg = f"mail delivery {delivery_id} not found"
        raise PermanentJobFailure(msg)

    if payload.get("mail_variant") == "confirmation":
        confirm_token = _require_str(payload, "confirm_token")
        confirm_url = (
            f"{ACCEPT_BASE_URL.rstrip('/')}"
            f"/corporate-invitations/{invitation_id}/confirm#token={confirm_token}"
            if ACCEPT_BASE_URL
            else f"{invitation_id}/confirm#token={confirm_token}"
        )
        template_source, template = await CONFIRM_TEMPLATE_LOADER.load()
        values = {
            "display_name": display_name,
            "organization_name": organization_name,
            "role": role,
            "confirm_url": confirm_url,
            "expires_at": expires_at,
        }
    else:
        accept_token = _require_str(payload, "accept_token")
        accept_url = (
            f"{ACCEPT_BASE_URL.rstrip('/')}"
            f"/corporate-invitations/{invitation_id}#token={accept_token}"
            if ACCEPT_BASE_URL
            else f"{invitation_id}#token={accept_token}"
        )
        template_source, template = await TEMPLATE_LOADER.load()
        values = {
            "display_name": display_name,
            "organization_name": organization_name,
            "role": role,
            "accept_url": accept_url,
            "expires_at": expires_at,
        }
    subject, text = render_template(template, values)

    delivery.attempts += 1
    delivery.template_key = template_source
    try:
        delivery.provider_message_id = MAIL_PORT.send_invitation(
            to_email=to_email,
            subject=subject,
            text=text,
        )
    except Exception as exc:
        # The runner rolls back handler failures, so the failure verdict is
        # committed before re-raising for the queue's retry machinery.
        delivery.state = "failed"
        delivery.error = f"{type(exc).__name__}: {exc}"[:512]
        await session.commit()
        raise
    delivery.state = "sent"
    delivery.error = None
    delivery.sent_at = datetime.now(UTC)
