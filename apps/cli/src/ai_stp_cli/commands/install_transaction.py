"""`ai-stp install transaction` — Click handlers. Effects: application.install_transaction."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.application import install
from ai_stp_cli.application import install_transaction as service
from ai_stp_contracts.machine_help import MultiRootTransactionView

__all__ = [
    "apply",
    "approve",
    "cancel",
    "compose_environment",
    "install",
    "plan",
    "recover",
    "status",
]


def __getattr__(name: str) -> object:
    return getattr(service, name)


def plan(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    return service.plan(parameters)


def compose_environment(
    parameters: Mapping[str, object],
) -> Answer[MultiRootTransactionView]:
    return service.compose_environment(parameters)


def approve(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    return service.approve(parameters)


def apply(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    return service.apply(parameters)


def recover(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    return service.recover(parameters)


def status(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    return service.status(parameters)


def cancel(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    return service.cancel(parameters)
