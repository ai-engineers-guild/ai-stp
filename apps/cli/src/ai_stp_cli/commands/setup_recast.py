"""Recast one recorded setup onto another harness (SPEC-062)."""

from collections.abc import Mapping
from contextlib import closing

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, setup_recast
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import SetupRecastPlan, SetupRecastResult
from ai_stp_foundation.ids import new_id


def plan(parameters: Mapping[str, object]) -> Answer[SetupRecastPlan]:
    """Resolve one recast and return the exact immutable plan."""
    source_id = str(parameters.get("id") or "")
    if not source_id:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the source setup id is required")
    target = str(parameters.get("to-harness") or "")
    if not target:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the target harness is required")
    version = str(parameters.get("version") or "") or None
    setup_id = str(parameters.get("setup-id") or new_id("setup"))
    created_at = passports.moment()
    with closing(open_registry(configured_path(), create=False)) as connection:
        return Answer(
            setup_recast.plan(
                connection,
                source_id=source_id,
                source_version=version,
                target_harness=target,
                setup_id=setup_id,
                created_at=created_at,
            )
        )


def apply(parameters: Mapping[str, object]) -> Answer[SetupRecastResult]:
    """Record the exact still-current recast as one immutable local setup."""
    source_id = str(parameters.get("id") or "")
    target = str(parameters.get("to-harness") or "")
    setup_id = str(parameters.get("setup-id") or "")
    created_at = str(parameters.get("created-at") or "")
    expected = str(parameters.get("expected-plan-digest") or "")
    if not source_id or not target or not setup_id or not created_at or not expected:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the exact recast plan identity is required")
    version = str(parameters.get("version") or "") or None
    current, _warning = identity.load_or_create()
    with closing(open_registry(configured_path(), create=False)) as connection:
        return Answer(
            setup_recast.apply(
                connection,
                source_id=source_id,
                source_version=version,
                target_harness=target,
                setup_id=setup_id,
                created_at=created_at,
                expected_plan_digest=expected,
                device_id=current.device_id,
                owner_id=passports.owner().account_id,
            )
        )
