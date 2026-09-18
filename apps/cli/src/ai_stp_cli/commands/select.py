"""`ai-stp select` — Click handlers. Effects live in `application.select`."""

from ai_stp_cli.application import select as _service
from ai_stp_cli.application.select import (
    blast_radius,
    cancel,
    compile_harness_bundle,
    compile_setup_version_bundle,
    compile_withdrawal_bundle,
    confirm,
    context_for_project,
    dependency_graph,
    eligible,
    eligible_everywhere,
    harness_bundle,
    impact_report,
    propose,
    provider_conformance,
    provider_fetch,
    provider_network,
    provider_trust,
    reports,
    session,
)


def __getattr__(name: str) -> object:
    return getattr(_service, name)


__all__ = [
    "blast_radius",
    "cancel",
    "compile_harness_bundle",
    "compile_setup_version_bundle",
    "compile_withdrawal_bundle",
    "confirm",
    "context_for_project",
    "dependency_graph",
    "eligible",
    "eligible_everywhere",
    "harness_bundle",
    "impact_report",
    "propose",
    "provider_conformance",
    "provider_fetch",
    "provider_network",
    "provider_trust",
    "reports",
    "session",
]
