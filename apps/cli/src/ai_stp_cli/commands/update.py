"""`ai-stp update` — replace this CLI distribution through its owning installer."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.self_update import service
from ai_stp_contracts.machine_help import (
    CliSelfUpdateCheck,
    CliSelfUpdatePlan,
    CliSelfUpdateResult,
    CliSelfUpdateStatus,
)


def check(parameters: Mapping[str, object]) -> Answer[CliSelfUpdateCheck]:
    """Report whether a newer compatible wheel is install-ready."""
    return Answer(service.check(parameters))


def plan(parameters: Mapping[str, object]) -> Answer[CliSelfUpdatePlan]:
    """Pin one exact wheel and the installer that must apply it."""
    return Answer(service.plan(parameters))


def apply(parameters: Mapping[str, object]) -> Answer[CliSelfUpdateResult]:
    """Reapply one stored plan digest through the owning installer."""
    return Answer(service.apply(parameters))


def status(_parameters: Mapping[str, object]) -> Answer[CliSelfUpdateStatus]:
    """Read the journal and the distribution a new process would import."""
    return Answer(service.status())


def recover(_parameters: Mapping[str, object]) -> Answer[CliSelfUpdateResult]:
    """Finish or restore an interrupted CLI update without a new digest."""
    return Answer(service.recover())


def rollback(parameters: Mapping[str, object]) -> Answer[CliSelfUpdateResult]:
    """Restore the previous verified distribution when its wheel is still held."""
    return Answer(service.rollback(parameters))
