"""Sprint-1 platform storage models (SPEC-020).

These mappings own storage integrity only. Domain semantics stay with the
active specifications that define accounts, devices, passports and catalog
objects.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_stp_platform.db import Base


class Account(Base):
    """Internal platform account, separated from provider identities."""

    __tablename__ = "account"
    __table_args__ = (
        Index(
            "uq_account_handle_normalized",
            "handle_normalized",
            unique=True,
            postgresql_where=text("handle_normalized IS NOT NULL"),
        ),
        Index(
            "uq_account_display_name_normalized",
            "display_name_normalized",
            unique=True,
            postgresql_where=text("display_name_normalized IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Existing accounts predate legal onboarding and remain active after the
    # additive migration. New OAuth accounts become active only on acceptance.
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    show_profile_publicly: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    allow_publisher_listing: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    handle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    handle_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name_normalized: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OAuthIdentity(Base):
    """Provider identity linked many-to-one to an account."""

    __tablename__ = "oauth_identity"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_oauth_identity_provider_subject"),
        CheckConstraint(
            "state in ('pending', 'linked', 'conflict', 'revoked')",
            name="ck_oauth_identity_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Provider-hosted avatar URL (HTTPS). Never email on the public wire (SPEC-013).
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Account] = relationship()


class Device(Base):
    """Registered CLI installation or browser session device."""

    __tablename__ = "device"
    __table_args__ = (
        UniqueConstraint("account_id", "public_key", name="uq_device_account_public_key"),
        CheckConstraint("state in ('active', 'revoked')", name="ck_device_state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    public_key: Mapped[str] = mapped_column(Text)
    device_type: Mapped[str] = mapped_column(String(32), default="cli")
    approximate_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Account] = relationship()


class AccountSession(Base):
    """Durable server session bound to one account and optionally one device."""

    __tablename__ = "account_session"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="SET NULL"), nullable=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship()
    device: Mapped[Device | None] = relationship()


class DeviceAuthorization(Base):
    """Pending CLI device-code authorization (RFC 8628, SPEC-002)."""

    __tablename__ = "device_authorization"
    __table_args__ = (
        UniqueConstraint("user_code", name="uq_device_authorization_user_code"),
        CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'consumed')",
            name="ck_device_authorization_status",
        ),
    )

    device_code: Mapped[str] = mapped_column(String(256), primary_key=True)
    user_code: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CatalogMetadata(Base):
    """Server metadata for a private draft or published catalog version.

    One row is one (object_kind, stable_id, version) identity. Publication and
    trust fields are additive for the anonymous public catalog (SPEC-021); the
    passport document is the projection source for card and detail reads.
    """

    __tablename__ = "catalog_metadata"
    __table_args__ = (
        UniqueConstraint(
            "object_kind",
            "stable_id",
            "version",
            name="uq_catalog_metadata_kind_stable_id_version",
        ),
        UniqueConstraint("stable_id", "version", name="uq_catalog_metadata_stable_id_version"),
        CheckConstraint(
            "trust_lane is null or trust_lane in ('authoritative', 'experimental')",
            name="ck_catalog_metadata_trust_lane",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), index=True
    )
    object_kind: Mapped[str] = mapped_column(String(32))
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_revision_id: Mapped[str] = mapped_column(String(73))
    visibility: Mapped[str] = mapped_column(String(32), default="private")
    lifecycle_state: Mapped[str] = mapped_column(String(32), default="draft")
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trust_lane: Mapped[str | None] = mapped_column(String(32), nullable=True)
    author_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    component_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    likes_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    passport_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    passport_document: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    # Mutable catalog copy. It is deliberately outside the immutable passport.
    presentation_bio: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    #: Safe provider support evidence projection (SPEC-033, ADR-0072). Raw
    #: reports, signatures and artifact bytes are never stored here.
    support_evidence: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    #: Safety checks summary for catalog cards (#270): percent, status, check list.
    checks_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[Account] = relationship()


class CatalogIdentity(Base):
    """One owned catalog line per component stable ID (SPEC-059)."""

    __tablename__ = "catalog_identity"
    __table_args__ = (
        UniqueConstraint("canonical_name_normalized", name="uq_catalog_identity_canonical"),
    )

    stable_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(80))
    canonical_name_normalized: Mapped[str] = mapped_column(String(80))
    ownership_revision_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogIdentityLocale(Base):
    """Unique RU/EN presentation name for one catalog line."""

    __tablename__ = "catalog_identity_locale"
    __table_args__ = (
        CheckConstraint("locale in ('ru', 'en')", name="ck_catalog_identity_locale"),
        UniqueConstraint("stable_id", "locale", name="uq_catalog_identity_locale_line"),
        UniqueConstraint(
            "locale", "display_name_normalized", name="uq_catalog_identity_locale_name"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stable_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("catalog_identity.stable_id", ondelete="CASCADE"), index=True
    )
    locale: Mapped[str] = mapped_column(String(8))
    display_name: Mapped[str] = mapped_column(String(80))
    display_name_normalized: Mapped[str] = mapped_column(String(80))


CATALOG_SEARCH_VECTOR_SQL = "to_tsvector('simple', coalesce(search_text, ''))"


class CatalogSearchProjection(Base):
    """One latest public catalog object for SQL search (ADR-0151)."""

    __tablename__ = "catalog_search_projection"
    __table_args__ = (
        UniqueConstraint(
            "object_kind",
            "stable_id",
            name="uq_catalog_search_projection_kind_stable_id",
        ),
        UniqueConstraint(
            "catalog_metadata_id",
            name="uq_catalog_search_projection_metadata_id",
        ),
        CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_catalog_search_projection_kind",
        ),
        CheckConstraint(
            "lifecycle_state in ('active', 'deprecated', 'blocked')",
            name="ck_catalog_search_projection_lifecycle",
        ),
        Index(
            "ix_catalog_search_projection_fts",
            "search_vector",
            postgresql_using="gin",
        ),
        Index(
            "ix_catalog_search_projection_tags",
            "tags",
            postgresql_using="gin",
        ),
        Index(
            "ix_catalog_search_projection_harnesses",
            "harness_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_catalog_search_projection_updated",
            "object_kind",
            "updated_at",
            "stable_id",
        ),
        Index(
            "ix_catalog_search_projection_likes",
            "object_kind",
            "likes_count",
            "updated_at",
            "stable_id",
        ),
        Index(
            "ix_catalog_search_projection_updated_active",
            "object_kind",
            "updated_at",
            "stable_id",
            postgresql_where=text("lifecycle_state = 'active'"),
        ),
        Index(
            "ix_catalog_search_projection_likes_active",
            "object_kind",
            "likes_count",
            "updated_at",
            "stable_id",
            postgresql_where=text("lifecycle_state = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_metadata_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_metadata.id", ondelete="CASCADE"), index=True
    )
    object_kind: Mapped[str] = mapped_column(String(32))
    stable_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    version_major: Mapped[int] = mapped_column(Integer)
    version_minor: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    owner_account_id: Mapped[str] = mapped_column(String(64))
    component_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    harness_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}"
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, server_default="{}")
    tag_aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}"
    )
    trust_lane: Mapped[str] = mapped_column(String(32))
    component_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    likes_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    support_tier: Mapped[str] = mapped_column(String(32), default="primary")
    support_state: Mapped[str] = mapped_column(String(32), default="missing")
    support_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    search_text: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed(CATALOG_SEARCH_VECTOR_SQL, persisted=True)
    )


class RepositoryMetric(Base):
    """Mutable, best-effort public metrics for one canonical repository."""

    __tablename__ = "repository_metric"

    repository: Mapped[str] = mapped_column(String(512), primary_key=True)
    github_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ExternalProduct(Base):
    """Mutable curated product/service presentation, deduplicated by domain."""

    __tablename__ = "external_product"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_domain: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    primary_url: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExternalProductLocale(Base):
    """Curated localized service presentation."""

    __tablename__ = "external_product_locale"
    __table_args__ = (
        UniqueConstraint(
            "external_product_id", "locale", name="uq_external_product_locale_identity"
        ),
        CheckConstraint("locale in ('ru', 'en')", name="ck_external_product_locale_locale"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_product_id: Mapped[int] = mapped_column(
        ForeignKey("external_product.id", ondelete="CASCADE"), index=True
    )
    locale: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(2000))
    source_url: Mapped[str] = mapped_column(String(512))


class CountryLocale(Base):
    """Curated country name used by localized public projections."""

    __tablename__ = "country_locale"
    __table_args__ = (
        UniqueConstraint("country_code", "locale", name="uq_country_locale_identity"),
        CheckConstraint("locale in ('ru', 'en')", name="ck_country_locale_locale"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_country_locale_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    locale: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(160))


class ExternalProductCountry(Base):
    """Country roof membership for one curated external product."""

    __tablename__ = "external_product_country"
    external_product_id: Mapped[int] = mapped_column(
        ForeignKey("external_product.id", ondelete="CASCADE"), primary_key=True
    )
    country_code: Mapped[str] = mapped_column(String(2), primary_key=True, index=True)


class CatalogExternalProduct(Base):
    __tablename__ = "catalog_external_product"
    catalog_metadata_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_metadata.id", ondelete="CASCADE"), primary_key=True
    )
    external_product_id: Mapped[int] = mapped_column(
        ForeignKey("external_product.id", ondelete="CASCADE"), primary_key=True
    )


class ComponentMedia(Base):
    """Ordered, normalized presentation media for one component (SPEC-035)."""

    __tablename__ = "component_media"
    __table_args__ = (
        UniqueConstraint("stable_id", "position", name="uq_component_media_position"),
        CheckConstraint("position >= 0 and position < 5", name="ck_component_media_position"),
        CheckConstraint("kind in ('image', 'video', 'youtube')", name="ck_component_media_kind"),
        CheckConstraint(
            "source_type in ('upload', 'github', 'youtube')",
            name="ck_component_media_source_type",
        ),
        CheckConstraint(
            "size_bytes is null or size_bytes <= 26214400", name="ck_component_media_size"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    public_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    github_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(11), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt: Mapped[str] = mapped_column(String(240))
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CatalogReaction(Base):
    """One idempotent authenticated like per account and catalog object."""

    __tablename__ = "catalog_reaction"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "object_kind", "stable_id", name="uq_catalog_reaction_account_object"
        ),
        CheckConstraint("object_kind in ('component', 'setup')", name="ck_catalog_reaction_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    object_kind: Mapped[str] = mapped_column(String(16))
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ObjectLocation(Base):
    """Pointer from one catalog version to immutable content-addressed bytes.

    The object store still refuses different bytes under the same key. This
    row is not that lock: several versions may share one key when their
    artifact digest is identical.
    """

    __tablename__ = "object_location"
    __table_args__ = (
        UniqueConstraint(
            "catalog_metadata_id",
            "purpose",
            name="uq_object_location_metadata_purpose",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_object_location_size_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_metadata_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_metadata.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(512))
    digest: Mapped[str] = mapped_column(String(71))
    content_id: Mapped[str] = mapped_column(String(71))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    catalog_metadata: Mapped[CatalogMetadata] = relationship()


class AuditEvent(Base):
    """Append-only audit row for sensitive server actions."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(128))
    target_table: Mapped[str] = mapped_column(String(128))
    target_id: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped[Account | None] = relationship()


class SyncRevision(Base):
    """Immutable account-scoped accepted revision (SPEC-025, ADR-0045)."""

    __tablename__ = "sync_revision"
    __table_args__ = (
        CheckConstraint(
            "entity_kind in ("
            "'developer_passport', 'device_summary', 'component_private', "
            "'setup_private', 'unverified_consent')",
            name="ck_sync_revision_entity_kind",
        ),
        CheckConstraint(
            "operation in ('upsert', 'tombstone')",
            name="ck_sync_revision_operation",
        ),
        CheckConstraint("schema_version = 1", name="ck_sync_revision_schema_version"),
    )

    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    revision_id: Mapped[str] = mapped_column(String(73), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    entity_kind: Mapped[str] = mapped_column(String(32))
    parent_revision_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    operation: Mapped[str] = mapped_column(String(16))
    content_digest: Mapped[str] = mapped_column(String(71))
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    device_id: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SyncEntityHead(Base):
    """One server head per (account, entity)."""

    __tablename__ = "sync_entity_head"

    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String(73))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SyncEventReceipt(Base):
    """Durable idempotent outcome of one push event."""

    __tablename__ = "sync_event_receipt"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_sync_event_receipt_account_idempotency",
        ),
        CheckConstraint(
            "state in ('accepted', 'rejected', 'conflict', 'superseded')",
            name="ck_sync_event_receipt_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str] = mapped_column(String(128))
    device_id: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    revision_id: Mapped[str | None] = mapped_column(String(73), nullable=True)
    server_head_revision_id: Mapped[str | None] = mapped_column(String(73), nullable=True)
    response_body: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncOutbox(Base):
    """Ordered durable stream of accepted events for account pull."""

    __tablename__ = "sync_outbox"
    __table_args__ = (
        UniqueConstraint("account_id", "sequence", name="uq_sync_outbox_account_sequence"),
        UniqueConstraint("account_id", "event_id", name="uq_sync_outbox_account_event"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger)
    event_id: Mapped[str] = mapped_column(String(128))
    entity_id: Mapped[str] = mapped_column(String(128))
    entity_kind: Mapped[str] = mapped_column(String(32))
    revision_id: Mapped[str] = mapped_column(String(73))
    parent_revision_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    device_id: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(16))
    content_digest: Mapped[str] = mapped_column(String(71))
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PublicationPlan(Base):
    """Immutable publication plan / operation (SPEC-026)."""

    __tablename__ = "publication_plan"
    __table_args__ = (
        UniqueConstraint(
            "actor_account_id",
            "idempotency_key",
            name="uq_publication_plan_actor_idempotency",
        ),
        CheckConstraint(
            "state in ("
            "'draft', 'ready', 'validating', 'publish_planned', "
            "'published', 'failed', 'cancelled', 'stale')",
            name="ck_publication_plan_state",
        ),
        CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_publication_plan_object_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str] = mapped_column(String(64))
    object_kind: Mapped[str] = mapped_column(String(32))
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    content_digest: Mapped[str] = mapped_column(String(71))
    policy_version: Mapped[str] = mapped_column(String(32), default="1")
    plan_hash: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32), default="ready")
    passport: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    attestations: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    effects: Mapped[list[str]] = mapped_column(JSON, default=list)
    component_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    confirm_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_ownership_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ValidationSnapshot(Base):
    """Durable validation results for one plan/digest (SPEC-026)."""

    __tablename__ = "validation_snapshot"
    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_validation_snapshot_plan"),
        CheckConstraint(
            "state in ('running', 'passed', 'warning', 'failed', 'degraded')",
            name="ck_validation_snapshot_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publication_plan.id", ondelete="CASCADE"), index=True
    )
    content_digest: Mapped[str] = mapped_column(String(71))
    policy_version: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), default="running")
    component_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceBinding(Base):
    """One check evidence binding on a validation snapshot."""

    __tablename__ = "evidence_binding"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "check_id",
            name="uq_evidence_binding_snapshot_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("validation_snapshot.id", ondelete="CASCADE"), index=True
    )
    check_id: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(64))
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity_max: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Why this check did not pass, in rule identifiers and counts. Never the
    #: scanned content: this reaches a client, and a message quoting what was
    #: found would put the artefact's bytes somewhere the artefact is not.
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    finding_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SafetyScanRun(Base):
    """Idempotent safety result for exact bytes, policy, profile and object kind."""

    __tablename__ = "safety_scan_run"
    __table_args__ = (
        UniqueConstraint(
            "content_digest",
            "policy_version",
            "profile",
            "object_kind",
            name="uq_safety_scan_run_identity",
        ),
        CheckConstraint(
            "state in ('running', 'complete', 'failed')",
            name="ck_safety_scan_run_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_digest: Mapped[str] = mapped_column(String(71), index=True)
    policy_version: Mapped[str] = mapped_column(String(32))
    profile: Mapped[str] = mapped_column(String(32))
    object_kind: Mapped[str] = mapped_column(String(32), default="component")
    state: Mapped[str] = mapped_column(String(32), default="complete")
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    wall_ms: Mapped[int] = mapped_column(Integer, default=0)
    engine_status: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SafetyFinding(Base):
    """Redacted finding attached to a safety scan run (#270 audit)."""

    __tablename__ = "safety_finding"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("safety_scan_run.id", ondelete="CASCADE"), index=True
    )
    check_id: Mapped[str] = mapped_column(String(64))
    family: Mapped[str] = mapped_column(String(64))
    rule_id: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(240))
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    tool_name: Mapped[str] = mapped_column(String(64), default="")
    fingerprint: Mapped[str] = mapped_column(String(32), default="")


class AccessGrant(Base):
    """Major-line access grant (SPEC-002, ADR-0030)."""

    __tablename__ = "access_grant"
    __table_args__ = (
        UniqueConstraint(
            "object_kind",
            "stable_id",
            "major",
            "grantee_account_id",
            name="uq_access_grant_target_grantee",
        ),
        CheckConstraint("state in ('active', 'revoked')", name="ck_access_grant_state"),
        CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_access_grant_object_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_kind: Mapped[str] = mapped_column(String(32))
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    major: Mapped[int] = mapped_column(Integer)
    owner_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    grantee_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GrantInvitation(Base):
    """Email invitation that becomes a grant after verified accept."""

    __tablename__ = "grant_invitation"
    __table_args__ = (
        UniqueConstraint(
            "owner_account_id",
            "idempotency_key",
            name="uq_grant_invitation_owner_idempotency",
        ),
        CheckConstraint(
            "state in ('pending', 'accepted', 'expired', 'revoked')",
            name="ck_grant_invitation_state",
        ),
        CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_grant_invitation_object_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    object_kind: Mapped[str] = mapped_column(String(32))
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    major: Mapped[int] = mapped_column(Integer)
    recipient_email_normalized: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_grant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportCase(Base):
    """Private request case routed by topic (SPEC-016)."""

    __tablename__ = "report_case"
    __table_args__ = (
        UniqueConstraint(
            "reporter_account_id",
            "idempotency_key",
            name="uq_report_case_reporter_idempotency",
        ),
        CheckConstraint(
            "state in ("
            "'submitted', 'triaged', 'awaiting_author', "
            "'security_escalated', 'resolved', 'dismissed')",
            name="ck_report_case_state",
        ),
        CheckConstraint(
            "topic in ("
            "'object_report', 'service_request', 'country_request', "
            "'component_complaint', 'author_complaint', 'ownership_transfer', "
            "'verification_request', 'other')",
            name="ck_report_case_topic",
        ),
        CheckConstraint(
            "(topic = 'object_report' and object_kind in ('component', 'setup') "
            "and stable_id is not null and version is not null and content_digest is not null) "
            "or (topic in ('component_complaint', 'ownership_transfer') "
            "and stable_id is not null) "
            "or (topic in ("
            "'service_request', 'country_request', 'author_complaint', "
            "'verification_request', 'other'))",
            name="ck_report_case_object_kind",
        ),
        CheckConstraint("locale in ('ru', 'en')", name="ck_report_case_locale"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reporter_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(String(32), default="object_report")
    object_kind: Mapped[str | None] = mapped_column(String(32))
    stable_id: Mapped[str | None] = mapped_column(String(64), index=True)
    version: Mapped[str | None] = mapped_column(String(32))
    content_digest: Mapped[str | None] = mapped_column(String(71))
    state: Mapped[str] = mapped_column(String(32), default="submitted")
    vulnerability: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    locale: Mapped[str] = mapped_column(String(8), default="en", server_default="en")
    group_key: Mapped[str] = mapped_column(String(200), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AccountAuthorVerification(Base):
    """Manual author_verified flag for an account (SPEC-007 REQ-715)."""

    __tablename__ = "account_author_verification"

    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_by_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ComplaintIntake(Base):
    """Public complaint about an author, catalog object, or other target."""

    __tablename__ = "complaint_intake"
    __table_args__ = (
        CheckConstraint(
            "target_kind in ('author', 'component', 'setup', 'other')",
            name="ck_complaint_intake_target_kind",
        ),
        Index("ix_complaint_intake_submitter_created", "submitter_key", "created_at"),
        Index("ix_complaint_intake_target_created", "target_kind", "target", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    submitter_account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    submitter_key: Mapped[str] = mapped_column(String(330), index=True)
    target_kind: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(256))
    sender_name: Mapped[str] = mapped_column(String(120))
    reply_email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublicProfile(Base):
    """One authored public profile per account (SPEC-028)."""

    __tablename__ = "public_profile"

    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    published_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProfileRevision(Base):
    """Immutable profile snapshot (draft or published)."""

    __tablename__ = "profile_revision"
    __table_args__ = (
        CheckConstraint(
            "lifecycle in ('draft', 'published', 'superseded')",
            name="ck_profile_revision_lifecycle",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    lifecycle: Mapped[str] = mapped_column(String(32), default="draft")
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(1500), nullable=True)
    links: Mapped[list[object]] = mapped_column(JSON, default=list)
    avatar_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_digest: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AvatarAsset(Base):
    """Processed avatar asset; originals stay private."""

    __tablename__ = "avatar_asset"
    __table_args__ = (
        CheckConstraint(
            "state in ('processing', 'ready', 'rejected', 'deleted')",
            name="ck_avatar_asset_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(32), default="processing")
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    public_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_digest: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="upload")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PublicDocument(Base):
    """Stable public document slug (SPEC-031)."""

    __tablename__ = "public_document"
    __table_args__ = (
        CheckConstraint(
            "kind in ('technical', 'privacy', 'cookies', 'service_rules', "
            "'author_content_and_license', 'personal_data_consent')",
            name="ck_public_document_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentRevision(Base):
    """Immutable localized document revision."""

    __tablename__ = "document_revision"
    __table_args__ = (
        CheckConstraint(
            "lifecycle in ('draft', 'published', 'superseded')",
            name="ck_document_revision_lifecycle",
        ),
        UniqueConstraint(
            "document_id", "locale", "content_digest", name="uq_document_revision_digest"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("public_document.id", ondelete="CASCADE"), index=True
    )
    locale: Mapped[str] = mapped_column(String(16))
    lifecycle: Mapped[str] = mapped_column(String(32), default="draft")
    title: Mapped[str] = mapped_column(String(240))
    policy_version: Mapped[str] = mapped_column(String(32), default="1.0")
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    markdown_source: Mapped[str] = mapped_column(Text)
    content_digest: Mapped[str] = mapped_column(String(80))
    renderer_version: Mapped[str] = mapped_column(String(32), default="commonmark_v1")
    source_type: Mapped[str] = mapped_column(String(32), default="repository")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountPolicyAcceptance(Base):
    """One immutable acceptance of an exact published legal revision."""

    __tablename__ = "account_policy_acceptance"
    __table_args__ = (
        CheckConstraint(
            "acceptance_type in ('service_rules', 'personal_data_consent')",
            name="ck_account_policy_acceptance_type",
        ),
        UniqueConstraint(
            "account_id",
            "document_revision_id",
            "acceptance_type",
            name="uq_account_policy_acceptance_exact",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    document_revision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("document_revision.id", ondelete="RESTRICT"), index=True
    )
    acceptance_type: Mapped[str] = mapped_column(String(32))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    locale: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32), default="web_onboarding")


class CatalogExternalObservation(Base):
    """One exact catalog metadata-adapter reference for a published revision.

    Deduplicated only by provider and external identifier. Last valid allowlist
    fields are retained on a later unavailable check. Adapters stay disabled
    until attribution and terms policy is verified.
    """

    __tablename__ = "catalog_external_observation"
    __table_args__ = (
        UniqueConstraint(
            "catalog_metadata_id",
            "provider",
            "external_identifier",
            name="uq_catalog_external_observation_identity",
        ),
        CheckConstraint(
            "provider in ('skills_sh', 'nori', 'modelcontextprotocol')",
            name="ck_catalog_external_observation_provider",
        ),
        CheckConstraint(
            "freshness in ('fresh', 'stale', 'unavailable')",
            name="ck_catalog_external_observation_freshness",
        ),
        CheckConstraint(
            "external_state in ('present', 'archived', 'unavailable')",
            name="ck_catalog_external_observation_external_state",
        ),
        CheckConstraint(
            "popularity_count is null or popularity_count >= 0",
            name="ck_catalog_external_observation_popularity",
        ),
        Index("ix_catalog_external_observation_metadata", "catalog_metadata_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_metadata_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_metadata.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(32))
    external_identifier: Mapped[str] = mapped_column(String(512))
    dedup_key: Mapped[str] = mapped_column(String(1024))
    source_url: Mapped[str] = mapped_column(String(2048))
    attribution: Mapped[str] = mapped_column(String(256))
    terms_url: Mapped[str] = mapped_column(String(2048))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    popularity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_state: Mapped[str] = mapped_column(String(16))


class CatalogUsageAggregate(Base):
    """One public usage aggregate per catalog object (SPEC-051)."""

    __tablename__ = "catalog_usage_aggregate"
    __table_args__ = (
        CheckConstraint(
            "detail_views_count >= 0 and artifact_downloads_count >= 0",
            name="ck_catalog_usage_aggregate_counts",
        ),
    )

    stable_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    detail_views_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    artifact_downloads_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogUsageDedup(Base):
    """Short-lived keyed anti-abuse row. No raw network or account identifiers."""

    __tablename__ = "catalog_usage_dedup"
    __table_args__ = (
        CheckConstraint(
            "dedup_key ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_usage_dedup_key",
        ),
        Index("ix_catalog_usage_dedup_expires_at", "expires_at"),
    )

    dedup_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OfficialUpstreamSource(Base):
    """Operator-managed Git or package component source (SPEC-056 REQ-5608)."""

    __tablename__ = "official_upstream_source"
    __table_args__ = (
        CheckConstraint(
            "component_type in ("
            "'instruction', 'skill', 'mcp', 'hook', 'command', 'agent', 'plugin', 'setting')",
            name="ck_official_upstream_source_component_type",
        ),
        CheckConstraint(
            "projection_kind in ('marketplace', 'plugin', 'native_files', 'package')",
            name="ck_official_upstream_source_projection_kind",
        ),
        CheckConstraint("kind in ('git', 'package')", name="ck_official_upstream_source_kind"),
        CheckConstraint(
            "("
            "kind = 'git' AND repository_url IS NOT NULL AND tracked_ref IS NOT NULL "
            "AND component_subpath IS NOT NULL"
            ") OR ("
            "kind = 'package' AND ecosystem IS NOT NULL AND package_name IS NOT NULL "
            "AND package_version IS NOT NULL"
            ")",
            name="ck_official_upstream_source_kind_fields",
        ),
        CheckConstraint(
            "inventory_state in ('enabled', 'paused', 'transferred', 'removed')",
            name="ck_official_upstream_source_inventory_state",
        ),
        CheckConstraint(
            "update_policy in ('daily', 'pinned', 'disabled')",
            name="ck_official_upstream_source_update_policy",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slot: Mapped[str] = mapped_column(String(16), default="official", server_default="official")
    kind: Mapped[str] = mapped_column(String(16), default="git", server_default="git")
    repository_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tracked_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    component_subpath: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ecosystem: Mapped[str | None] = mapped_column(String(32), nullable=True)
    package_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    package_version: Mapped[str | None] = mapped_column(String(256), nullable=True)
    package_filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    package_platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_type: Mapped[str] = mapped_column(String(32))
    projection_kind: Mapped[str] = mapped_column(
        String(32), default="native_files", server_default="native_files"
    )
    harness_id: Mapped[str] = mapped_column(String(32))
    target_scope: Mapped[str | None] = mapped_column(String(16), nullable=True)
    projection_root: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    projection_shape: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), index=True
    )
    actor_device_id: Mapped[str] = mapped_column(String(64))
    stable_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    upstream_project_name: Mapped[str] = mapped_column(String(200))
    upstream_maintainer: Mapped[str] = mapped_column(String(200))
    reviewed_description: Mapped[str] = mapped_column(Text)
    reviewed_license: Mapped[str] = mapped_column(String(64))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    inventory_state: Mapped[str] = mapped_column(
        String(16), default="enabled", server_default="enabled"
    )
    update_policy: Mapped[str] = mapped_column(String(16), default="daily", server_default="daily")
    canonical_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name_en: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name_ru: Mapped[str | None] = mapped_column(String(80), nullable=True)
    manifest_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    ownership_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_github_repo_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_commit: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_canonical_coordinate: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_archive_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    last_component_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OfficialUpstreamSync(Base):
    """One Official sync attempt from desired update through a terminal result."""

    __tablename__ = "official_upstream_sync"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "trigger_key", name="uq_official_upstream_sync_source_trigger"
        ),
        CheckConstraint(
            "result in ('unchanged', 'publication_started', 'failed')",
            name="ck_official_upstream_sync_result",
        ),
        CheckConstraint(
            "state in ("
            "'desired', 'queued', 'resolving', 'unchanged', 'publishing', 'published', "
            "'retry_wait', 'dead_lettered', 'failed_permanent', 'cancelled_transferred')",
            name="ck_official_upstream_sync_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    utc_day: Mapped[date] = mapped_column(Date)
    trigger_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), default="desired", server_default="desired")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outbox_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_owner_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_ownership_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    provenance: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(256), nullable=True)
    archive_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    component_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    observed_license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    github_owner: Mapped[str | None] = mapped_column(String(256), nullable=True)
    github_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    github_repo_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OfficialSyncOutbox(Base):
    """Transactional Official sync intent independent of the generic job row."""

    __tablename__ = "official_sync_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_official_sync_outbox_idempotency"),
        CheckConstraint(
            "state in ('pending', 'dispatched', 'cancelled')",
            name="ck_official_sync_outbox_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    attempt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("official_upstream_sync.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OwnershipClaim(Base):
    """Request to receive an official catalog component."""

    __tablename__ = "ownership_claim"
    __table_args__ = (
        CheckConstraint(
            "state in ('requested', 'approved', 'denied')",
            name="ck_ownership_claim_state",
        ),
        CheckConstraint("object_kind = 'component'", name="ck_ownership_claim_object_kind"),
        UniqueConstraint("idempotency_key", name="uq_ownership_claim_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_kind: Mapped[str] = mapped_column(String(32), default="component")
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    requester_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), index=True
    )
    from_account_id: Mapped[str] = mapped_column(String(64), index=True)
    to_account_id: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), default="requested")
    preview: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    staff_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class OwnershipRevision(Base):
    """Append-only ownership revision. Published version passports stay as written."""

    __tablename__ = "ownership_revision"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("ownership_claim.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    from_account_id: Mapped[str] = mapped_column(String(64))
    to_account_id: Mapped[str] = mapped_column(String(64))
    major_lines: Mapped[list[int]] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    staff_account_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
