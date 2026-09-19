"""`ai-stp install` — Click handlers. Effects live in `application.install`."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.application import install as install_service
from ai_stp_contracts.machine_help import (
    InstallationStatus,
    InstallationView,
    RecoveryView,
    RollbackTarget,
    TargetBackups,
    TargetDiff,
    TargetSurvey,
)

transaction_child_access = install_service.transaction_child_access
observe_backups = install_service.observe_backups


def __getattr__(name: str) -> object:
    return getattr(install_service, name)


def plan(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    return install_service.plan(parameters)


def approve(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    return install_service.approve(parameters)


def apply(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    return install_service.apply(parameters)


def cancel(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    return install_service.cancel(parameters)


def status(parameters: Mapping[str, object]) -> Answer[InstallationStatus]:
    return install_service.status(parameters)


def recover(parameters: Mapping[str, object]) -> Answer[RecoveryView]:
    return install_service.recover(parameters)


def resume(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    return install_service.resume(parameters)


def recover_preserved(
    parameters: Mapping[str, object],
    *,
    settle_provider: bool = False,
) -> Answer[InstallationView]:
    return install_service.recover_preserved(parameters, settle_provider=settle_provider)


def target_status(parameters: Mapping[str, object]) -> Answer[TargetSurvey]:
    return install_service.target_status(parameters)


def target_diff(parameters: Mapping[str, object]) -> Answer[TargetDiff]:
    return install_service.target_diff(parameters)


def target_rollback(parameters: Mapping[str, object]) -> Answer[RollbackTarget]:
    return install_service.target_rollback(parameters)


def target_backups(parameters: Mapping[str, object]) -> Answer[TargetBackups]:
    return install_service.target_backups(parameters)
