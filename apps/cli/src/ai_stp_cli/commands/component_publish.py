"""`component publish --from-setup`: extract one embedded member into publication."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import publication
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import embedded_promotion
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.machine_help import ComponentPromotionPlan


def publish(parameters: Mapping[str, object]) -> Answer[ComponentPromotionPlan]:
    """Materialize one embedded component, then create the ordinary publication plan."""
    setup_id = str(parameters.get("from-setup") or "")
    version = str(parameters.get("setup-version") or "")
    component_id = str(parameters.get("component-id") or "")
    if not setup_id or not version or not component_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a setup identifier, version, and exact component id are required",
        )
    signer, _warning = identity.current()
    device_id = "" if signer is None else signer.device_id
    with closing(open_registry(configured_path(), create=True)) as connection:
        materialized = embedded_promotion.materialize(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=component_id,
            device_id=device_id or "device_local",
            at=moment(),
        )
        connection.commit()
    planned = publication.plan(
        {
            "id": materialized.catalog_stable_id,
            "version": materialized.catalog_version,
            "attestation-file": parameters.get("attestation-file") or (),
        }
    )
    view = planned.payload
    return Answer(
        ComponentPromotionPlan(
            setup_id=materialized.setup_id,
            setup_version=materialized.setup_version,
            source_component_id=materialized.source_component_id,
            catalog_stable_id=materialized.catalog_stable_id,
            catalog_version=materialized.catalog_version,
            reused_passport=materialized.reused_passport,
            still_embedded=materialized.still_embedded,
            plan_id=view.plan_id,
            plan_hash=view.plan_hash,
            state=view.state,
        )
    )
