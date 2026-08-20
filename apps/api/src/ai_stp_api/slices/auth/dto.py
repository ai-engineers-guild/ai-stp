"""Auth boundary DTOs (OpenAPI / envelope data)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SessionIssuedData(BaseModel):
    """Response body after a successful login or link that issues a session.

    ``session_token`` is present only for CLI/json clients. Web clients receive
    the token solely via the HttpOnly cookie and never see it in the body.
    """

    account_id: str
    session_token: str | None = None
    link_state: str = Field(description="pending|linked|conflict|revoked")


class LogoutData(BaseModel):
    """Logout acknowledgement."""

    revoked: bool


class LinkStartData(BaseModel):
    """Step-up link initiation result (redirect URL for the browser)."""

    authorization_url: str
