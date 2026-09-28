"""Typed worker settings from explicit environment sources (SPEC-017)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_stp_platform.queue.engine import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_LEASE_TIMEOUT_SECONDS,
)
from ai_stp_platform.settings import DatabaseSettings


class WorkerSettings(BaseSettings):
    """Runtime settings for the worker process."""

    model_config = SettingsConfigDict(env_prefix="AI_STP_WORKER_", extra="ignore")

    worker_id: str = Field(default="worker")
    batch_size: int = Field(default=10, ge=1)
    poll_interval_seconds: float = Field(default=1.0, gt=0)
    drain_timeout_seconds: float = Field(default=30.0, gt=0)
    lease_timeout_seconds: float = Field(default=DEFAULT_LEASE_TIMEOUT_SECONDS, gt=0)
    heartbeat_interval_seconds: float = Field(
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        gt=0,
    )
    log_dir: Path = Field(default=Path("logs"))
    # Invitation delivery (REQ-2613): when resend_api_key is empty the worker
    # falls back to the recording port — mails are kept in memory, not sent.
    resend_api_key: str = Field(default="")
    mail_from_address: str = Field(default="noreply@ai-stp.invalid")
    # Public web origin used to build the one-time accept link carried by the
    # invitation email, e.g. https://app.example.invalid (NEXT_PUBLIC_APP_URL).
    invitation_base_url: str = Field(default="")
    # Corporate invitation mail (#201): a dedicated sender on its own domain.
    # corporate_resend_api_key falls back to resend_api_key when empty.
    corporate_resend_api_key: str = Field(default="")
    corporate_mail_from_address: str = Field(default="invitations@ai-stp.invalid")
    # S3 location of the invitation mail template; missing object falls back
    # to the embedded default. Empty bucket selects the storage asset bucket.
    corporate_mail_template_bucket: str = Field(default="")
    corporate_mail_template_key: str = Field(default="mail/corporate-invitation.txt")


@dataclass(frozen=True)
class Settings:
    """Bundle of worker and database settings."""

    worker: WorkerSettings
    database: DatabaseSettings


def load_settings() -> Settings:
    """Construct settings; a missing required database value raises here."""
    return Settings(
        worker=WorkerSettings(),
        database=DatabaseSettings(),  # pyright: ignore[reportCallIssue]
    )
