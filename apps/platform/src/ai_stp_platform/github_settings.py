"""Explicit, optional GitHub App configuration; never reuse login credentials."""

from __future__ import annotations

import base64
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type ConnectorPurpose = Literal["source", "administration"]


class GitHubConnectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_STP_GITHUB_CONNECTOR_", extra="ignore", hide_input_in_errors=True
    )

    client_id: str = ""
    client_secret: SecretStr = Field(default_factory=lambda: SecretStr(""))
    app_slug: str = ""
    encryption_key: SecretStr = Field(default_factory=lambda: SecretStr(""))

    @field_validator("app_slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if value and (
            len(value) > 100 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in value)
        ):
            raise ValueError("GitHub App slug must be lowercase letters, digits and hyphens")
        return value

    @field_validator("encryption_key")
    @classmethod
    def _key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw:
            try:
                valid = len(base64.b64decode(raw, altchars=b"-_", validate=True)) == 32
            except (ValueError, UnicodeEncodeError):
                valid = False
            if not valid:
                raise ValueError("connector encryption key must encode exactly 32 bytes")
        return value

    def credentials(self, purpose: ConnectorPurpose) -> tuple[str, str, str]:
        # ``purpose`` remains part of the account consent and token binding, but
        # both purposes use the same one GitHub App registration.
        _ = purpose
        return self.client_id, self.client_secret.get_secret_value(), self.app_slug

    def enabled(self, purpose: ConnectorPurpose) -> bool:
        return bool(all(self.credentials(purpose)) and self.encryption_key.get_secret_value())
