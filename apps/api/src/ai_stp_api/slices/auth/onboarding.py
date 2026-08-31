"""Legal onboarding: exact current revisions activate a pending account."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.slices.documents.service import current_published_revision
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AccountPolicyAcceptance


async def required_revisions(
    db: AsyncSession, *, account_id: str, locale: str
) -> dict[str, object]:
    account = await db.get(Account, account_id)
    if account is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
    terms = await current_published_revision(db, slug="service-rules", locale=locale)
    consent = await current_published_revision(db, slug="personal-data-consent", locale=locale)
    return {
        "schema_version": 1,
        "account_id": account.id,
        "account_status": account.status,
        "service_rules_revision_id": terms.id,
        "personal_data_consent_revision_id": consent.id,
    }


async def complete_onboarding(
    db: AsyncSession,
    *,
    account_id: str,
    locale: str,
    service_rules_revision_id: str,
    personal_data_consent_revision_id: str,
) -> dict[str, object]:
    """Accept both current documents, then atomically activate the account."""
    account = await db.get(Account, account_id)
    if account is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
    if account.status not in {"onboarding_pending", "active"}:
        raise ApiError(ErrorCategory.PERMISSION, "account is unavailable")

    current = await required_revisions(db, account_id=account_id, locale=locale)
    expected_terms = str(current["service_rules_revision_id"])
    expected_consent = str(current["personal_data_consent_revision_id"])
    if (
        service_rules_revision_id != expected_terms
        or personal_data_consent_revision_id != expected_consent
    ):
        raise ApiError(ErrorCategory.VALIDATION, "legal policy revision changed; review it again")

    existing = await db.execute(
        select(AccountPolicyAcceptance.acceptance_type).where(
            AccountPolicyAcceptance.account_id == account_id,
            AccountPolicyAcceptance.document_revision_id.in_(
                (service_rules_revision_id, personal_data_consent_revision_id)
            ),
        )
    )
    already = set(existing.scalars().all())
    records = (
        ("service_rules", service_rules_revision_id),
        ("personal_data_consent", personal_data_consent_revision_id),
    )
    for acceptance_type, revision_id in records:
        if acceptance_type not in already:
            db.add(
                AccountPolicyAcceptance(
                    id=new_id("acceptance"),
                    account_id=account_id,
                    document_revision_id=revision_id,
                    acceptance_type=acceptance_type,
                    locale=locale,
                )
            )
    if account.status != "active":
        account.status = "active"
        await db.flush()
        await emit_audit(
            db,
            actor_account_id=account_id,
            action="auth.legal_onboarding_completed",
            target_table="account",
            target_id=account_id,
            payload={
                "service_rules_revision_id": service_rules_revision_id,
                "personal_data_consent_revision_id": personal_data_consent_revision_id,
            },
        )
    await db.flush()
    return await required_revisions(db, account_id=account_id, locale=locale)
