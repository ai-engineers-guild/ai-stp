"""Typed API settings composed from explicit environment sources (SPEC-017).

No secret has a default. A missing required value raises a ValidationError at
construction, which the app factory surfaces as a typed startup failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_stp_contracts.catalog import (
    USAGE_METRICS_DEFAULT_RETENTION_SECONDS,
    USAGE_METRICS_DEFAULT_SECRET_ROTATION_SECONDS,
    USAGE_METRICS_DEFAULT_WINDOW_SECONDS,
    USAGE_METRICS_ENABLED_BY_DEFAULT,
)
from ai_stp_platform.catalog_usage import CatalogUsagePolicy
from ai_stp_platform.settings import DatabaseSettings, StorageSettings

# Fail-closed single-node HTTP gate (SPEC-010 REQ-1015, ADR-0128).
RATE_LIMIT_OVERALL_REQUESTS = 100
RATE_LIMIT_OVERALL_WINDOW_SECONDS = 60
RATE_LIMIT_IP_REQUESTS = 1000
RATE_LIMIT_IP_WINDOW_SECONDS = 3600
RATE_LIMIT_MAX_KEYS = 2048


def _distribution_version() -> str:
    """The version of the installed API distribution.

    Falls back to `0.0.0` only when the package is not installed at all, which
    happens when the module is imported straight from a source checkout. A
    deployment always installs it, so the fallback marks "not a real build"
    rather than guessing a number.
    """
    try:
        return installed_version("ai-stp-api")
    except PackageNotFoundError:
        return "0.0.0"


class ServiceSettings(BaseSettings):
    """Service-level settings for the API process."""

    model_config = SettingsConfigDict(env_prefix="AI_STP_API_", extra="ignore")

    environment: str = Field(default="dev")
    # Read from the installed distribution rather than written here. The literal
    # that used to sit in this line said `0.1.0` while every package in the
    # workspace said `0.0.1`, so `/v1/system/version` advertised a release that
    # does not exist — nothing kept the two in step, and nothing noticed.
    #
    # Removing the literal was not enough. `env_prefix` made `AI_STP_API_VERSION`
    # outrank the distribution, `.env.prod.example` told the operator to set it,
    # and the value it named was the same dead `0.1.0`. Production served that
    # number for another day while the container underneath reported `0.0.2`.
    #
    # The alias takes this field out of the prefix, so a leftover
    # `AI_STP_API_VERSION` in anyone's environment is simply not consulted. The
    # version of a running build is a fact of the build; configuration that can
    # disagree with it is a second source of truth for something that has one.
    version: str = Field(
        default_factory=_distribution_version,
        validation_alias=AliasChoices("ai_stp_api_build_version"),
    )
    # Optional deploy identity for safe diagnostics (REQ-2411). Never a secret.
    git_commit: str | None = Field(default=None)
    log_dir: Path = Field(default=Path("logs"))
    otel_exporter_endpoint: str | None = Field(default=None)
    # Runtime-only OTLP headers, formatted as comma-separated ``name=value`` pairs.
    # The values may be credentials and must never be logged or copied into evidence.
    otel_exporter_headers: str = Field(default="")
    # The single-node MVP policy `SPEC-010` `REQ-1015` / `ADR-0128` names. It is
    # the default rather than an opt-in because `SlidingWindowLimiter.allow`
    # returns `True` for everything when `maximum` is `0`: an environment that
    # simply never mentioned the variable ran a public API with no limit, and
    # absence looked exactly like a deliberate decision to switch the limiter
    # off. Measured on the deployed environment before the first fail-closed
    # default: 150 requests in one burst returned 150 x 200.
    #
    # `0` still turns that dimension off, and still means that — it just has to
    # be asked for now. The retired `AI_STP_API_RATE_LIMIT_REQUESTS` name is not
    # an alias: `extra=ignore` drops it so a leftover `0` cannot fail open.
    rate_limit_overall_requests: int = Field(default=RATE_LIMIT_OVERALL_REQUESTS, ge=0)
    rate_limit_overall_window_seconds: int = Field(default=RATE_LIMIT_OVERALL_WINDOW_SECONDS, gt=0)
    rate_limit_ip_requests: int = Field(default=RATE_LIMIT_IP_REQUESTS, ge=0)
    rate_limit_ip_window_seconds: int = Field(default=RATE_LIMIT_IP_WINDOW_SECONDS, gt=0)
    rate_limit_max_keys: int = Field(default=RATE_LIMIT_MAX_KEYS, gt=0)

    def otel_headers(self) -> dict[str, str]:
        """Return validated OTLP headers without exposing their values in errors."""
        if not self.otel_exporter_headers.strip():
            return {}
        headers: dict[str, str] = {}
        for item in self.otel_exporter_headers.split(","):
            name, separator, value = item.partition("=")
            normalized = name.strip()
            if not separator or not normalized or not value:
                msg = "otel exporter headers must use name=value entries"
                raise ValueError(msg)
            headers[normalized] = value.strip()
        return headers


class AuthSettings(BaseSettings):
    """OAuth, opaque session and device-challenge settings (ADR-0041).

    ``secret_key`` signs the OAuth handshake cookie and device challenge nonces.
    Provider client secrets are required only when the corresponding provider is
    enabled; empty values disable that provider at startup registration time.
    """

    model_config = SettingsConfigDict(env_prefix="AI_STP_AUTH_", extra="ignore")

    secret_key: str = Field(min_length=32)
    # Browser-facing origin for post-login redirects (public site origin).
    public_base_url: str = Field(default="http://localhost:8000")
    # Optional separate origin for OAuth redirect_uri when it must match a
    # provider-registered callback that differs from the public web origin
    # (e.g. Google client still has :8000 while the site is on :3000 in local dev).
    # Empty → use public_base_url.
    oauth_redirect_base_url: str = Field(default="")
    session_ttl_seconds: int = Field(default=1_209_600, ge=60)  # 14 days
    challenge_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    cookie_name: str = Field(default="ai_stp_session")
    device_cookie_name: str = Field(default="ai_stp_browser_device")
    geoip_city_db_path: Path | None = Field(default=None)
    csrf_cookie_name: str = Field(default="ai_stp_csrf")
    csrf_header_name: str = Field(default="X-CSRF-Token")
    cookie_secure: bool = Field(default=True)
    cookie_samesite: str = Field(default="lax")
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")
    github_client_id: str = Field(default="")
    github_client_secret: str = Field(default="")
    # Comma-separated account ids that may perform audited admin reads.
    admin_account_ids: str = Field(default="")

    # Every browser origin this deployment answers on whose callback is also
    # registered in the provider console, comma-separated. `#62`: the aiguild
    # migration made the login page reachable on a second domain, while the
    # callback stayed pinned to the first — so the authlib state lived in a
    # cookie on the domain that started the flow, the callback landed on the
    # other one, and every sign-in from the canonical domain failed.
    #
    # An allowlist rather than the request `Host`, which a proxy controls: the
    # request may select among the origins the operator already declared, and
    # nothing else. A deployment that names none behaves exactly as before.
    oauth_callback_origins: str = Field(default="")

    def oauth_callback_base(self) -> str:
        """Origin used to build provider redirect_uri (must match console)."""
        base = self.oauth_redirect_base_url.strip() or self.public_base_url
        return base.rstrip("/")

    def oauth_callback_bases(self) -> tuple[str, ...]:
        """The default origin first, then every additional declared one.

        Order matters: the first entry is what a request whose origin is not
        declared falls back to, which is the single-domain behaviour this
        deployment had before the list existed.
        """
        default = self.oauth_callback_base()
        extra = [
            item.strip().rstrip("/")
            for item in self.oauth_callback_origins.split(",")
            if item.strip()
        ]
        ordered = [default]
        ordered.extend(item for item in extra if item != default)
        return tuple(ordered)

    @field_validator("cookie_samesite")
    @classmethod
    def _samesite_allowed(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            msg = "cookie_samesite must be lax, strict or none"
            raise ValueError(msg)
        return normalized

    def admin_ids(self) -> frozenset[str]:
        """Return the configured admin account id set."""
        parts = [part.strip() for part in self.admin_account_ids.split(",")]
        return frozenset(part for part in parts if part)

    def provider_enabled(self, provider: str) -> bool:
        """Report whether both client id and secret are configured for provider."""
        if provider == "google":
            return bool(self.google_client_id and self.google_client_secret)
        if provider == "github":
            return bool(self.github_client_id and self.github_client_secret)
        return False


class CatalogSettings(BaseSettings):
    """Anonymous catalog settings (ADR-0042 cursor signing).

    ``cursor_signing_secret`` is a dedicated env secret (not committed). When
    unset in local tests, callers inject a value; production must set
    ``AI_STP_CATALOG_CURSOR_SECRET``.
    """

    model_config = SettingsConfigDict(env_prefix="AI_STP_CATALOG_", extra="ignore")

    cursor_signing_secret: str = Field(min_length=32)
    usage_enabled: bool = USAGE_METRICS_ENABLED_BY_DEFAULT
    usage_window_seconds: int = USAGE_METRICS_DEFAULT_WINDOW_SECONDS
    usage_retention_seconds: int = USAGE_METRICS_DEFAULT_RETENTION_SECONDS
    usage_secret_rotation_seconds: int = USAGE_METRICS_DEFAULT_SECRET_ROTATION_SECONDS
    usage_secret: str = ""

    @model_validator(mode="after")
    def _usage_bounds(self) -> CatalogSettings:
        CatalogUsagePolicy(
            enabled=self.usage_enabled,
            window_seconds=self.usage_window_seconds,
            retention_seconds=self.usage_retention_seconds,
            secret_rotation_seconds=self.usage_secret_rotation_seconds,
            secret=self.usage_secret,
        ).validate()
        return self

    def usage_policy(self) -> CatalogUsagePolicy:
        return CatalogUsagePolicy(
            enabled=self.usage_enabled,
            window_seconds=self.usage_window_seconds,
            retention_seconds=self.usage_retention_seconds,
            secret_rotation_seconds=self.usage_secret_rotation_seconds,
            secret=self.usage_secret,
        )


class ContentSettings(BaseSettings):
    """Scoped repository import credential (SPEC-054). Empty token forbids import."""

    model_config = SettingsConfigDict(env_prefix="AI_STP_CONTENT_", extra="ignore")

    import_token: str = Field(default="")


class ComplaintSettings(BaseSettings):
    """Limits for public complaint intake (SPEC-052)."""

    model_config = SettingsConfigDict(env_prefix="AI_STP_COMPLAINT_", extra="ignore")

    submitter_limit: int = Field(default=1, ge=1)
    submitter_window_seconds: int = Field(default=300, ge=1)
    target_limit: int = Field(default=50, ge=1)
    target_window_seconds: int = Field(default=60, ge=1)


@dataclass(frozen=True)
class Settings:
    """Bundle of the independently sourced settings groups."""

    service: ServiceSettings
    database: DatabaseSettings
    storage: StorageSettings
    auth: AuthSettings
    catalog: CatalogSettings
    complaint: ComplaintSettings = field(default_factory=ComplaintSettings)
    content: ContentSettings = field(default_factory=ContentSettings)


def load_settings() -> Settings:
    """Construct every settings group; a missing required value raises here."""
    return Settings(
        service=ServiceSettings(),
        database=DatabaseSettings(),  # pyright: ignore[reportCallIssue]
        storage=StorageSettings(),  # pyright: ignore[reportCallIssue]
        auth=AuthSettings(),  # pyright: ignore[reportCallIssue]
        catalog=CatalogSettings(),  # pyright: ignore[reportCallIssue]
        complaint=ComplaintSettings(),
        content=ContentSettings(),
    )
