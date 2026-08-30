"""Exact setup evaluation profiles and local evidence (issue #308)."""

from contextlib import closing

import pytest

from ai_stp_cli.commands import evaluation as command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, evaluation, revisions, versions
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry, transaction
from ai_stp_contracts.evaluation import EvaluationBudget, EvaluationCheck
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import versions as corpus_versions

AT = "2026-08-13T12:00:00.000Z"


def _grok() -> tuple[tuple[FirstPartyVersion, ...], FirstPartyVersion]:
    """The whole grok-build family, which stopped being a pair on 2026-08-29."""
    family = [item for item in corpus_versions() if item.passport.harness_id == "grok-build"]
    components = tuple(item for item in family if item.kind == "component")
    (setup,) = [item for item in family if item.kind == "setup"]
    return components, setup


def _materialize() -> tuple[FirstPartyVersion, FirstPartyVersion]:
    """Record the whole graph, and hand back one member to name in a plan."""
    components, setup = _grok()
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        for item in (*components, setup):
            content.put(connection, item.artifact, at=AT)
            document = item.passport.model_dump(mode="json")
            document.pop("revision_id")
            stored = revisions.commit(connection, document, device_id="device_test")
            versions.record(
                connection,
                stable_id=item.passport.stable_id,
                version=item.passport.version,
                passport_digest=item.passport_digest,
                revision_id=stored.revision_id,
                at=AT,
            )
    return components[0], setup


@pytest.mark.parametrize(
    "component_type",
    ["instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"],
)
def test_reference_profile_covers_every_type_with_separated_methods(
    component_type: str,
) -> None:
    profile = evaluation.reference_profile((component_type,))  # type: ignore[arg-type]

    assert profile.scope == "component"
    assert profile.component_types == [component_type]
    assert {item.method for item in profile.checks} == {
        "deterministic",
        "model_assisted",
        "human_review",
    }
    assert profile.eval_permissions.model_dump() == {
        "filesystem": [],
        "network": [],
        "process": [],
    }


def test_runner_method_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not match"):
        EvaluationCheck(
            check_id="skill.wrong_runner",
            component_type="skill",
            method="model_assisted",
            runner="local_static",
            assertion="Would incorrectly promote a local static result.",
            tolerance="No tolerance.",
            budget=EvaluationBudget(timeout_seconds=10, max_output_bytes=1024),
        )


def test_plan_accepts_the_shape_click_actually_delivers_for_a_repeated_option() -> None:
    """A repeatable option arrives as a tuple, and the handler has to take it.

    Every test in this module built `component-id` as a list, and the handler
    accepted only a list, so the pair agreed with each other and with nothing
    else. `app.py` maps `repeatable` onto Click's `multiple=True`, which yields a
    tuple, and the real command therefore refused every correct invocation with
    `component-id must be repeated strings` — taking `eval run`, `eval show` and
    `eval status` with it, since none of them start without a plan (`#384`).
    """
    component, setup = _materialize()
    common = {
        "setup-id": setup.passport.stable_id,
        "setup-version": setup.passport.version,
        "harness-version": "stable-1.0.0",
        "provider-version": "0.3.0",
        "runner-version": "ai-stp-local-static/1",
    }

    # Accepting the tuple is the whole property: before the fix this call raised
    # `AI_STP_VALIDATION_ERROR` and no plan existed to run, show or check.
    # Neither `plan_id` nor `plan_digest` is comparable across calls — the id is
    # minted per call and the digest binds the moment — so what is asserted is
    # that each shape produces a plan bound to the setup that was named.
    for supplied in ((component.passport.stable_id,), [component.passport.stable_id], ()):
        plan = command.plan({**common, "component-id": supplied}).payload
        assert plan.setup_id == setup.passport.stable_id
        assert plan.setup_version == setup.passport.version

    with pytest.raises(CliFailure) as refused:
        command.plan({**common, "component-id": component.passport.stable_id})
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"


def test_exact_plan_and_run_are_idempotent_without_promoting_unavailable_runners() -> None:
    component, setup = _materialize()
    parameters = {
        "setup-id": setup.passport.stable_id,
        "setup-version": setup.passport.version,
        "component-id": [component.passport.stable_id],
        "harness-version": "stable-1.0.0",
        "provider-version": "0.3.0",
        "runner-version": "ai-stp-local-static/1",
    }

    plan = command.plan(parameters).payload
    # The digest is the confirmation. A run is local, reads only, and persists
    # evidence idempotently, so `ADR-0118` leaves it inside the task's
    # authority; naming the exact plan is the precondition that still holds, and
    # a stale one is refused rather than run against whatever the plan is now.
    with pytest.raises(CliFailure) as stale:
        command.run({"plan-id": plan.plan_id, "expected-plan-digest": "sha256:" + "0" * 64})
    assert stale.value.code == "AI_STP_PRECONDITION_FAILED"

    run_parameters = {
        "plan-id": plan.plan_id,
        "expected-plan-digest": plan.plan_digest,
    }
    first = command.run(run_parameters).payload
    second = command.run(run_parameters).payload

    assert first == second
    assert first.status == "degraded"
    assert first.immutable_published_bytes_changed is False
    assert first.provider_permissions_used is False
    assert {item.status for item in first.checks if item.method == "deterministic"} == {"passed"}
    assert {item.status for item in first.checks if item.method != "deterministic"} == {"not_run"}
    assert command.status({"run-id": first.run_id}).payload == first
    assert command.show({"run-id": first.run_id}).payload == first
    with closing(open_readonly(configured_path())) as connection:
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM object_version), "
            "(SELECT count(*) FROM revision), (SELECT count(*) FROM content), "
            "(SELECT count(*) FROM eval_plan), (SELECT count(*) FROM eval_result)"
        ).fetchone()
        members = len(_grok()[0]) + 1
        assert tuple(counts) == (members, members, members, 1, 1)


def test_plan_rejects_a_component_outside_the_exact_setup_graph() -> None:
    _component, setup = _materialize()
    with pytest.raises(CliFailure, match="outside"):
        command.plan(
            {
                "setup-id": setup.passport.stable_id,
                "setup-version": setup.passport.version,
                "component-id": ["component_01ARZ3NDEKTSV4RRFFQ69G5FAV"],
                "harness-version": "stable-1.0.0",
                "provider-version": "0.3.0",
                "runner-version": "ai-stp-local-static/1",
            }
        )


def test_run_refuses_a_different_plan_digest() -> None:
    _component, setup = _materialize()
    plan = command.plan(
        {
            "setup-id": setup.passport.stable_id,
            "setup-version": setup.passport.version,
            "harness-version": "stable-1.0.0",
            "provider-version": "0.3.0",
            "runner-version": "ai-stp-local-static/1",
        }
    ).payload
    with pytest.raises(CliFailure) as mismatch:
        command.run(
            {
                "plan-id": plan.plan_id,
                "expected-plan-digest": "sha256:" + "0" * 64,
                "confirm": True,
            }
        )
    assert mismatch.value.code == "AI_STP_PRECONDITION_FAILED"
