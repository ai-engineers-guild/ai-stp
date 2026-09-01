"""Explicit embedded-component update: plan does not select; apply creates a version."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import embedded_update, project_passport
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.machine_help import SetupUpdatePlan, SetupUpdateResult
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_sources.models import SourceSnapshot


@dataclass(frozen=True)
class _Request:
    setup_id: str
    version: str
    component_id: str
    harness: str
    snapshot: SourceSnapshot
    project_id: str
    at: str
    device_id: str


def plan(parameters: Mapping[str, object]) -> Answer[SetupUpdatePlan]:
    """Preview one exact replacement without changing the selected setup."""
    request = _request(parameters)
    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(
            embedded_update.plan(
                connection,
                setup_id=request.setup_id,
                version=request.version,
                component_id=request.component_id,
                snapshot=request.snapshot,
                project_id=request.project_id,
                harness_id=request.harness,
                at=request.at,
            )
        )


def apply(parameters: Mapping[str, object]) -> Answer[SetupUpdateResult]:
    """Create a new immutable setup version only after explicit confirmation."""
    request = _request(parameters)
    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(
            embedded_update.apply(
                connection,
                setup_id=request.setup_id,
                version=request.version,
                component_id=request.component_id,
                snapshot=request.snapshot,
                project_id=request.project_id,
                harness_id=request.harness,
                expected_plan_digest=str(parameters.get("expected-plan-digest") or ""),
                device_id=request.device_id,
                at=request.at,
                confirm=parameters.get("confirm") is True,
            )
        )


def _request(parameters: Mapping[str, object]) -> _Request:
    setup_id = str(parameters.get("id") or "")
    version = str(parameters.get("version") or "")
    component_id = str(parameters.get("component-id") or "")
    source = str(parameters.get("source") or "")
    if not setup_id or not version:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a setup identifier and exact version are both required",
            next_actions=["setup update plan --id <id> --version <X.Y> --json"],
        )
    harness = str(parameters.get("harness") or "")
    if harness not in HARNESS_IDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supported harness identifier is required",
            next_actions=["setup update plan --harness <id> --json"],
        )
    if not source:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an exact update snapshot is required",
            next_actions=["setup update plan --id <id> --version <X.Y> --json"],
        )
    intent = embedded_update.parse_source(
        source,
        commit=None if parameters.get("commit") is None else str(parameters["commit"]),
        subpath=None if parameters.get("subpath") is None else str(parameters["subpath"]),
    )
    root = Path(str(parameters.get("project") or Path.cwd())).expanduser()
    current, _warning = identity.load_or_create()
    with closing(open_registry(configured_path(), create=True)) as connection:
        project_id = project_passport.stable_id_for(connection, root.resolve()) or ""
    return _Request(
        setup_id=setup_id,
        version=version,
        component_id=component_id,
        harness=harness,
        snapshot=embedded_update.default_resolve(intent, root=str(root)),
        project_id=project_id,
        at=moment(),
        device_id=current.device_id,
    )
