"""`select eligibility`: the constraint decision seen from the command surface."""

import io
import os
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    acquired_trust,
    cache,
    component_passports,
    consent,
    content,
    passports,
    project_passport,
    revisions,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.local.passports import owner
from ai_stp_cli.paths import data_dir
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_contracts.machine_help import EligibilityMatrix, EligibilityReport
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_passports import EnvVarRequirement, LicenseInfo

MOMENT = "2026-08-08T10:00:00.000Z"
DEVICE = "device_test"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _register(connection: sqlite3.Connection, suffix: str, *, harness_id: str) -> str:
    stable_id = f"component_01J0000000000000000000000{suffix}"
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, MOMENT),
    )
    revisions.commit(
        connection,
        {  # pyright: ignore[reportArgumentType]
            "schema_version": 1,
            "kind": "component",
            "stable_id": stable_id,
            "owner_id": owner().account_id,
            "created_at": MOMENT,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": {
                "harness_id": {
                    "value": harness_id,
                    "origin": "observed",
                    "confirmation": "none",
                    "observed_at": MOMENT,
                },
                "component_type": {
                    "value": "skill",
                    "origin": "observed",
                    "confirmation": "none",
                    "observed_at": MOMENT,
                },
            },
        },
        device_id=DEVICE,
    )
    connection.commit()
    return stable_id


def _register_catalog_passport(
    connection: sqlite3.Connection, suffix: str, *, harness_id: str
) -> str:
    """A version passport as `registry acquire` stores it: harness_id on the document."""
    stable_id = f"component_01J0000000000000000000000{suffix}"
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, MOMENT),
    )
    revisions.commit(
        connection,
        {  # pyright: ignore[reportArgumentType]
            "schema_version": 1,
            "kind": "component",
            "stable_id": stable_id,
            "owner_id": owner().account_id,
            "created_at": MOMENT,
            "visibility": "public",
            "parent_revision_ids": [],
            "harness_id": harness_id,
            "facts": {
                "component_type": {
                    "value": "skill",
                    "origin": "observed",
                    "confirmation": "none",
                    "observed_at": MOMENT,
                },
            },
        },
        device_id=DEVICE,
    )
    connection.commit()
    return stable_id


def _report(root: Path, **parameters: object) -> EligibilityReport:
    return select.eligible({"harness": "claude-code", "project": str(root), **parameters}).payload


@pytest.mark.parametrize("given", ["", "undefined", "not-a-harness"])
def test_an_unsupported_harness_is_refused_before_anything_is_read(given: str) -> None:
    with pytest.raises(CliFailure) as raised:
        select.eligible({"harness": given})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_an_empty_registry_is_an_honest_empty_report(tmp_path: Path) -> None:
    """`no_candidate` is a normal state in `SPEC-006`, not an error."""
    report = _report(tmp_path)
    assert report.candidates == []
    assert report.admissible_count == 0
    assert report.auto_selectable_count == 0


def test_the_report_carries_the_facts_the_verdict_was_reached_from(tmp_path: Path) -> None:
    report = _report(tmp_path)
    assert report.harness_id == "claude-code"
    assert report.os
    assert report.arch
    assert report.capability_vocabulary_version


def test_a_project_fact_reaches_the_target_as_a_capability(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    held = set(_report(tmp_path).capabilities)
    assert {"project.language.python", "project.surface.agents_md"} <= held


def test_a_local_object_for_this_harness_is_admissible(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    stable_id = _register(registry, "A", harness_id="claude-code")
    report = _report(tmp_path)
    assert [item.stable_id for item in report.candidates] == [stable_id]
    only = report.candidates[0]
    assert only.lane == "local_owner_or_pinned"
    assert only.admissible
    assert only.auto_selectable
    assert report.admissible_count == 1


def test_a_catalog_passport_uses_top_level_harness_id(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Acquired version passports declare harness_id on the document, not as a fact."""
    stable_id = _register_catalog_passport(registry, "P", harness_id="claude-code")
    report = _report(tmp_path)
    assert [item.stable_id for item in report.candidates] == [stable_id]
    only = report.candidates[0]
    assert only.admissible
    assert [item.code for item in only.refusals] == []


def test_eligibility_reads_a_legacy_owner_without_recreating_the_owner_file(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    passports.init_developer(registry, device_id=DEVICE)
    stable_id = _register(registry, "E", harness_id="claude-code")
    (data_dir() / "owner.json").unlink()

    report = _report(tmp_path)

    assert [item.stable_id for item in report.candidates] == [stable_id]
    assert report.candidates[0].admissible
    assert not (data_dir() / "owner.json").exists()


def _matrix(root: Path, **parameters: object) -> EligibilityMatrix:
    return select.eligible_everywhere({"project": str(root), **parameters}).payload


def test_the_matrix_answers_for_every_supported_harness_installed_or_not(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Whether an object fits Pi is a property of the object, not of this machine.

    `select eligibility` answers for the harness it was given, and with only
    that available an agent answered "where does this fit" with the harness its
    own session happened to run in — a portable skill then carried that
    `harness_id` into a draft passport (`#380`, `REQ-629`).

    None of the five is installed in this test, and all five have a row.
    """
    _register(registry, "M", harness_id="claude-code")

    matrix = _matrix(tmp_path)

    answered = [report.harness_id for report in matrix.harnesses]
    assert answered == sorted(HARNESS_IDS)
    assert list(matrix.requested) == answered
    assert len(answered) == len(set(answered))


def test_the_matrix_refuses_a_harness_the_object_does_not_declare(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """An object laid out for one harness does not become eligible for another."""
    _register(registry, "N", harness_id="claude-code")

    rows = {report.harness_id: report for report in _matrix(tmp_path).harnesses}

    assert rows["claude-code"].admissible_count == 1
    for other in sorted(set(HARNESS_IDS) - {"claude-code"}):
        assert rows[other].admissible_count == 0, other
        refused = rows[other].candidates[0]
        assert [item.code for item in refused.refusals] == ["harness_mismatch"]


def test_naming_a_harness_narrows_the_matrix_without_emptying_it(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Explicit narrowing stays allowed; it is the *default* that had to change."""
    _register(registry, "Q", harness_id="codex")

    narrowed = _matrix(tmp_path, harness=("codex", "pi"))

    assert [report.harness_id for report in narrowed.harnesses] == ["codex", "pi"]
    assert list(narrowed.requested) == ["codex", "pi"]

    with pytest.raises(CliFailure) as refused:
        _matrix(tmp_path, harness=("codex", "not-a-harness"))
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"
    assert refused.value.next_actions


def test_a_local_object_for_another_harness_is_refused_by_name(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _register(registry, "B", harness_id="codex")
    only = _report(tmp_path).candidates[0]
    assert not only.admissible
    assert [item.code for item in only.refusals] == ["harness_mismatch"]
    assert only.refusals[0].family == "compatibility"
    assert only.refusals[0].details == {"declared": "codex", "target": "claude-code"}


def test_looking_at_what_is_allowed_creates_nothing(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`ADR-0027` makes a durable object the result of a confirmation, not a look."""
    _register(registry, "C", harness_id="claude-code")
    before = registry.execute("SELECT count(*) AS held FROM revision").fetchone()["held"]
    _report(tmp_path)
    _report(tmp_path)
    after = registry.execute("SELECT count(*) AS held FROM revision").fetchone()["held"]
    assert after == before


def test_two_runs_over_the_same_facts_agree(registry: sqlite3.Connection, tmp_path: Path) -> None:
    _register(registry, "D", harness_id="claude-code")
    _register(registry, "E", harness_id="codex")
    assert _report(tmp_path).model_dump(mode="json") == _report(tmp_path).model_dump(mode="json")


def _ready(connection: sqlite3.Connection, root: Path) -> str:
    """A machine with the three passports a session needs (`REQ-621`)."""
    passports.init_developer(connection, device_id=DEVICE)
    passports.ensure_device(connection, device_id=DEVICE)
    found = project_passport.scan(connection, root)
    project_passport.record(connection, found, device_id=DEVICE)
    connection.commit()
    return found.stable_id


def _released(connection: sqlite3.Connection, suffix: str) -> str:
    """One component with one released version, which a member must have."""
    stable_id = _register(connection, suffix, harness_id="claude-code")
    stored = revisions.head(connection, stable_id)
    assert stored is not None
    versions.record(
        connection,
        stable_id=stable_id,
        version="1.0",
        passport_digest=cache.digest_of(stored.envelope.model_dump(mode="json")),
        revision_id=stored.revision_id,
        at=MOMENT,
    )
    connection.commit()
    return stable_id


def test_a_session_needs_a_project_passport_before_it_can_start(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        select.session({"harness": "claude-code", "project": str(tmp_path)})
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_proposing_and_confirming_through_the_command_surface(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    project_id = _ready(registry, tmp_path)
    stable_id = _released(registry, "F")

    session = select.propose(
        {
            "harness": "claude-code",
            "project": str(tmp_path),
            "member": [f"{stable_id}@1.0"],
        }
    ).payload
    assert session.project_id == project_id
    assert len(session.proposals) == 1
    assert session.selected_stable_id is None
    proposal_id = session.proposals[0].proposal_id
    assert session.proposals[0].members[0].stable_id == stable_id

    confirmed = select.confirm({"proposal": proposal_id}).payload
    assert confirmed.created
    assert confirmed.state == "pending_install"
    assert confirmed.trace["policy_version"] == session.policy_version

    after = select.session({"harness": "claude-code", "project": str(tmp_path)}).payload
    assert after.selected_stable_id == confirmed.stable_id
    assert after.selected_state == "pending_install"
    assert after.proposals == [], "a confirmed proposal is no longer open"


def test_a_repeat_confirmation_returns_the_same_version(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _released(registry, "G")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    proposal_id = session.proposals[0].proposal_id

    first = select.confirm({"proposal": proposal_id}).payload
    second = select.confirm({"proposal": proposal_id}).payload
    assert (second.stable_id, second.version) == (first.stable_id, first.version)
    assert first.created and not second.created


def test_a_member_named_without_an_exact_version_is_refused(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _released(registry, "H")
    with pytest.raises(CliFailure) as raised:
        select.propose({"harness": "claude-code", "project": str(tmp_path), "member": [stable_id]})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_member_with_no_recorded_version_is_not_found(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _register(registry, "J", harness_id="claude-code")
    registry.commit()
    with pytest.raises(CliFailure) as raised:
        select.propose(
            {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_member_for_another_harness_is_refused_before_it_is_proposed(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`REQ-601`: the mechanical stage runs before selection, and proposing is one."""
    _ready(registry, tmp_path)
    stable_id = _register(registry, "K", harness_id="codex")
    stored = revisions.head(registry, stable_id)
    assert stored is not None
    versions.record(
        registry,
        stable_id=stable_id,
        version="1.0",
        passport_digest=cache.digest_of(stored.envelope.model_dump(mode="json")),
        revision_id=stored.revision_id,
        at=MOMENT,
    )
    registry.commit()

    with pytest.raises(CliFailure) as raised:
        select.propose(
            {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "harness_mismatch" in str(raised.value.details)


def test_cancelling_removes_a_proposal_from_the_session(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _released(registry, "M")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    after = select.cancel({"proposal": session.proposals[0].proposal_id}).payload
    assert after.proposals == []
    assert after.selected_stable_id is None


def test_confirming_without_naming_a_proposal_is_refused() -> None:
    with pytest.raises(CliFailure) as raised:
        select.confirm({})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_the_policy_version_names_the_setting_it_came_from(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`REQ-620`: a changed limit changes behaviour without an edit to the code."""
    _ready(registry, tmp_path)
    reported = select.session({"harness": "claude-code", "project": str(tmp_path)}).payload
    assert "result_limit=" in reported.policy_version


def test_the_closure_of_a_proposal_resolves_through_the_command(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _released(registry, "N")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload

    resolved = select.dependency_graph({"proposal": session.proposals[0].proposal_id}).payload
    assert resolved.resolved
    assert resolved.order == [f"{stable_id}@1.0"]
    assert resolved.max_depth >= 1


def test_a_closure_can_be_checked_before_anything_is_proposed(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _released(registry, "P")
    resolved = select.dependency_graph({"member": [f"{stable_id}@1.0"]}).payload
    assert resolved.resolved
    assert [item.stable_id for item in resolved.nodes] == [stable_id]


def test_the_graph_command_takes_a_proposal_or_members_but_not_both(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _released(registry, "Q")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload

    for parameters in (
        {},
        {"proposal": session.proposals[0].proposal_id, "member": [f"{stable_id}@1.0"]},
    ):
        with pytest.raises(CliFailure) as raised:
            select.dependency_graph(parameters)
        assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_the_graph_command_never_takes_a_digest_from_the_caller(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """It is read from the registry, so the two statements cannot disagree."""
    _ready(registry, tmp_path)
    stable_id = _released(registry, "R")
    resolved = select.dependency_graph({"member": [f"{stable_id}@1.0"]}).payload
    recorded = versions.held(registry, stable_id, "1.0")
    assert recorded is not None
    assert resolved.nodes[0].passport_digest == recorded.passport_digest


def test_an_unknown_proposal_has_no_closure(registry: sqlite3.Connection, tmp_path: Path) -> None:
    _ready(registry, tmp_path)
    with pytest.raises(CliFailure) as raised:
        select.dependency_graph({"proposal": "proposal_01J0000000000000000000000Z"})
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_the_reports_come_back_together_through_the_command(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _released(registry, "S")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload

    both = select.reports(
        {
            "harness": "claude-code",
            "project": str(tmp_path),
            "proposal": session.proposals[0].proposal_id,
        }
    ).payload
    assert [item.stable_id for item in both.chosen] == [stable_id]
    assert both.chosen[0].lane == "local_owner_or_pinned"
    assert both.chosen[0].reason == ("your own or exactly pinned; installable after local checks")
    assert both.rejected == []
    assert set(both.operations) <= {
        "canonical_ordering",
        "exact_reference_deduplication",
        "dependency_closure",
        "disjoint_managed_path_union",
        "deterministic_report_generation",
    }
    assert both.conversion, "a report with no conversion entries answers half the question"


def test_reports_need_a_proposal(registry: sqlite3.Connection, tmp_path: Path) -> None:
    _ready(registry, tmp_path)
    with pytest.raises(CliFailure) as raised:
        select.reports({"harness": "claude-code", "project": str(tmp_path)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_there_are_no_reports_until_the_closure_resolves(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Reporting on a composition that cannot exist would describe a fiction."""
    _ready(registry, tmp_path)
    stable_id = _released(registry, "T")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    registry.execute("DELETE FROM object_version WHERE stable_id = ?", (stable_id,))
    registry.commit()

    with pytest.raises(CliFailure) as raised:
        select.reports(
            {
                "harness": "claude-code",
                "project": str(tmp_path),
                "proposal": session.proposals[0].proposal_id,
                "scope": "project",
            }
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "dependency_missing" in str(raised.value.details)


def _adopted(registry: sqlite3.Connection, tmp_path: Path, name: str) -> str:
    """One component adopted from a real file, so its bytes are in the store."""
    from ai_stp_cli.commands import component as command
    from ai_stp_cli.local import harnesses

    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "claude-code")
    place = harnesses.config_root(detector, dict(os.environ)) / "skills"
    place.mkdir(parents=True, exist_ok=True)
    (place / name).write_text(f"# {name}\n", encoding="utf-8")
    stable_id = command.adopt({"path": str(place / name)}).payload.stable_id
    _complete_adopted(registry, stable_id, name)
    command.version_release({"id": stable_id})
    return stable_id


def _complete_adopted(registry: sqlite3.Connection, stable_id: str, name: str) -> None:
    head = revisions.head(registry, stable_id)
    assert head is not None
    component_passports.update(
        registry,
        stable_id,
        head.revision_id,
        ComponentPassportPatch(
            name=name,
            description=f"Locally adopted {name} component.",
            tags=["local"],
            license=LicenseInfo(spdx_id="MIT", redistribution_allowed=True),
        ),
        device_id=DEVICE,
    )


def test_a_bundle_compiles_from_adopted_content(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "review.md")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    select.confirm({"proposal": session.proposals[0].proposal_id})

    compiled = select.harness_bundle(
        {
            "harness": "claude-code",
            "project": str(tmp_path),
            "proposal": session.proposals[0].proposal_id,
        }
    ).payload
    assert compiled.compiled
    assert compiled.digest.startswith("sha256:")
    assert compiled.artifact_digest.startswith("sha256:")
    assert compiled.byte_length > compiled.files[0].byte_length
    assert [item.path for item in compiled.files] == ["skills/review.md"]
    assert compiled.files[0].owner == stable_id


def test_a_hook_manifest_bundle_keeps_sibling_handlers(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    from ai_stp_cli.local import components, composition

    hooks = tmp_path / ".agents"
    (hooks / "hooks").mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    (hooks / "hooks" / "h01.py").write_text("print('deny')\n", encoding="utf-8")
    found = next(
        item
        for item in components.discover(project=tmp_path)
        if item.component_type == "hook" and item.absolute == hooks / "hooks.json"
    )
    stored = components.adopt(registry, found, device_id=DEVICE)
    facts = stored.envelope.model_dump(mode="json")["facts"]
    surface = composition.Surface(
        stable_id=stored.stable_id,
        version="1.0",
        component_type="hook",
        harness_id="antigravity",
        revision_id=stored.revision_id,
        source_name="hooks.json",
        content_format=str(facts["content_format"]["value"]),
        managed_paths=("config/hooks.json", "config/hooks/h01.py"),
    )

    sources = select._bundle_sources(  # pyright: ignore[reportPrivateUsage]
        registry,
        (surface,),
        composition.Target(harness_id="antigravity", os="windows", arch="amd64"),
    )

    assert [item.path for item in sources] == ["config/hooks.json", "config/hooks/h01.py"]


def test_a_directory_hook_artifact_lands_handlers_under_hooks(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Plugin-style `hooks/` directories store handlers beside `hooks.json`.

    Adopting the directory captures `hooks.json` and `guard.sh`, not
    `hooks/guard.sh`. Projection still has to land the handler at
    `config/hooks/guard.sh`, or the installed hook cannot execute.
    """
    from ai_stp_cli.local import components, composition

    plugin = tmp_path / "plugins" / "flow"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text('{"name": "flow"}\n', encoding="utf-8")
    (plugin / "hooks").mkdir()
    (plugin / "hooks" / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    (plugin / "hooks" / "guard.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    found = next(
        item
        for item in components.discover(project=tmp_path)
        if item.component_type == "hook" and item.absolute == plugin / "hooks"
    )
    stored = components.adopt(registry, found, device_id=DEVICE)
    facts = stored.envelope.model_dump(mode="json")["facts"]
    surface = composition.Surface(
        stable_id=stored.stable_id,
        version="1.0",
        component_type="hook",
        harness_id="antigravity",
        revision_id=stored.revision_id,
        source_name="hooks",
        content_format=str(facts["content_format"]["value"]),
        managed_paths=("config/hooks.json",),
    )

    sources = select._bundle_sources(  # pyright: ignore[reportPrivateUsage]
        registry,
        (surface,),
        composition.Target(harness_id="antigravity", os="windows", arch="amd64"),
    )

    assert sorted(item.path for item in sources) == [
        "config/hooks.json",
        "config/hooks/guard.sh",
    ]


def test_bundle_sources_refuse_a_declared_root_the_artifact_does_not_cover(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    from ai_stp_cli.local import composition, revisions

    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "review.md")
    stored = revisions.head(registry, stable_id)
    assert stored is not None
    facts = stored.envelope.model_dump(mode="json")["facts"]
    surface = composition.Surface(
        stable_id=stored.stable_id,
        version="1.0",
        component_type="skill",
        harness_id="claude-code",
        revision_id=stored.revision_id,
        source_name="review.md",
        content_format=str(facts["content_format"]["value"]),
        managed_paths=("skills/review.md", "skills/missing.md"),
    )
    with pytest.raises(CliFailure, match="declared managed paths"):
        select._bundle_sources(  # pyright: ignore[reportPrivateUsage]
            registry,
            (surface,),
            composition.Target(harness_id="claude-code", os="linux", arch="x86_64"),
        )


def test_declared_covers_prefer_passport_roots_over_projected_files() -> None:
    from ai_stp_cli.local import bundle, composition

    surfaces = (
        composition.Surface(
            stable_id="component_a",
            version="1.0",
            component_type="skill",
            harness_id="claude-code",
            managed_paths=("skills/foo",),
        ),
    )
    sources = (
        bundle.Source("skills/foo/SKILL.md", b"# foo\n", "component_a"),
        bundle.Source("skills/foo/references/a.md", b"a\n", "component_a"),
    )
    assert select._declared_covers(surfaces, sources) == frozenset({"skills/foo"})  # pyright: ignore[reportPrivateUsage]


def test_managed_path_drift_treats_declared_paths_as_roots() -> None:
    missing, undeclared = select._managed_path_drift(  # pyright: ignore[reportPrivateUsage]
        frozenset({"skills/foo"}),
        frozenset({"skills/foo/SKILL.md", "skills/foo/references/a.md"}),
    )
    assert missing == frozenset()
    assert undeclared == frozenset()
    missing, undeclared = select._managed_path_drift(  # pyright: ignore[reportPrivateUsage]
        frozenset({"skills/foo"}),
        frozenset({"skills/foo/SKILL.md", "other.md"}),
    )
    assert missing == frozenset()
    assert undeclared == frozenset({"other.md"})
    missing, undeclared = select._managed_path_drift(  # pyright: ignore[reportPrivateUsage]
        frozenset({"skills/foo", "skills/bar"}),
        frozenset({"skills/foo/SKILL.md"}),
    )
    assert missing == frozenset({"skills/bar"})
    assert undeclared == frozenset()


def test_a_bundle_preserves_every_file_and_mode_from_an_adopted_skill_tree(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    from ai_stp_cli.commands import component as command
    from ai_stp_cli.local import harnesses

    _ready(registry, tmp_path)
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "claude-code")
    skill = harnesses.config_root(detector, dict(os.environ)) / "skills" / "reviewer"
    (skill / "references").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "SKILL.md").write_bytes(b"# reviewer\n")
    (skill / "references" / "policy.md").write_bytes(b"policy\n")
    script = skill / "scripts" / "check.sh"
    script.write_bytes(b"#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    stable_id = command.adopt({"path": str(skill)}).payload.stable_id
    _complete_adopted(registry, stable_id, "reviewer")
    command.version_release({"id": stable_id})
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    proposal_id = session.proposals[0].proposal_id
    select.confirm({"proposal": proposal_id})

    compiled = select.compile_harness_bundle(registry, proposal_id, "claude-code")
    assert compiled.compiled
    paths_modes = [(item.path, item.mode) for item in compiled.files]
    if os.name == "nt":
        # Windows does not retain Unix executable bits; every file is owner-read/write.
        assert [path for path, _ in paths_modes] == [
            "skills/reviewer/SKILL.md",
            "skills/reviewer/references/policy.md",
            "skills/reviewer/scripts/check.sh",
        ]
    else:
        assert paths_modes == [
            ("skills/reviewer/SKILL.md", 0o644),
            ("skills/reviewer/references/policy.md", 0o644),
            ("skills/reviewer/scripts/check.sh", 0o755),
        ]
    with zipfile.ZipFile(io.BytesIO(compiled.archive), "r") as archive:
        assert archive.read("files/skills/reviewer/references/policy.md") == b"policy\n"


def test_a_confirmed_bundle_reads_the_exact_graph_revision_not_a_later_head(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """A mutable draft head cannot rewrite an already confirmed setup version."""
    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "pinned.md")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    proposal_id = session.proposals[0].proposal_id
    select.confirm({"proposal": proposal_id})

    released = revisions.head(registry, stable_id)
    assert released is not None
    released_document = cast(dict[str, JsonValue], released.envelope.model_dump(mode="json"))
    released_facts = cast(dict[str, JsonValue], released_document["facts"])
    released_digest_fact = cast(dict[str, JsonValue], released_facts["content_digest"])
    released_digest = str(released_digest_fact["value"])
    released_bytes = content.get(registry, released_digest)

    later = content.put(registry, b"# unconfirmed later draft\n", at=MOMENT)
    later_document = cast(dict[str, JsonValue], released.envelope.model_dump(mode="json"))
    later_document["parent_revision_ids"] = []
    later_facts = cast(dict[str, JsonValue], later_document["facts"])
    later_digest_fact = cast(dict[str, JsonValue], later_facts["content_digest"])
    later_digest_fact["value"] = later.digest
    moved = revisions.commit(registry, later_document, device_id=DEVICE)
    registry.commit()
    assert moved.revision_id != released.revision_id
    assert {item.revision_id for item in revisions.heads(registry, stable_id)} == {
        released.revision_id,
        moved.revision_id,
    }

    compiled = select.compile_harness_bundle(registry, proposal_id, "claude-code")
    with zipfile.ZipFile(io.BytesIO(compiled.archive), "r") as archive:
        assert archive.read("files/skills/pinned.md") == released_bytes


def test_an_unconfirmed_proposal_has_no_setup_version_to_bundle(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "unconfirmed.md")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload

    with pytest.raises(CliFailure) as raised:
        select.harness_bundle(
            {
                "harness": "claude-code",
                "project": str(tmp_path),
                "proposal": session.proposals[0].proposal_id,
            }
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_compiling_the_same_composition_twice_gives_one_digest(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """The acceptance criterion, through the command surface."""
    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "again.md")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    confirmed = select.confirm({"proposal": session.proposals[0].proposal_id}).payload
    parameters = {
        "harness": "claude-code",
        "project": str(tmp_path),
        "proposal": session.proposals[0].proposal_id,
    }
    assert (
        select.harness_bundle(parameters).payload.digest
        == select.harness_bundle(parameters).payload.digest
    )
    with closing(open_readonly(configured_path())) as connection:
        prepared = select.compile_setup_version_bundle(
            connection,
            confirmed.stable_id,
            confirmed.version,
            expected_harness="claude-code",
        )
    composed = select.compile_harness_bundle(
        registry, session.proposals[0].proposal_id, "claude-code"
    )
    assert prepared.digest == composed.digest
    assert prepared.artifact_digest == composed.artifact_digest
    assert prepared.archive == composed.archive


def test_a_bundle_needs_a_proposal(registry: sqlite3.Connection, tmp_path: Path) -> None:
    _ready(registry, tmp_path)
    with pytest.raises(CliFailure) as raised:
        select.harness_bundle({"harness": "claude-code", "project": str(tmp_path)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_missing_passport_names_the_command_that_creates_it() -> None:
    """A refusal that points at a diagnostic is a dead end.

    `select propose` refused with `next_actions: ["doctor --json"]`, and `doctor`
    creates nothing — it answered `ready` on the very installation that had just
    been refused. Following the advice confirmed nothing was wrong and left the
    caller exactly where they started.
    """
    from ai_stp_cli.local import passports

    creates = passports.CREATES_PASSPORT
    assert creates["developer"] == "passport developer init --json"
    assert creates["device"] == "passport device refresh --json"
    for action in creates.values():
        assert "doctor" not in action


def test_every_named_passport_command_is_a_real_command() -> None:
    """A next action that does not parse is worse than none."""
    from ai_stp_cli.local import passports
    from ai_stp_cli.registry import COMMANDS

    known = {command.name for command in COMMANDS}
    creates = passports.CREATES_PASSPORT
    for action in creates.values():
        words = action.split()
        path = " ".join(words[: next(i for i, w in enumerate(words) if w.startswith("--"))])
        assert path in known, f"{path!r} is not a declared command"


def test_select_confirm_declares_a_flag_it_can_actually_check() -> None:
    """`explicit_flag` is a promise the command has to keep itself.

    `_require_declared_flags` skips confirmation flags on purpose: a missing
    confirmation is `AI_STP_USER_DECISION_REQUIRED` and exit class 4, not a
    malformed call, so the use case that knows what is being confirmed raises
    it. A command that declares `explicit_flag` and carries no flag to check
    promises a decision it never asks for; every one that declares it must
    carry the flag. (`select confirm` once declared it with no flag, then
    gained one, then lost the declaration on 2026-09-02: naming the exact
    proposal is the decision, `ADR-0118`.)
    """
    from ai_stp_cli.registry import COMMANDS

    declared = {
        command.name: command.descriptor
        for command in COMMANDS
        if command.descriptor.confirmation == "explicit_flag"
    }
    assert declared, (
        "the registry must still carry explicit-flag commands for this to prove anything"
    )
    for name, descriptor in declared.items():
        booleans = {
            parameter.name
            for parameter in descriptor.parameters
            if parameter.value_type == "boolean"
        }
        assert "confirm" in booleans, f"{name} promises explicit_flag with no flag to check"


def test_every_destructive_command_asks_for_a_decision_of_its_own() -> None:
    """`destructive` is defined as needing that decision.

    "removes data, a target or a backup, and needs a decision of its own even
    when the caller already approved the surrounding work". `toolchain remove`
    declared the class, set no `confirmation` at all so the default `none`
    applied, and deleted files from disk on a bare call.
    """
    from ai_stp_cli.registry import COMMANDS

    for command in COMMANDS:
        if command.descriptor.mutability != "destructive":
            continue
        assert command.descriptor.confirmation == "explicit_flag", (
            f"{command.name} removes data and declares no confirmation"
        )


def test_confirming_names_the_proposal_and_asks_for_nothing_else() -> None:
    """Naming the exact proposal is the decision (`ADR-0118`, amendment of 2026-09-02).

    A bare call used to stop with `AI_STP_USER_DECISION_REQUIRED` and a next
    action telling the caller to add `--confirm` — a second question about the
    one answer already given. The first refusal a well-formed call can meet
    now is about the proposal itself.
    """
    from ai_stp_cli.commands import select as select_command

    with pytest.raises(CliFailure) as raised:
        select_command.confirm({"proposal": "proposal_01ARZ3NDEKTSV4RRFFQ69G5FAV"})
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert not any("--confirm" in action for action in raised.value.next_actions)


def test_a_proposal_with_no_members_is_refused_unless_the_emptiness_is_named(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Zero members by omission is a search that found nothing (`REQ-630`).

    An empty setup is a real thing to want — a harness configured to project no
    files at all — and until now the only way to make one was to write the
    registry by hand, which is not a workflow. But the call that means it looked
    exactly like the call that meant nothing, and the object it freezes is
    immutable. So the emptiness is named, and the bare call keeps refusing.
    """
    _ready(registry, tmp_path)

    with pytest.raises(CliFailure) as raised:
        select.propose({"harness": "claude-code", "project": str(tmp_path)})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert "composes nothing" in raised.value.message
    assert "--empty" in raised.value.details["empty_is_deliberate"]


def test_an_empty_proposal_cannot_also_name_members(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """The flag asserts something about the call, so a false assertion refuses.

    Ignoring it instead would let one of the two statements win silently, and
    the caller would learn which only from the version it got.
    """
    _ready(registry, tmp_path)
    stable_id = _released(registry, "H")

    with pytest.raises(CliFailure) as raised:
        select.propose(
            {
                "harness": "claude-code",
                "project": str(tmp_path),
                "member": [f"{stable_id}@1.0"],
                "empty": True,
            }
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.details["members"] == "1"


def test_a_named_empty_setup_is_proposed_confirmed_and_immutable(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`REQ-630` end to end: the emptiness is named, the freeze is still decided.

    `--empty` says zero members is the composition; naming the proposal to
    `select confirm` says freeze this exact one. Neither implies the other.
    """
    _ready(registry, tmp_path)

    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "empty": True}
    ).payload
    assert len(session.proposals) == 1
    assert session.proposals[0].members == []

    proposal_id = session.proposals[0].proposal_id
    confirmed = select.confirm({"proposal": proposal_id}).payload
    assert confirmed.created
    assert confirmed.state == "pending_install"

    again = select.confirm({"proposal": proposal_id}).payload
    assert (again.stable_id, again.version) == (confirmed.stable_id, confirmed.version)
    assert not again.created, "an empty version is as immutable as any other"

    compiled = select.compile_harness_bundle(registry, proposal_id, "claude-code")
    assert compiled.compiled
    assert compiled.files == ()
    conversion = compiled.manifest["conversion_report"]
    assert isinstance(conversion, dict)
    assert conversion["complete"] is True
    assert conversion["entries"] == []

    from ai_stp_cli.commands import install

    prepared = install._prepared_setup_source(  # pyright: ignore[reportPrivateUsage]
        registry, f"{confirmed.stable_id}@{confirmed.version}", str(tmp_path)
    )
    assert prepared.members == ()
    assert prepared.harness_id == "claude-code"


def test_a_resolved_component_with_no_digest_refuses_instead_of_vanishing(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The closure named it, the report chose it, and the writer dropped it.

    `_bundle_sources` skipped a resolved component whose passport carries no
    artifact digest, so the bundle compiled as though that member had never been
    part of the graph. Same shape as the sibling artifacts of `#438`: a package
    silently weaker than the passport describing it, with every downstream
    report — composition `chosen`, the plan's file count, the provider's
    verified answer — still true about what it was handed.

    Zero components stays a real graph (`ADR-0124`, `REQ-630`). A *present* node
    without bytes is not emptiness, and that is the distinction asserted here.
    """
    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "review.md")
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    select.confirm({"proposal": session.proposals[0].proposal_id})

    real = revisions.get

    def without_digest(
        connection: sqlite3.Connection, revision_id: str
    ) -> revisions.StoredRevision | None:
        stored = real(connection, revision_id)
        if stored is None or stored.stable_id != stable_id:
            return stored
        document: dict[str, Any] = stored.envelope.model_dump(mode="json")
        document.pop("artifact", None)
        facts: object = document.get("facts")
        if isinstance(facts, dict):
            cast(dict[str, Any], facts).pop("content_digest", None)
        return replace(stored, envelope=type(stored.envelope).model_validate(document))

    monkeypatch.setattr(revisions, "get", without_digest)

    with pytest.raises(CliFailure) as raised:
        select.harness_bundle(
            {
                "harness": "claude-code",
                "project": str(tmp_path),
                "proposal": session.proposals[0].proposal_id,
            }
        )
    assert raised.value.code == "AI_STP_CONFLICT"
    assert "digest" in raised.value.message
    assert raised.value.details.get("stable_id") == stable_id


def test_a_component_needing_an_unset_variable_still_compiles(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """The process environment is not the composition's declaration.

    `_composition_target` passed `frozenset(os.environ)` as `declared_env`, so
    `_environment` — whose own docstring says it is about the *composition*
    declaring what it needs and explicitly not about a value being present —
    became "is this variable exported in the shell that ran the CLI". A
    component declaring `required_env` for a key nobody had exported blocked the
    bundle with `undeclared_environment`, and any `external_endpoints` blocked
    unconditionally because endpoints were never declared at all.

    A missing value is an advisory at install time (`REQ-111`, `REQ-816`) and a
    note at eligibility. It is not a reason to refuse to build a package.
    """
    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "review.md")

    # State the need on the passport the composition reads.
    stored = revisions.head(registry, stable_id)
    assert stored is not None
    component_passports.update(
        registry,
        stable_id,
        stored.revision_id,
        ComponentPassportPatch(
            required_env=[
                EnvVarRequirement(
                    name="AI_STP_NOT_EXPORTED_ANYWHERE", purpose="a key nobody exported"
                )
            ],
            external_endpoints=["https://api.example.test"],
        ),
        device_id=DEVICE,
    )
    from ai_stp_cli.commands import component as command

    command.version_release({"id": stable_id, "version": "1.1"})

    assert "AI_STP_NOT_EXPORTED_ANYWHERE" not in os.environ
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.1"]}
    ).payload
    select.confirm({"proposal": session.proposals[0].proposal_id})

    compiled = select.harness_bundle(
        {
            "harness": "claude-code",
            "project": str(tmp_path),
            "proposal": session.proposals[0].proposal_id,
        }
    ).payload
    assert compiled.compiled


def test_an_adopted_command_records_the_native_identity_discovery_found(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`native_id_collision` existed and the ordinary path could never reach it.

    `composition._identities` refuses two components claiming one native
    identifier, `_surfaces` reads `native_ids` from the passport, and authoring
    scaffolds it — but adoption never recorded it. `ADOPTED_FIELDS` carried
    `source_name` and `entry_points` and stopped there, so
    adopt → version → propose → bundle produced passports whose `native_ids`
    were always empty and the conflict was unreachable outside fixtures.

    Nothing is invented: the identifier is the `source_name` discovery already
    determined, recorded only for the kinds whose contract has one
    (`component_passports._ACTION_SURFACES`). A skill gets none, and
    `permissions` and `precedence` stay absent — undeclared stays undeclared.
    """
    from ai_stp_cli.commands import component as command

    _ready(registry, tmp_path)
    commands = tmp_path / ".claude" / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    (commands / "review.md").write_text("# review\n", encoding="utf-8")
    identified = command.adopt(
        {"path": str(commands / "review.md"), "root": str(tmp_path)}
    ).payload.stable_id

    assert _document_list(registry, identified, "native_ids") == ["review.md"]

    skill = _adopted(registry, tmp_path, "helper.md")
    assert _document_list(registry, skill, "native_ids") == []


def _document_list(connection: sqlite3.Connection, stable_id: str, key: str) -> list[str]:
    """One list of strings from a head passport, wherever the field is recorded."""
    stored = revisions.head(connection, stable_id)
    assert stored is not None
    document: dict[str, Any] = stored.envelope.model_dump(mode="json")
    holders: list[dict[str, Any]] = [document]
    facts: object = document.get("facts")
    if isinstance(facts, dict):
        holders.append(cast(dict[str, Any], facts))
    for holder in holders:
        value: object = holder.get(key)
        if isinstance(value, dict):
            value = cast(dict[str, Any], value).get("value")
        if isinstance(value, list):
            return [str(item) for item in cast(list[object], value)]
    return []


def test_a_named_version_is_assessed_by_its_own_declared_facts(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Live eligibility read three fields and the mutable head.

    `_candidates` copied `harness_id`, `component_type` and `owner_id` from
    `revisions.head` and nothing else, so `os_unsupported`, `arch_unsupported`,
    `capability_*`, `license_undeclared` and the rest of `SPEC-006` `REQ-601`
    could not fire on the live path at all — the families were implemented,
    covered by their own unit tests, and unreachable from `select propose`.
    It also assessed the entity head rather than the exact `X.Y` being proposed,
    so a member could be admitted on facts belonging to a different version.

    `owned_or_pinned` stays true for adopted local objects (`ADR-0016`): this is
    the user's own work and it needs no grant and no licence. What changes is
    that the mechanical constraints now see what the version declares.
    """
    _ready(registry, tmp_path)
    stable_id = _adopted(registry, tmp_path, "review.md")

    stored = revisions.head(registry, stable_id)
    assert stored is not None
    component_passports.update(
        registry,
        stable_id,
        stored.revision_id,
        ComponentPassportPatch(supported_os=["linux" if os.name == "nt" else "windows"]),
        device_id=DEVICE,
    )
    from ai_stp_cli.commands import component as command

    command.version_release({"id": stable_id, "version": "1.1"})

    with pytest.raises(CliFailure) as raised:
        select.propose(
            {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.1"]}
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "os_unsupported" in str(raised.value.details.get("refusals"))

    # The version that declares nothing about the operating system still proposes.
    session = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    assert session.proposals


# --- durable consent at eligibility (#447) --------------------------------


def _acquired(connection: sqlite3.Connection, suffix: str, **facts: str) -> str:
    """An object the catalogue handed over: somebody else's, and unverified.

    This is the only shape that reaches the `experimental` lane, and until the
    first half of `#447` nothing could: `_candidates` claimed `owned_or_pinned`
    for every local row, so an acquired object was treated as the user's own.
    """
    stable_id = f"component_01J0000000000000000000000{suffix}"
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, MOMENT),
    )
    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": "account_01J00000000000000000000FAR",
        "version": "1.0",
        "created_at": MOMENT,
        "visibility": "public",
        "parent_revision_ids": [],
        "license_id": "MIT",
        "facts": {
            name: {
                "value": value,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            }
            for name, value in (
                ("harness_id", "claude-code"),
                ("component_type", "skill"),
                *facts.items(),
            )
        },
    }
    revisions.commit(connection, document, device_id=DEVICE)
    acquired_trust.record(
        connection,
        stable_id=stable_id,
        version="1.0",
        passport_digest="sha256:" + "0" * 64,
        verdict=acquired_trust.Verdict(
            trust_lane="experimental", author_verified=False, component_verified=False
        ),
        at=MOMENT,
    )
    connection.commit()
    return stable_id


def _codes(report: EligibilityReport, stable_id: str) -> set[str]:
    for candidate in report.candidates:
        if candidate.stable_id == stable_id:
            return {refusal.code for refusal in candidate.refusals}
    raise AssertionError(f"{stable_id} is not in the report")


def test_an_acquired_object_without_consent_is_refused_by_name(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    stable_id = _acquired(registry, "C")
    assert "unverified_without_consent" in _codes(_report(tmp_path), stable_id)


def test_a_durable_consent_admits_an_acquired_object_without_making_it_automatic(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """The ticket's own proof: consent admits, and admits is not selects.

    `select propose` has no `--include-unverified` and read no records, so this
    refusal was unreachable by any means — a durable consent could be granted,
    listed, and had no effect on the one path it exists for.
    """
    stable_id = _acquired(registry, "D")
    consent.grant(
        registry,
        consent_id="request_01J00000000000000000000CNS",
        scope=consent.SCOPE_PUBLISHER,
        target="account_01J00000000000000000000FAR",
        fingerprint=consent.fingerprint_of({}),
        observed=(stable_id,),
        decided_by=owner().account_id,
        origin="component consent allow",
        at=MOMENT,
    )
    registry.commit()

    report = _report(tmp_path)
    assert "unverified_without_consent" not in _codes(report, stable_id)
    only = next(item for item in report.candidates if item.stable_id == stable_id)
    assert only.lane == "experimental"
    # Consent never promotes: `ADR-0016` keeps an experimental candidate out of
    # automatic selection whatever the user agreed to.
    assert not only.auto_selectable


def test_a_permission_grown_since_the_consent_is_refused_and_the_field_named(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    stable_id = _acquired(registry, "F", network_permissions="collect.elsewhere.test")
    consent.grant(
        registry,
        consent_id="request_01J00000000000000000000GRW",
        scope=consent.SCOPE_PUBLISHER,
        target="account_01J00000000000000000000FAR",
        # The shape agreed to had no network permission; the object now asks
        # for one. That is the contract's revoking event, by name.
        fingerprint=consent.fingerprint_of({}),
        observed=(stable_id,),
        decided_by=owner().account_id,
        origin="component consent allow",
        at=MOMENT,
    )
    registry.commit()
    assert "unverified_without_consent" in _codes(_report(tmp_path), stable_id)


def test_the_matrix_accepts_the_empty_tuple_click_delivers_for_no_harness(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`#384`'s lesson, missed here: a repeatable option omitted is `()`, not None.

    Measured through the real CLI: `select eligibility-matrix` without
    `--harness` — the exact invocation the all-harness matrix exists for —
    refused with "a supported harness identifier is required", because the
    handler tested `is None` while Click delivers an empty tuple. The direct
    calls in this file passed no key at all, so the pair agreed with each
    other and with nothing else.
    """
    _register(registry, "T", harness_id="claude-code")

    matrix = _matrix(tmp_path, **{"harness": ()})

    assert [report.harness_id for report in matrix.harnesses] == sorted(HARNESS_IDS)


def test_a_project_stable_id_where_a_root_belongs_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--project` is a directory here and a stable id in `target`. Same flag, two types.

    Measured in the functional sweep of 2026-09-02. `select session --project
    project_01M1F6BZ… --harness claude-code` answered:

        AI_STP_PRECONDITION_FAILED
        "this project has no passport, so there is nothing to compose against"
        details.root: /home/…/ai-stp/project_01M1F6BZ…
        next_actions: ["project passport --root project_01M1F6BZ… --json"]

    Three wrongs from one missing check. `Path(value)` turned an identifier into
    a relative path and `.resolve()` anchored it to the working directory, so the
    refusal named a directory nobody mentioned and that never existed; and the
    next action echoed the same unusable value into a command that fails
    identically — a pointer the `next_actions` lint passes, because the command
    and its flags are real and only the argument cannot work.

    The confusion is not exotic: `target status --project` genuinely takes a
    stable id, and an agent building argv from machine help meets the same word
    twice with two meanings.
    """
    from ai_stp_cli.commands import select as command

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    with pytest.raises(CliFailure) as refused:
        command.session({"harness": "claude-code", "project": "project_01M1F6BZ0AP7K6CHGBPGJ7JCTR"})
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"
    assert "directory" in refused.value.message
    # The invented path must not appear anywhere in the answer.
    assert "project_01M1F6BZ0AP7K6CHGBPGJ7JCTR" not in str(refused.value.details.get("root", ""))
    assert all(
        "project_01M1F6BZ0AP7K6CHGBPGJ7JCTR" not in action for action in refused.value.next_actions
    )

    # A directory that exists but holds no passport keeps the old, correct answer.
    real = tmp_path / "work"
    real.mkdir()
    with pytest.raises(CliFailure) as absent:
        command.session({"harness": "claude-code", "project": str(real)})
    assert absent.value.code == "AI_STP_PRECONDITION_FAILED"


def test_propose_names_the_proposal_it_recorded_among_the_open_ones(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Several proposals may be open for one pair; the answer says which is new.

    Measured in a functional sweep: `select propose` answered with the whole
    session, the caller took the first row, confirmed an older empty proposal
    and installed nothing. `proposal_id` is the one this call recorded;
    `select session`, which records none, leaves it empty.
    """
    _ready(registry, tmp_path)
    first = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "empty": True}
    ).payload
    second = select.propose(
        {"harness": "claude-code", "project": str(tmp_path), "empty": True}
    ).payload

    assert first.proposal_id == first.proposals[0].proposal_id
    assert second.proposal_id is not None
    assert second.proposal_id != first.proposal_id
    assert second.proposal_id in {item.proposal_id for item in second.proposals}
    assert len(second.proposals) == 2

    session = select.session({"harness": "claude-code", "project": str(tmp_path)}).payload
    assert session.proposal_id is None


def test_bundle_takes_the_target_a_contribution_needs(tmp_path: Path) -> None:
    """`select bundle --target` is the same shape `install plan --target` accepts.

    A composition holding a contribution to a provider-owned file could be
    planned and installed but never bundled on its own, because `install plan`
    took a target and `select bundle` declared none.
    """
    target = tmp_path / "target"
    target.mkdir()
    assert select._bundle_host_root({}) is None  # pyright: ignore[reportPrivateUsage]
    assert select._bundle_host_root({"target": str(target)}) == target.resolve()  # pyright: ignore[reportPrivateUsage]

    link = tmp_path / "link"
    link.symlink_to(target)
    for given in ("relative/place", str(tmp_path / "absent"), str(link)):
        with pytest.raises(CliFailure) as raised:
            select._bundle_host_root({"target": given})  # pyright: ignore[reportPrivateUsage]
        assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_bundle_compiled_for_a_workspace_lands_on_workspace_surfaces(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`REQ-632`: the scope is chosen at compile time, and the paths follow it.

    The same confirmed composition compiles twice: once for cursor's home,
    where rules live under `rules/`, and once for a workspace, where the
    provider's 0.0.54 declaration puts them under `.cursor/rules`. Only the
    workspace manifest names its scope, so the home bundle's digest is the one
    it always was.
    """
    from ai_stp_cli.commands import component as command

    _ready(registry, tmp_path)
    place = tmp_path / ".cursor" / "rules"
    place.mkdir(parents=True)
    (place / "review.mdc").write_text("# review\n", encoding="utf-8")
    stable_id = command.adopt(
        {"path": str(place / "review.mdc"), "root": str(tmp_path)}
    ).payload.stable_id
    _complete_adopted(registry, stable_id, "review.mdc")
    command.version_release({"id": stable_id})
    session = select.propose(
        {"harness": "cursor", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    proposal = session.proposal_id
    assert proposal is not None
    select.confirm({"proposal": proposal})

    with pytest.raises(CliFailure) as unavailable:
        select.harness_bundle({"harness": "cursor", "project": str(tmp_path), "proposal": proposal})
    assert unavailable.value.code == "AI_STP_PRECONDITION_FAILED"
    workspace = select.harness_bundle(
        {"harness": "cursor", "project": str(tmp_path), "proposal": proposal, "scope": "project"}
    ).payload
    assert [item.path for item in workspace.files] == [".cursor/rules/review.mdc"]
    assert workspace.target_scope == "project"
    scoped = select.compile_harness_bundle(registry, proposal, "cursor", scope="project")
    assert scoped.manifest["target_scope"] == "project"


def _contributed(registry: sqlite3.Connection, tmp_path: Path) -> tuple[str, str]:
    """One `mcp` component adopted from codex's owned `config.toml`, proposed and confirmed."""
    import os

    from ai_stp_cli.commands import component as command
    from ai_stp_cli.local import harnesses

    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "codex")
    place = harnesses.config_root(detector, dict(os.environ)) / "config.toml"
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_text(
        '[mcp_servers.mcp01]\ncommand = "mcp01-server"\nargs = ["--stdio"]\n', encoding="utf-8"
    )
    stable_id = command.adopt(
        {"path": str(place), "kind": "mcp", "harness": "codex"}
    ).payload.stable_id
    _complete_adopted(registry, stable_id, "mcp01")
    command.version_release({"id": stable_id})
    session = select.propose(
        {"harness": "codex", "project": str(tmp_path), "member": [f"{stable_id}@1.0"]}
    ).payload
    assert session.proposal_id is not None
    confirmed = select.confirm({"proposal": session.proposal_id}).payload
    return confirmed.stable_id, confirmed.version


def test_a_withdrawal_bundle_keeps_what_the_person_wrote_beside_the_contribution(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """`ADR-0129`'s removal half, on the bytes the target holds.

    The host file the contribution landed in keeps the person's own key and
    comment, and loses exactly the contributed table; the bundle names that
    file as the one member whose bytes survive.
    """
    _ready(registry, tmp_path)
    stable_id, version = _contributed(registry, tmp_path)
    host_root = tmp_path / "target"
    host_root.mkdir()
    (host_root / "config.toml").write_text(
        '# kept by the person\nmodel = "sibling"\n\n'
        '[mcp_servers.mcp01]\ncommand = "mcp01-server"\nargs = ["--stdio"]\n',
        encoding="utf-8",
    )
    with closing(open_readonly(configured_path())) as connection:
        compiled = select.compile_withdrawal_bundle(
            connection, stable_id, version, expected_harness="codex", host_root=host_root
        )
    assert compiled is not None
    assert [item.path for item in compiled.files] == ["config.toml"]
    with zipfile.ZipFile(io.BytesIO(compiled.archive), "r") as archive:
        survived = archive.read("files/config.toml")
    assert b"# kept by the person" in survived
    assert b'model = "sibling"' in survived
    assert b"mcp01" not in survived
    assert compiled.files[0].byte_length == len(survived)
    assert compiled.manifest.get("target_scope") in (None, "global")


def test_a_host_that_would_end_empty_is_not_packed(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    """Nothing survives: the removal goes whole and no bundle says otherwise."""
    _ready(registry, tmp_path)
    stable_id, version = _contributed(registry, tmp_path)
    host_root = tmp_path / "target"
    host_root.mkdir()
    (host_root / "config.toml").write_text(
        '[mcp_servers.mcp01]\ncommand = "mcp01-server"\nargs = ["--stdio"]\n', encoding="utf-8"
    )
    with closing(open_readonly(configured_path())) as connection:
        assert (
            select.compile_withdrawal_bundle(
                connection, stable_id, version, expected_harness="codex", host_root=host_root
            )
            is None
        )
        # A host the target no longer holds has nothing to keep either.
        (host_root / "config.toml").unlink()
        assert (
            select.compile_withdrawal_bundle(
                connection, stable_id, version, expected_harness="codex", host_root=host_root
            )
            is None
        )
