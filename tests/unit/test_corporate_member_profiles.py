"""Corporate names are tenant-local and profile requests cannot change authority."""

import pytest
from pydantic import ValidationError

from ai_stp_api.slices.corporate.service import member_view
from ai_stp_contracts.corporate import CorporateMemberProfileRequest
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import OrganizationMembership


def test_tenant_member_names_do_not_mutate_shared_account() -> None:
    account = Account(id=new_id("account"), display_name="Public name", status="active")
    first = OrganizationMembership(
        organization_id=new_id("organization"),
        account_id=account.id,
        display_name="Mobile lead",
        role="staff",
        state="active",
        revision=2,
    )
    second = OrganizationMembership(
        organization_id=new_id("organization"),
        account_id=account.id,
        display_name="Other organization name",
        role="staff",
        state="active",
        revision=1,
    )
    assert member_view(first, account).display_name == "Mobile lead"
    assert member_view(second, account).display_name == "Other organization name"
    assert account.display_name == "Public name"
    second.display_name = None
    assert member_view(second, account).display_name == "Public name"


def test_profile_boundary_rejects_blank_names_and_authority_fields() -> None:
    payload = {
        "display_name": "Alice",
        "expected_revision": 1,
        "authorization_revision": 1,
        "idempotency_key": "profile-test-key",
    }
    assert CorporateMemberProfileRequest.model_validate(payload).display_name == "Alice"
    for invalid in [
        {**payload, "display_name": "  "},
        {**payload, "role": "superadmin"},
        {**payload, "state": "suspended"},
        {**payload, "expected_revision": 0},
    ]:
        with pytest.raises(ValidationError):
            CorporateMemberProfileRequest.model_validate(invalid)
