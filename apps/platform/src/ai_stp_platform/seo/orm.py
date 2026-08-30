"""ORM mappings for SEO snapshots and revisions (SPEC-053)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class SeoFactSnapshot(Base):
    """Immutable allowlist projection of one public subject aggregate."""

    __tablename__ = "seo_fact_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "subject_kind",
            "subject_id",
            "locale",
            "source_digest",
            name="uq_seo_fact_snapshot_identity",
        ),
        CheckConstraint(
            "subject_kind in ('component', 'setup', 'article', 'service', 'country')",
            name="ck_seo_fact_snapshot_kind",
        ),
        CheckConstraint("locale in ('ru', 'en')", name="ck_seo_fact_snapshot_locale"),
        CheckConstraint("schema_version = 1", name="ck_seo_fact_snapshot_schema"),
    )

    id: Mapped[str] = mapped_column(String(71), primary_key=True)
    subject_kind: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[str] = mapped_column(String(253), index=True)
    source_revision: Mapped[str] = mapped_column(String(128))
    locale: Mapped[str] = mapped_column(String(8))
    source_digest: Mapped[str] = mapped_column(String(71))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    facts: Mapped[dict[str, object]] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SeoRevision(Base):
    """Immutable presentation document for one snapshot and generator."""

    __tablename__ = "seo_revision"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "generator_kind",
            "template_version",
            "prompt_version",
            "model_alias",
            name="uq_seo_revision_identity",
        ),
        CheckConstraint(
            "state in ("
            "'building', 'base_ready', 'enriching', 'validating', "
            "'active', 'rejected', 'failed', 'stale')",
            name="ck_seo_revision_state",
        ),
        CheckConstraint(
            "generator_kind in ('template', 'model')",
            name="ck_seo_revision_generator",
        ),
    )

    id: Mapped[str] = mapped_column(String(73), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(71), ForeignKey("seo_fact_snapshot.id", ondelete="RESTRICT"), index=True
    )
    state: Mapped[str] = mapped_column(String(16), default="building")
    profile: Mapped[dict[str, object]] = mapped_column(JSON)
    profile_digest: Mapped[str] = mapped_column(String(71))
    template_version: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    generator_kind: Mapped[str] = mapped_column(String(16))
    model_alias: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SeoActiveRevision(Base):
    """Exactly one serving pointer per subject and locale."""

    __tablename__ = "seo_active_revision"
    __table_args__ = (
        UniqueConstraint(
            "subject_kind",
            "subject_id",
            "locale",
            name="uq_seo_active_revision_subject_locale",
        ),
        CheckConstraint(
            "subject_kind in ('component', 'setup', 'article', 'service', 'country')",
            name="ck_seo_active_revision_kind",
        ),
        CheckConstraint("locale in ('ru', 'en')", name="ck_seo_active_revision_locale"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_kind: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[str] = mapped_column(String(253), index=True)
    locale: Mapped[str] = mapped_column(String(8))
    revision_id: Mapped[str] = mapped_column(
        String(73), ForeignKey("seo_revision.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(71), ForeignKey("seo_fact_snapshot.id", ondelete="RESTRICT")
    )
    generation: Mapped[int] = mapped_column(BigInteger)
    index_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SeoGeneration(Base):
    """Single-row generation counter for sitemap and LLM cache keys."""

    __tablename__ = "seo_generation"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
