"""`ai-stp eval` — exact local setup evaluation plans and evidence."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import evaluation
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry, transaction
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.evaluation import SetupEvalPlan, SetupEvalProfile, SetupEvalResult


def profile(parameters: Mapping[str, object]) -> Answer[SetupEvalProfile]:
    """Show the closed reference profile for all or one component type."""
    raw = parameters.get("type")
    selected = None if raw is None else (str(raw),)
    return Answer(
        evaluation.reference_profile(selected)  # pyright: ignore[reportArgumentType]
    )


def plan(parameters: Mapping[str, object]) -> Answer[SetupEvalPlan]:
    """Persist an evaluation plan bound to one exact local SetupVersion."""
    # `list | tuple`, and the tuple is the one that matters: a repeatable option
    # reaches a handler as Click's `multiple=True`, which yields a tuple. Testing
    # for `list` alone sent every correct invocation to the `else` branch, so
    # `eval plan` refused `--component-id` in every shape and took `eval run`,
    # `eval show` and `eval status` down with it — none of them can start without
    # a plan (`#384`).
    #
    # The other four readers of repeated options — `config_show._names`,
    # `select`'s `member`, `install`'s `requires-env`, `publication._files` —
    # already accept both. This one was alone.
    raw_component_ids = parameters.get("component-id")
    if raw_component_ids is None:
        component_ids: tuple[str, ...] = ()
    elif isinstance(raw_component_ids, list | tuple):
        raw_items = tuple(cast(list[object] | tuple[object, ...], raw_component_ids))
        if not all(isinstance(item, str) for item in raw_items):
            raise CliFailure("AI_STP_VALIDATION_ERROR", "component-id must be strings")
        component_ids = tuple(cast(tuple[str, ...], raw_items))
    else:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "component-id must be repeated strings")
    with (
        closing(open_registry(configured_path(), create=False)) as connection,
        transaction(connection),
    ):
        planned = evaluation.plan(
            connection,
            setup_id=_required(parameters, "setup-id"),
            setup_version=_required(parameters, "setup-version"),
            component_ids=component_ids,
            harness_version=_required(parameters, "harness-version"),
            provider_version=_required(parameters, "provider-version"),
            runner_version=_required(parameters, "runner-version"),
            at=moment(),
        )
    return Answer(planned)


def run(parameters: Mapping[str, object]) -> Answer[SetupEvalResult]:
    """Run the local-static checks after exact plan confirmation."""
    plan_id = _required(parameters, "plan-id")
    digest = _required(parameters, "expected-plan-digest")
    with (
        closing(open_registry(configured_path(), create=False)) as connection,
        transaction(connection),
    ):
        result = evaluation.run(connection, plan_id, digest, at=moment())
    return Answer(result)


def status(parameters: Mapping[str, object]) -> Answer[SetupEvalResult]:
    """Read one immutable evaluation result without rerunning checks."""
    with closing(open_readonly(configured_path())) as connection:
        return Answer(evaluation.show_result(connection, _required(parameters, "run-id")))


def show(parameters: Mapping[str, object]) -> Answer[SetupEvalResult]:
    """Show the full immutable evidence document for one run."""
    run_id = _required(parameters, "run-id")
    with closing(open_readonly(configured_path())) as connection:
        return Answer(evaluation.show_result(connection, run_id))


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = parameters.get(name)
    if not isinstance(value, str) or not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value
