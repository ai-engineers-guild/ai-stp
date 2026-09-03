"""Exact setup evaluation profiles and local evidence (issue #308)."""

import json
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.commands import component as component_command
from ai_stp_cli.commands import evaluation as command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import components, content, evaluation, revisions, versions
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry, transaction
from ai_stp_contracts.evaluation import EvaluationBudget, EvaluationCheck
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import family as corpus_family

AT = "2026-08-13T12:00:00.000Z"


def _grok() -> tuple[tuple[FirstPartyVersion, ...], FirstPartyVersion]:
    """The whole grok-build family, which stopped being a pair on 2026-08-29."""
    family = list(corpus_family("grok-build", "nddev-builder"))
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


def test_an_adopted_draft_component_is_loaded_through_the_one_passport_owner(
    tmp_path: Path,
) -> None:
    """`#385`, the half `eval` still had: an adopted draft failed its loader.

    Measured live: a setup that had passed adopt, release, propose, confirm,
    bundle, install and verify was refused by `eval plan` with "a recorded
    component passport is invalid" — empty details, no next action. The stored
    envelope of an adopted component is the draft, narrower than
    `ComponentVersionPassport`; `select impact` already falls back to
    `component_passports.version_passport`, the one owner that synthesises the
    public passport from the draft's facts, and the evaluation loader did not.
    """
    project = tmp_path / "repository"
    skill = project / ".claude" / "skills" / "probe"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Probe\nA skill under evaluation.\n", encoding="utf-8")

    with closing(open_registry(configured_path(), create=True)) as connection:
        found = next(
            item for item in components.discover(project=project) if item.absolute == skill
        )
        stored = components.adopt(connection, found, device_id="device_test")
        connection.commit()

    patch = tmp_path / "authoring.json"
    patch.write_text(
        json.dumps(
            {
                "name": "probe",
                "description": "A skill under evaluation.",
                "tags": ["probe"],
                "license": {"spdx_id": "MIT", "redistribution_allowed": True},
                "projection_kind": "native_files",
                "source": {
                    "repository": "https://github.com/example/component",
                    "commit": "a" * 40,
                    "path": "skills/probe",
                },
            }
        ),
        encoding="utf-8",
    )
    component_command.passport_update(
        {"id": stored.stable_id, "expected-revision": stored.revision_id, "from": str(patch)}
    )
    component_command.version_release({"id": stored.stable_id})

    with closing(open_readonly(configured_path())) as connection:
        recorded = versions.held(connection, stored.stable_id, "1.0")
        assert recorded is not None
        loaded = evaluation._component(  # pyright: ignore[reportPrivateUsage]
            connection, stored.stable_id, "1.0", recorded.passport_digest
        )

    assert loaded.coordinate.component_type == "skill"
    assert loaded.coordinate.passport_digest == recorded.passport_digest


def test_an_incomplete_adopted_draft_must_be_enriched_before_version_evaluation(
    tmp_path: Path,
) -> None:
    """An evaluation names an immutable version, so an incomplete draft cannot enter it."""
    project = tmp_path / "repository"
    skill = project / ".claude" / "skills" / "plain"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "# Plain\nAdopted and released, nothing more.\n", encoding="utf-8"
    )

    with closing(open_registry(configured_path(), create=True)) as connection:
        found = next(
            item for item in components.discover(project=project) if item.absolute == skill
        )
        stored = components.adopt(connection, found, device_id="device_test")
        connection.commit()
    with pytest.raises(CliFailure) as incomplete:
        component_command.version_release({"id": stored.stable_id})
    assert incomplete.value.code == "AI_STP_VALIDATION_ERROR"
    assert "name" in str(incomplete.value.details.get("fields"))


def test_a_draft_without_its_kind_is_named_as_a_precondition_for_evaluation(
    tmp_path: Path,
) -> None:
    """What the evaluator genuinely cannot do without is named, with a next action."""
    from ai_stp_cli.local import cache, passports

    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = "component_01J0000000000000000000000E"
        artifact = content.put(connection, b"# kindless\n", at=AT)
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
            (stable_id, AT),
        )
        fact = {"origin": "observed", "confirmation": "none", "observed_at": AT}
        document: dict[str, object] = {
            "schema_version": 1,
            "kind": "component",
            "stable_id": stable_id,
            "owner_id": passports.owner().account_id,
            "created_at": AT,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": {
                "harness_id": {"value": "claude-code", **fact},
                "content_digest": {"value": artifact.digest, **fact},
            },
        }
        stored = revisions.commit(connection, document, device_id="device_test")  # type: ignore[arg-type]
        digest = cache.digest_of(stored.envelope.model_dump(mode="json"))
        versions.record(
            connection,
            stable_id=stable_id,
            version="1.0",
            passport_digest=digest,
            revision_id=stored.revision_id,
            at=AT,
        )

        with pytest.raises(CliFailure) as raised:
            evaluation._component(connection, stable_id, "1.0", digest)  # pyright: ignore[reportPrivateUsage]

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert raised.value.details["field"] == "component_type"
    assert raised.value.next_actions == [f"component passport show --id {stable_id} --json"]
