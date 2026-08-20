"""Typed settings for the shared platform layer.

Settings come only from explicit environment sources. Required secrets have no
default: a missing required value raises at construction time, which the app
factory turns into a typed startup failure (SPEC-017 REQ-1703).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings. No default URL: it must be provided."""

    model_config = SettingsConfigDict(env_prefix="AI_STP_DB_", extra="ignore")

    url: str = Field(min_length=1)
    pool_size: int = Field(default=5, ge=1)
    command_timeout_seconds: float = Field(default=30.0, gt=0)


class StorageSettings(BaseSettings):
    """RustFS/S3 settings used by readiness and immutable object writes."""

    model_config = SettingsConfigDict(env_prefix="AI_STP_STORAGE_", extra="ignore")

    endpoint: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    access_key_id: str = Field(min_length=1)
    secret_access_key: str = Field(min_length=1)
    region: str = Field(default="us-east-1", min_length=1)
    key_prefix: str = Field(default="objects", min_length=1)
    health_timeout_seconds: float = Field(default=2.0, gt=0)
