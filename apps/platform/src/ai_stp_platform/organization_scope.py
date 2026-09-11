"""Shared organization scope column for remote account-owned records."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, event, inspect, select, text
from sqlalchemy.orm import Mapped, Session, declared_attr, mapped_column, relationship

from ai_stp_platform.organization_models import Organization

__all__ = ["OrganizationScopedMixin", "_populate_legacy_personal_scope"]


class OrganizationScopedMixin:
    """Additive scope during the account-to-organization compatibility window."""

    organization_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("organization.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    @declared_attr
    def organization(cls) -> Mapped[Organization | None]:
        return relationship(Organization)


def _populate_legacy_personal_scope(
    session: Session, _flush_context: object, _instances: object
) -> None:
    """Fill compatibility writes from their account attribution.

    New organization-aware paths set the scope explicitly. This fallback only
    serves old account-owned writers during the additive migration window.
    """
    new_instances = tuple(session.new)
    if not any(isinstance(instance, OrganizationScopedMixin) for instance in new_instances):
        return
    if not inspect(session.get_bind()).has_table("organization"):
        return

    _ensure_personal_organizations(session)
    from ai_stp_platform.organization_models import Organization

    pending_personal = {
        organization.owner_account_id: organization
        for organization in session.new
        if isinstance(organization, Organization)
        and organization.kind == "personal"
        and organization.owner_account_id is not None
    }
    for instance in tuple(session.new):
        if not isinstance(instance, OrganizationScopedMixin):
            continue
        if instance.organization_id is not None:
            continue
        account_id = next(
            (
                getattr(instance, field, None)
                for field in (
                    "owner_account_id",
                    "actor_account_id",
                    "account_id",
                    "reporter_account_id",
                )
                if getattr(instance, field, None) is not None
            ),
            None,
        )
        if account_id is None:
            catalog_metadata_id = getattr(instance, "catalog_metadata_id", None)
            if catalog_metadata_id is None:
                continue
            from ai_stp_platform.models import CatalogMetadata

            instance.organization_id = session.scalar(
                select(CatalogMetadata.organization_id).where(
                    CatalogMetadata.id == catalog_metadata_id
                )
            )
            continue
        if account_id in pending_personal:
            instance.organization = pending_personal[account_id]
            continue
        organization_ids = (
            session.execute(
                text(
                    "SELECT id FROM organization "
                    "WHERE owner_account_id = :account_id AND kind = 'personal'"
                ),
                {"account_id": account_id},
            )
            .scalars()
            .all()
        )
        if len(organization_ids) > 1:
            raise ValueError("personal organization attribution is ambiguous")
        if organization_ids:
            instance.organization_id = organization_ids[0]


def _ensure_personal_organizations(session: Session) -> None:
    """Create the account's personal organization with the account itself."""
    from ai_stp_foundation.ids import new_id
    from ai_stp_platform.models import Account
    from ai_stp_platform.organization_models import Organization, OrganizationMembership

    new_accounts = {
        account.id
        for account in session.new
        if getattr(account, "__tablename__", None) == "account"
    }
    scoped_accounts = {
        account_id
        for instance in session.new
        if isinstance(instance, OrganizationScopedMixin)
        for account_id in (
            next(
                (
                    getattr(instance, field, None)
                    for field in (
                        "owner_account_id",
                        "actor_account_id",
                        "account_id",
                        "reporter_account_id",
                    )
                    if getattr(instance, field, None) is not None
                ),
                None,
            ),
        )
        if account_id is not None
    }
    account_ids = new_accounts | scoped_accounts
    if not account_ids:
        return

    pending_personal = {
        organization.owner_account_id
        for organization in session.new
        if isinstance(organization, Organization)
        and organization.kind == "personal"
        and organization.owner_account_id is not None
    }
    for account_id in account_ids:
        if account_id in pending_personal:
            continue
        with session.no_autoflush:
            existing = session.scalar(
                select(Organization.id).where(
                    Organization.owner_account_id == account_id,
                    Organization.kind == "personal",
                )
            )
        if existing is not None:
            continue
        if (
            account_id not in new_accounts
            and session.scalar(select(Account.id).where(Account.id == account_id)) is None
        ):
            continue
        organization_id = new_id("organization")
        organization = Organization(
            id=organization_id,
            kind="personal",
            owner_account_id=account_id,
            display_name="Personal workspace",
            revision=1,
        )
        session.add(organization)
        session.add(
            OrganizationMembership(
                organization=organization,
                organization_id=organization_id,
                account_id=account_id,
                role="owner",
                state="active",
                revision=1,
            )
        )


event.listen(Session, "before_flush", _populate_legacy_personal_scope)
