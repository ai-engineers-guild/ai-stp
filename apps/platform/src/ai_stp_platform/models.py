"""Sprint-1 platform storage models (SPEC-020).

These mappings own storage integrity only. Domain semantics stay with the
active specifications that define accounts, devices, passports and catalog
objects.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_stp_platform.db import Base


class Account(Base):
    """Internal platform account, separated from provider identities."""

    __tablename__ = "account"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    show_profile_publicly: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    allow_publisher_listing: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
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
    """Opaque content-addressed storage location for immutable object bytes."""

    __tablename__ = "object_location"
    __table_args__ = (
        UniqueConstraint(
            "catalog_metadata_id",
            "purpose",
            name="uq_object_location_metadata_purpose",
        ),
        UniqueConstraint("object_key", name="uq_object_location_object_key"),
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
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SafetyScanRun(Base):
    """Idempotent safety suite result for (content_digest, policy_version)."""

    __tablename__ = "safety_scan_run"
    __table_args__ = (
        UniqueConstraint(
            "content_digest",
            "policy_version",
            name="uq_safety_scan_run_digest_policy",
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
    """Closed report case for one exact version (SPEC-016)."""

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
            "object_kind in ('component', 'setup')",
            name="ck_report_case_object_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reporter_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), index=True
    )
    object_kind: Mapped[str] = mapped_column(String(32))
    stable_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    content_digest: Mapped[str] = mapped_column(String(71))
    state: Mapped[str] = mapped_column(String(32), default="submitted")
    vulnerability: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
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
            "'author_content_and_license')",
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
    markdown_source: Mapped[str] = mapped_column(Text)
    content_digest: Mapped[str] = mapped_column(String(80))
    renderer_version: Mapped[str] = mapped_column(String(32), default="commonmark_v1")
    source_type: Mapped[str] = mapped_column(String(32), default="repository")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
