"""One retained operational owner per tenant and stable catalog object."""

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class CorporateCatalogOwnership(Base):
    __tablename__ = "corporate_catalog_ownership"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "owner_account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("object_kind IN ('setup','component')", name="ck_catalog_ownership_kind"),
        CheckConstraint("revision >= 1", name="ck_catalog_ownership_revision"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), primary_key=True
    )
    object_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    stable_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
