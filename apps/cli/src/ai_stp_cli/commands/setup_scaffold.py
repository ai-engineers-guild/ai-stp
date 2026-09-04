"""Physical setup authoring scaffold, distinct from compose and install."""

from collections.abc import Mapping
from pathlib import Path

from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import setup_scaffold
from ai_stp_contracts.authoring import SetupScaffoldPlan, SetupScaffoldResult


def plan(parameters: Mapping[str, object]) -> Answer[SetupScaffoldPlan]:
    """Preview every byte of one versioned setup authoring directory."""
    name = _required(parameters, "name", "a setup name is required")
    harness = _required(parameters, "harness", "a concrete harness is required")
    output = Path(_required(parameters, "output", "an output path is required")).expanduser()
    components = parameters.get("components")
    plan_view, _files = setup_scaffold.setup_scaffold_plan(
        name=name,
        harness=harness,
        output=output,
        components=None if components is None else str(components),
    )
    return Answer(plan_view)


def apply(parameters: Mapping[str, object]) -> Answer[SetupScaffoldResult]:
    """Create exactly one confirmed setup scaffold directory from its recomputed plan."""
    name = _required(parameters, "name", "a setup name is required")
    harness = _required(parameters, "harness", "a concrete harness is required")
    output = Path(_required(parameters, "output", "an output path is required")).expanduser()
    expected = _required(
        parameters, "expected-plan-digest", "the exact scaffold plan digest is required"
    )
    components = parameters.get("components")
    plan_view, files = setup_scaffold.setup_scaffold_plan(
        name=name,
        harness=harness,
        output=output,
        components=None if components is None else str(components),
    )
    return Answer(setup_scaffold.apply_setup_scaffold(plan_view, files, expected_digest=expected))


def _required(parameters: Mapping[str, object], name: str, message: str) -> str:
    value = parameters.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CliFailure("AI_STP_VALIDATION_ERROR", message)
    return value
