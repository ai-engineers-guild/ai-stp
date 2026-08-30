"""ORM mappings for hybrid article publication (SPEC-054)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class Article(Base):
    """Stable content-hub identity with an immutable source owner."""

    __tablename__ = "article"
    __table_args__ = (
        UniqueConstraint("article_type", "slug", name="uq_article_type_slug"),
        CheckConstraint(
            "article_type in ('article', 'blog_post', 'changelog', 'release_notes')",
            name="ck_article_type",
        ),
        CheckConstraint(
            "source_kind in ('repository', 'staff')",
            name="ck_article_source_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    article_type: Mapped[str] = mapped_column(String(32))
    slug: Mapped[str] = mapped_column(String(120))
    source_kind: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArticleRevision(Base):
    """Immutable localized article contents."""

    __tablename__ = "article_revision"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "locale",
            "content_digest",
            name="uq_article_revision_identity",
        ),
        CheckConstraint("locale in ('ru', 'en')", name="ck_article_revision_locale"),
        CheckConstraint(
            "source_kind in ('repository', 'staff')",
            name="ck_article_revision_source_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(73), primary_key=True)
    article_id: Mapped[str] = mapped_column(
        String(160), ForeignKey("article.id", ondelete="RESTRICT"), index=True
    )
    locale: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(320))
    published_at: Mapped[str] = mapped_column(String(10))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    body: Mapped[str] = mapped_column(Text)
    content_digest: Mapped[str] = mapped_column(String(71))
    source_kind: Mapped[str] = mapped_column(String(16))
    source_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    actor_account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleActive(Base):
    """Currently served localized revision; history stays in article_revision."""

    __tablename__ = "article_active"
    __table_args__ = (
        UniqueConstraint("article_id", "locale", name="uq_article_active_identity"),
        CheckConstraint("locale in ('ru', 'en')", name="ck_article_active_locale"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[str] = mapped_column(
        String(160), ForeignKey("article.id", ondelete="RESTRICT"), index=True
    )
    locale: Mapped[str] = mapped_column(String(8))
    revision_id: Mapped[str] = mapped_column(
        String(73), ForeignKey("article_revision.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleRepositoryState(Base):
    """Singleton repository import generation."""

    __tablename__ = "article_repository_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_article_repository_state_singleton"),
        CheckConstraint("generation >= 0", name="ck_article_repository_state_generation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    generation: Mapped[int] = mapped_column(BigInteger, default=0)
    snapshot_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
