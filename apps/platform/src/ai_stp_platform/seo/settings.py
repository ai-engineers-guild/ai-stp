"""Optional SEO serving and enrichment settings. Missing values leave enrichment off."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_stp_contracts.seo import SEO_PROMPT_VERSION, SEO_TEMPLATE_VERSION


class SeoSettings(BaseSettings):
    """Operator settings for public origin and optional LiteLLM enrichment."""

    model_config = SettingsConfigDict(env_prefix="AI_STP_SEO_", extra="ignore")

    public_origin: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("AI_STP_SEO_PUBLIC_ORIGIN", "NEXT_PUBLIC_APP_URL"),
    )
    template_version: str = Field(default=SEO_TEMPLATE_VERSION)
    prompt_version: str = Field(default=SEO_PROMPT_VERSION)
    enrichment_enabled: bool = Field(default=False)
    enrichment_url: str = Field(default="")
    enrichment_credential: str = Field(default="")
    enrichment_model_alias: str = Field(default="seo-writer")
    enrichment_timeout_seconds: float = Field(default=20.0, gt=0)


def load_seo_settings() -> SeoSettings:
    """Load SEO settings; absence of enrichment fields does not fail startup."""
    return SeoSettings()
