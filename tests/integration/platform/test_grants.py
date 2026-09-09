"""Access grant lifecycle behaviour."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.grants.service import create_direct_grant
from ai_stp_contracts.grants import DirectGrantCreateRequest
from ai_stp_platform.grant_identity_models import GrantRecipientReference
from ai_stp_platform.models import AccessGrant, Account, CatalogMetadata

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_direct_grant_reactivates_a_previously_revoked_grant(
    db_session: AsyncSession,
) -> None:
    owner_id = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    grantee_id = "account_01ARZ3NDEKTSV4RRFFQ69G5FAW"
    stable_id = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    grant_id = "grant_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    revoked_at = datetime.now(UTC)

    db_session.add_all([Account(id=owner_id), Account(id=grantee_id)])
    await db_session.flush()
    db_session.add_all(
        [
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="component",
                stable_id=stable_id,
                version="1.3",
                current_revision_id="revision_" + "a" * 64,
                visibility="private",
                lifecycle_state="published",
            ),
            AccessGrant(
                id=grant_id,
                object_kind="component",
                stable_id=stable_id,
                major=1,
                owner_account_id=owner_id,
                grantee_account_id=grantee_id,
                state="revoked",
                revoked_at=revoked_at,
            ),
        ]
    )
    await db_session.flush()
    db_session.add(
        GrantRecipientReference(
            grant_id=grant_id,
            identifier_kind="user_id",
            identifier_value=grantee_id,
        )
    )
    await db_session.flush()

    result = await create_direct_grant(
        db_session,
        ctx=AuthContext(owner_id, "session_test", None, "active", False, True),
        body=DirectGrantCreateRequest(
            object_kind="component",
            stable_id=stable_id,
            major=1,
            recipient_kind="user_id",
            recipient=grantee_id,
            idempotency_key="regrant-test-20260909",
        ),
    )

    assert result.grant_id == grant_id
    assert result.state == "active"
    assert result.revoked_at is None
