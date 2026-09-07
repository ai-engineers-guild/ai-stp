"""Preserve, inspect and return to complete user-owned native setups."""

from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Literal, cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import install
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, preserved_setups
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_cli.paths import redact_home
from ai_stp_cli.provider.status import BackupObservation
from ai_stp_contracts.machine_help import InstallationView, PreservedSetupsView, PreservedSetupView


def _provider_options(parameters: Mapping[str, object]) -> dict[str, object]:
    """Forward only the provider selection and trust inputs accepted by this surface."""
    return {
        name: parameters[name]
        for name in (
            "provider",
            "provider-manifest",
            "provider-build-attestation",
            "provider-attestation-bundle",
            "unverified-provider",
            "provider-release-recovery",
        )
        if name in parameters
    }


def _view(
    saved: preserved_setups.PreservedSetup,
    observed: BackupObservation | None = None,
    *,
    measured: bool = False,
) -> PreservedSetupView:
    project_id, harness_id = installation.target_pair(saved.target_id)
    native = None if observed is None else observed.native_snapshot
    valid = (
        native is not None
        and native.digest == saved.snapshot_digest
        and native.verification == "verified"
        and observed is not None
        and observed.held is True
    )
    return PreservedSetupView(
        stable_id=saved.stable_id,
        operation_id=saved.operation_id,
        project_id=project_id,
        harness_id=harness_id,
        target_scope=saved.target_scope,
        provider_target=redact_home(Path(saved.provider_target)),
        provider_id=saved.provider_id,
        backup_ref=saved.backup_ref,
        snapshot_digest=saved.snapshot_digest,
        roots=list(saved.roots),
        base_root=cast(Literal["target", "parent"], saved.base_root),
        created_at=saved.created_at,
        verification="recorded_verified"
        if not measured
        else "verified"
        if valid
        else "unavailable",
        target_state=(native.target_state if valid and native is not None else "unavailable")
        if measured
        else "not_observed",
        held=None if observed is None else observed.held,
    )


def list_saved(parameters: Mapping[str, object]) -> Answer[PreservedSetupsView]:
    """List immutable capture identities without guessing current provider state."""
    path = configured_path()
    if not path.exists():
        return Answer(PreservedSetupsView())
    with closing(open_readonly(path)) as connection:
        return Answer(
            PreservedSetupsView(
                setups=[
                    _view(item)
                    for item in preserved_setups.all_saved(connection)
                    if not parameters.get("harness")
                    or installation.target_pair(item.target_id)[1] == parameters["harness"]
                ]
            )
        )


def show(parameters: Mapping[str, object]) -> Answer[PreservedSetupView]:
    """Inspect a saved setup, optionally verifying its recovery bytes through its provider."""
    with closing(open_readonly(configured_path())) as connection:
        saved = preserved_setups.held(connection, str(parameters.get("setup") or ""))
        if saved is None:
            raise CliFailure("AI_STP_NOT_FOUND", "the preserved setup is not held by this registry")
        project_id, harness_id = installation.target_pair(saved.target_id)
        observed = install.observe_backups(
            connection,
            {
                **_provider_options(parameters),
                "target": saved.provider_target,
                "scope": saved.target_scope,
            },
            project_id,
            harness_id,
            expected_provider_id=saved.provider_id,
        )
        return Answer(
            _view(
                saved,
                None if observed is None else observed.get(saved.backup_ref),
                measured=observed is not None,
            )
        )


def preserve_plan(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    """Plan complete capture through the ordinary provider operation machine."""
    return install.plan(
        {
            **_provider_options(parameters),
            "action": "backup",
            "protocol-version": 3,
            "project": parameters.get("project"),
            "harness": parameters.get("harness"),
            "target": parameters.get("target"),
            "scope": parameters.get("scope"),
        }
    )


def restore_plan(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    """Resolve a setup identity to its exact retained native restoration source."""
    with closing(open_readonly(configured_path())) as connection:
        saved = preserved_setups.held(connection, str(parameters.get("preserved-setup") or ""))
    if saved is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the preserved setup is not held by this registry")
    project_id, harness_id = installation.target_pair(saved.target_id)
    return install.plan(
        {
            **_provider_options(parameters),
            "preserved-setup": saved.stable_id,
            "action": "rollback",
            "protocol-version": 3,
            "project": project_id,
            "harness": harness_id,
            "target": saved.provider_target,
            "scope": saved.target_scope,
            "backup-ref": saved.backup_ref,
        }
    )
