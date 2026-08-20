"""Deliver grant invitation email job (SPEC-026)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.mail import RecordingMailPort

# Process-wide default port; tests may replace.
MAIL_PORT = RecordingMailPort()


async def handle_deliver_invitation(session: AsyncSession, payload: Mapping[str, object]) -> None:
    del session  # delivery is external; invitation row already durable
    invitation_id = payload.get("invitation_id")
    to_email = payload.get("to_email")
    object_stable_id = payload.get("object_stable_id")
    major = payload.get("major")
    accept_token = payload.get("accept_token")
    if not isinstance(invitation_id, str) or not isinstance(to_email, str):
        msg = "deliver_invitation requires invitation_id and to_email"
        raise ValueError(msg)
    if not isinstance(object_stable_id, str) or not isinstance(major, int):
        msg = "deliver_invitation requires object_stable_id and major"
        raise ValueError(msg)
    if not isinstance(accept_token, str):
        msg = "deliver_invitation requires accept_token"
        raise ValueError(msg)
    MAIL_PORT.send_invitation(
        to_email=to_email,
        invitation_id=invitation_id,
        object_stable_id=object_stable_id,
        major=major,
        accept_token=accept_token,
    )
