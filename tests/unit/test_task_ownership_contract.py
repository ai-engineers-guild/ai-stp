"""A task's retained local identity is not a selected company or session."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.cli.tasks import NativePersonalTaskOwnership, TaskView

ACCOUNT = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
DEVICE = "device_01ARZ3NDEKTSV4RRFFQ69G5FAW"


def test_task_without_reported_ownership_stays_unclassified() -> None:
    task = TaskView(
        task_id="task_01ARZ3NDEKTSV4RRFFQ69G5FAX",
        revision=1,
        intent="author",
        state="blocked",
        goal_satisfied=False,
        questions=[],
        outcome=None,
        child_operation_ids=[],
    )
    assert task.ownership is None


def test_personal_task_ownership_retains_exact_native_ids() -> None:
    value = {"kind": "personal", "native_account_id": ACCOUNT, "native_device_id": DEVICE}
    assert NativePersonalTaskOwnership.model_validate(value).model_dump() == value


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "corporate"},
        {"kind": None},
        {"native_device_id": ACCOUNT},
        {"native_account_id": DEVICE},
        {"organization_id": "organization_01ARZ3NDEKTSV4RRFFQ69G5FAX"},
    ],
)
def test_task_ownership_refuses_invented_company_or_malformed_ids(
    change: dict[str, object],
) -> None:
    value = {"kind": "personal", "native_account_id": ACCOUNT, "native_device_id": DEVICE}
    with pytest.raises(ValidationError):
        NativePersonalTaskOwnership.model_validate({**value, **change})


def test_task_ownership_never_defaults_missing_kind_to_personal() -> None:
    with pytest.raises(ValidationError):
        NativePersonalTaskOwnership.model_validate(
            {"native_account_id": ACCOUNT, "native_device_id": DEVICE}
        )
