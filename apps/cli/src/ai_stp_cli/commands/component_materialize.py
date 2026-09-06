"""Materialize one target-harness adaptation of a pinned component (SPEC-063)."""

from collections.abc import Mapping
from contextlib import closing

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import component_materialize, passports
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import ComponentMaterializePlan, ComponentMaterializeResult
from ai_stp_foundation.ids import new_id


def plan(parameters: Mapping[str, object]) -> Answer[ComponentMaterializePlan]:
    """Resolve one adaptation and return the exact immutable plan."""
    stable_id = str(parameters.get("id") or "")
    if not stable_id:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the component id is required")
    target = str(parameters.get("to-harness") or "")
    if not target:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "the target harness is required")
    version = str(parameters.get("version") or "") or None
    source = str(parameters.get("from-harness") or "")
    local_only = parameters.get("local-only") is True
    overlay_id = str(parameters.get("overlay-id") or "")
    if local_only and not overlay_id:
        overlay_id = new_id("component")
    created_at = passports.moment()
    with closing(open_registry(configured_path(), create=False)) as connection:
        return Answer(
            component_materialize.plan(
                connection,
                stable_id=stable_id,
                version=version,
                source_harness=source,
                target_harness=target,
                overlay_id=overlay_id,
                created_at=created_at,
                local_only=local_only,
            )
        )


def apply(parameters: Mapping[str, object]) -> Answer[ComponentMaterializeResult]:
    """Record the exact still-current adaptation."""
    stable_id = str(parameters.get("id") or "")
    target = str(parameters.get("to-harness") or "")
    overlay_id = str(parameters.get("overlay-id") or "")
    created_at = str(parameters.get("created-at") or "")
    expected = str(parameters.get("expected-plan-digest") or "")
    if not stable_id or not target or not overlay_id or not created_at or not expected:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "the exact materialize plan identity is required"
        )
    version = str(parameters.get("version") or "") or None
    source = str(parameters.get("from-harness") or "")
    local_only = parameters.get("local-only") is True
    current, _warning = identity.load_or_create()
    with closing(open_registry(configured_path(), create=False)) as connection:
        return Answer(
            component_materialize.apply(
                connection,
                stable_id=stable_id,
                version=version,
                source_harness=source,
                target_harness=target,
                overlay_id=overlay_id,
                created_at=created_at,
                local_only=local_only,
                expected_plan_digest=expected,
                device_id=current.device_id,
                owner_id=passports.owner().account_id,
            )
        )


def portability_plan(parameters: Mapping[str, object]) -> Answer[ComponentMaterializePlan]:
    """Preview a private overlay. The command itself is the portability claim."""
    return plan({**dict(parameters), "local-only": True})


def portability_apply(parameters: Mapping[str, object]) -> Answer[ComponentMaterializeResult]:
    """Record the private overlay from an explicit still-current claim."""
    return apply({**dict(parameters), "local-only": True})
