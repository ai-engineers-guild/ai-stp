"""Per-organization GitLab instance configuration; connector stays optional."""

from __future__ import annotations

import base64

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitLabConnection(BaseModel):
    """One corporate GitLab instance: operator PAT for discovery plus the OAuth
    application that issues expiring user grants for the source connector."""

    base_url: str
    token: SecretStr
    allowed_hosts: list[str] = Field(default_factory=list)
    # OAuth application registered on this instance (instance-wide or group).
    # Absent credentials keep only the operator-PAT discovery paths alive.
    oauth_client_id: str = ""
    oauth_client_secret: SecretStr = Field(default_factory=lambda: SecretStr(""))


class GitLabSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_STP_GITLAB_", extra="ignore")

    connections: dict[str, GitLabConnection] = Field(default_factory=dict)
    # AES-GCM key material for connector token ciphertext; URL-safe base64 of
    # exactly 32 bytes, like the GitHub connector key.
    connector_encryption_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    # Optional PEM bundle with an internal CA root — on-premise instances
    # commonly terminate TLS at a corporate CA that public stores cannot see.
    ca_bundle: str = ""

    @field_validator("connector_encryption_key")
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

    def connection_for(self, organization_id: str) -> GitLabConnection | None:
        """Exact organization key first, then the ``"*"`` wildcard used when a
        deployment points every organization at the same corporate instance."""
        return self.connections.get(organization_id) or self.connections.get("*")

    def connector_credentials(self, organization_id: str) -> tuple[str, str] | None:
        connection = self.connection_for(organization_id)
        if connection is None or not connection.oauth_client_id:
            return None
        return connection.oauth_client_id, connection.oauth_client_secret.get_secret_value()

    def connector_enabled(self, organization_id: str) -> bool:
        return bool(
            self.connector_credentials(organization_id)
            and self.connector_encryption_key.get_secret_value()
        )

    def tls_verify(self) -> str | bool:
        """httpx ``verify`` value: the internal CA bundle path, else public."""
        return self.ca_bundle or True
