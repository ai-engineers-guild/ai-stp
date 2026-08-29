"""The daily lifecycle: four states told apart, and a rollback that walks back."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, revisions, targets, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.provider.status import AuthorizationEvidence
from ai_stp_foundation.canonical import JsonValue

PROJECT = "project_01J0000000000000000000000A"
HARNESS = "claude-code"
PAIR = f"{PROJECT}:{HARNESS}"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _survey(**overrides: object) -> targets.Survey:
    facts: dict[str, object] = {"project_id": PROJECT, "harness_id": HARNESS}
    facts.update(overrides)
    return targets.Survey(**facts)  # pyright: ignore[reportArgumentType]


def _verified(connection: sqlite3.Connection, version: str, *, digest: str, at: str) -> str:
    """One operation that a provider verified, as the log would record it."""
    plan = _installation_plan(connection, version, at=at)
    _finish_verified(connection, plan, digest=digest, at=at)
    return plan.operation_id


def _installation_plan(
    connection: sqlite3.Connection, version: str, *, at: str
) -> installation.Plan:
    plan = installation.propose(
        connection,
        action="install",
        author="account_x",
        target_id=PAIR,
        expected_target_digest="sha256:" + "0" * 64,
        provider_version="1.0.0",
        effects=("write something",),
        recovery_action="restore",
        idempotency_key=f"key-{version}",
        at=at,
        expires_at="2099-01-01T00:00:00.000Z",
        setup_stable_id="setup_01J0000000000000000000000B",
        setup_version=version,
    )
    return plan


def _finish_verified(
    connection: sqlite3.Connection,
    plan: installation.Plan,
    *,
    digest: str,
    at: str,
) -> None:
    installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=at)
    installation.begin(
        connection,
        plan.operation_id,
        observed_target_digest="sha256:" + "0" * 64,
        at=at,
    )
    installation.applied(connection, plan.operation_id, at=at)
    installation.verify(
        connection,
        plan.operation_id,
        postconditions_met=True,
        at=at,
        observed_target_digest=digest,
    )


def _selected_setup(
    connection: sqlite3.Connection,
    *,
    required_env: tuple[str, ...] = ("OPENAI_API_KEY",),
    requires_authorization: str = "none",
    name: str = "readiness fixture",
    description: str = "An exact selected setup used by target status tests.",
) -> None:
    stable_id = "setup_01J0000000000000000000000C"
    for entity, kind in ((PROJECT, "project"), (stable_id, "setup")):
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
            (entity, kind, "2026-08-08T10:00:00.000Z"),
        )
    passport: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": stable_id,
        "owner_id": "account_01J0000000000000000000000D",
        "created_at": "2026-08-08T10:00:00.000Z",
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {},
        "name": name,
        "description": description,
        "version": "1.0",
        "tags": ["tests"],
        "source": None,
        "artifact": {"digest": "sha256:" + "a" * 64, "size_bytes": 1},
        "harness_id": HARNESS,
        "required_env": [
            {"name": name, "purpose": "Required by the readiness fixture."} for name in required_env
        ],
        "requires_authorization": requires_authorization,
        "license": {"spdx_id": "MIT", "redistribution_allowed": False},
        "purpose": "Exercise authoritative readiness requirements.",
        "target_role": "tests",
        "components": [
            {
                "stable_id": "component_01J0000000000000000000000D",
                "version": "1.0",
                "passport_digest": "sha256:" + "b" * 64,
            }
        ],
    }
    stored = revisions.commit(connection, passport, device_id="device_test")
    recorded = versions.record(
        connection,
        stable_id=stable_id,
        version="1.0",
        passport_digest=cache.digest_of(stored.envelope.model_dump(mode="json")),
        revision_id=stored.revision_id,
        at="2026-08-08T10:00:00.000Z",
    )
    connection.execute(
        """
        INSERT INTO selected_version
            (project_id, harness_id, stable_id, version, state, selected_at)
        VALUES (?, ?, ?, ?, 'pending_install', ?)
        """,
        (PROJECT, HARNESS, stable_id, recorded.version, "2026-08-08T10:00:00.000Z"),
    )


# The four states `#177` names, told apart.
def test_a_pair_with_nothing_chosen_says_so() -> None:
    """An empty list of states reads as "no problems", which is a different thing."""
    assert _survey().states == (targets.STATE_NOT_SELECTED,)


def test_a_selected_version_that_is_not_installed_is_pending() -> None:
    assert _survey(selected_version="1.0").states == (targets.STATE_PENDING_INSTALL,)


def test_another_setup_with_the_same_version_is_pending() -> None:
    found = _survey(
        selected_stable_id="setup_new",
        selected_version="1.0",
        installed_stable_id="setup_old",
        installed_version="1.0",
    )
    assert found.states == (targets.STATE_PENDING_INSTALL,)
    assert targets.pending_changes(found) == ("setup: setup_old -> setup_new",)


def test_a_target_that_moved_under_us_is_local_drift() -> None:
    found = _survey(
        selected_version="1.0",
        installed_version="1.0",
        verified_target_digest="sha256:" + "a" * 64,
        observed_target_digest="sha256:" + "b" * 64,
    )
    assert found.states == (targets.STATE_LOCAL_DRIFT,)


def test_a_newer_version_in_the_catalogue_is_catalog_drift() -> None:
    found = _survey(selected_version="1.0", installed_version="1.0", catalog_version="1.1")
    assert found.states == (targets.STATE_CATALOG_DRIFT,)


def test_an_older_catalogue_version_is_not_drift_or_a_pending_change() -> None:
    found = _survey(selected_version="2.0", installed_version="2.0", catalog_version="1.9")
    assert found.states == (targets.STATE_INSTALLED,)
    assert targets.pending_changes(found) == ()


def test_catalogue_versions_are_compared_as_two_numbers() -> None:
    found = _survey(selected_version="1.9", installed_version="1.9", catalog_version="1.10")
    assert found.states == (targets.STATE_CATALOG_DRIFT,)
    assert targets.pending_changes(found) == ("catalogue has 1.10, selected is 1.9",)


def test_a_noncanonical_catalogue_version_is_a_typed_input_error() -> None:
    found = _survey(selected_version="1.0", installed_version="1.0", catalog_version="v2")
    with pytest.raises(CliFailure) as raised:
        _ = found.states
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


@pytest.mark.parametrize(
    "missing", [{"missing_env": ("OPENAI_API_KEY",)}, {"pending_authorization": "external_service"}]
)
def test_anything_still_to_configure_is_needs_configuration(missing: dict[str, object]) -> None:
    found = _survey(selected_version="1.0", installed_version="1.0", **missing)
    assert found.states == (targets.STATE_NEEDS_CONFIGURATION,)


def test_a_settled_pair_says_installed() -> None:
    found = _survey(
        selected_version="1.0",
        installed_version="1.0",
        verified_target_digest="sha256:" + "a" * 64,
        observed_target_digest="sha256:" + "a" * 64,
        catalog_version="1.0",
    )
    assert found.states == (targets.STATE_INSTALLED,)


def test_every_applicable_state_comes_back_not_the_first() -> None:
    """Answering with one would send somebody to fix a thing and meet the next."""
    found = _survey(
        selected_version="1.1",
        installed_version="1.0",
        verified_target_digest="sha256:" + "a" * 64,
        observed_target_digest="sha256:" + "b" * 64,
        catalog_version="1.2",
        missing_env=("OPENAI_API_KEY",),
    )
    assert found.states == (
        targets.STATE_PENDING_INSTALL,
        targets.STATE_LOCAL_DRIFT,
        targets.STATE_CATALOG_DRIFT,
        targets.STATE_NEEDS_CONFIGURATION,
    )


def test_every_declared_state_is_reachable() -> None:
    """A state nothing can produce is a state nobody has to handle."""
    seen = {
        _survey().states[0],
        _survey(selected_version="1.0").states[0],
        _survey(
            selected_version="1.0",
            installed_version="1.0",
            verified_target_digest="a",
            observed_target_digest="b",
        ).states[0],
        _survey(selected_version="1.0", installed_version="1.0", catalog_version="1.1").states[0],
        _survey(selected_version="1.0", installed_version="1.0", missing_env=("X",)).states[0],
        _survey(selected_version="1.0", installed_version="1.0").states[0],
    }
    assert seen == targets.STATES


def test_an_unknown_catalogue_is_not_the_same_as_nothing_newer() -> None:
    """Empty means nobody asked; it must not read as "you are up to date"."""
    found = _survey(selected_version="1.0", installed_version="1.0", catalog_version="")
    assert targets.STATE_CATALOG_DRIFT not in found.states
    assert found.catalog_version == ""


def test_drift_needs_both_digests_to_be_expressible() -> None:
    """One of them alone cannot say whether anything moved."""
    only_verified = _survey(
        selected_version="1.0", installed_version="1.0", verified_target_digest="a"
    )
    assert targets.STATE_LOCAL_DRIFT not in only_verified.states


# The history, read from the operation log.
def test_only_verified_operations_count_as_installed(registry: sqlite3.Connection) -> None:
    _verified(registry, "1.0", digest="sha256:" + "a" * 64, at="2026-08-08T10:00:00.000Z")

    plan = installation.propose(
        registry,
        action="install",
        author="account_x",
        target_id=PAIR,
        expected_target_digest="sha256:" + "0" * 64,
        provider_version="1.0.0",
        effects=("write",),
        recovery_action="restore",
        idempotency_key="unfinished",
        at="2026-08-08T11:00:00.000Z",
        expires_at="2099-01-01T00:00:00.000Z",
        setup_stable_id="setup_01J0000000000000000000000B",
        setup_version="2.0",
    )
    installation.approve(
        registry, plan.operation_id, plan_digest=plan.digest, at="2026-08-08T11:00:00.000Z"
    )

    history = targets.verified(registry, project_id=PROJECT, harness_id=HARNESS)
    assert [item.setup_version for item in history] == ["1.0"]


def test_the_survey_reads_the_last_verified_version(registry: sqlite3.Connection) -> None:
    _verified(registry, "1.0", digest="sha256:" + "a" * 64, at="2026-08-08T10:00:00.000Z")
    _verified(registry, "1.1", digest="sha256:" + "b" * 64, at="2026-08-08T11:00:00.000Z")

    found = targets.survey(registry, project_id=PROJECT, harness_id=HARNESS)
    assert found.installed_version == "1.1"
    assert found.verified_target_digest == "sha256:" + "b" * 64


def test_survey_reads_required_environment_from_the_exact_selected_setup(
    registry: sqlite3.Connection,
) -> None:
    _selected_setup(registry)

    missing = targets.survey(registry, project_id=PROJECT, harness_id=HARNESS)
    configured = targets.survey(
        registry,
        project_id=PROJECT,
        harness_id=HARNESS,
        present_env=frozenset({"OPENAI_API_KEY"}),
    )

    assert missing.missing_env == ("OPENAI_API_KEY",)
    assert targets.STATE_NEEDS_CONFIGURATION in missing.states
    assert configured.missing_env == ()


def test_cli_environment_requirements_can_only_extend_the_selected_passport(
    registry: sqlite3.Connection,
) -> None:
    _selected_setup(registry)

    found = targets.survey(
        registry,
        project_id=PROJECT,
        harness_id=HARNESS,
        present_env=frozenset({"OPENAI_API_KEY"}),
        additional_required_env=("TARGET_ONLY_TOKEN",),
    )

    assert found.missing_env == ("TARGET_ONLY_TOKEN",)


def test_declared_authorization_stays_pending_without_provider_evidence(
    registry: sqlite3.Connection,
) -> None:
    _selected_setup(registry, required_env=(), requires_authorization="external_service")

    found = targets.survey(registry, project_id=PROJECT, harness_id=HARNESS)

    assert found.pending_authorization == "external_service"
    assert targets.STATE_NEEDS_CONFIGURATION in found.states


@pytest.mark.parametrize(
    ("state", "pending"),
    [("pending", "external_service"), ("ready", "")],
)
def test_only_matching_provider_evidence_can_clear_authorization(
    registry: sqlite3.Connection, state: str, pending: str
) -> None:
    _selected_setup(registry, required_env=(), requires_authorization="external_service")

    found = targets.survey(
        registry,
        project_id=PROJECT,
        harness_id=HARNESS,
        authorization_evidence=AuthorizationEvidence(kind="external_service", state=state),
    )

    assert found.pending_authorization == pending


def test_mismatched_provider_authorization_evidence_fails_closed(
    registry: sqlite3.Connection,
) -> None:
    _selected_setup(registry, required_env=(), requires_authorization="external_service")

    with pytest.raises(CliFailure) as raised:
        targets.survey(
            registry,
            project_id=PROJECT,
            harness_id=HARNESS,
            authorization_evidence=AuthorizationEvidence(kind="user_account", state="ready"),
        )

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_survey_fails_closed_when_the_selected_exact_version_is_missing(
    registry: sqlite3.Connection,
) -> None:
    for entity, kind in (
        (PROJECT, "project"),
        ("setup_01J0000000000000000000000C", "setup"),
    ):
        registry.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
            (entity, kind, "2026-08-08T10:00:00.000Z"),
        )
    registry.execute(
        """
        INSERT INTO selected_version
            (project_id, harness_id, stable_id, version, state, selected_at)
        VALUES (?, ?, ?, '1.0', 'pending_install', ?)
        """,
        (
            PROJECT,
            HARNESS,
            "setup_01J0000000000000000000000C",
            "2026-08-08T10:00:00.000Z",
        ),
    )

    with pytest.raises(CliFailure) as raised:
        targets.survey(registry, project_id=PROJECT, harness_id=HARNESS)
    assert raised.value.code == "AI_STP_INTERNAL"


def test_equal_timestamps_follow_verification_order_not_operation_creation(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback order comes from serialized terminal events, not a clock tie."""
    identifiers = iter(("operation_a", "operation_z"))

    def fixed_id(_kind: str) -> str:
        return next(identifiers)

    monkeypatch.setattr(installation, "new_id", fixed_id)
    at = "2026-08-08T10:00:00.000Z"
    created_first = _installation_plan(registry, "1.0", at=at)
    created_second = _installation_plan(registry, "2.0", at=at)

    _finish_verified(registry, created_second, digest="sha256:" + "b" * 64, at=at)
    _finish_verified(registry, created_first, digest="sha256:" + "a" * 64, at=at)

    history = targets.verified(registry, project_id=PROJECT, harness_id=HARNESS)
    assert [item.setup_version for item in history] == ["2.0", "1.0"]
    assert (
        targets.rollback_target(registry, project_id=PROJECT, harness_id=HARNESS).setup_version
        == "2.0"
    )


def test_a_pair_with_no_history_has_none(registry: sqlite3.Connection) -> None:
    assert targets.verified(registry, project_id=PROJECT, harness_id=HARNESS) == ()


# Rollback names the exact previous version.
def test_rollback_names_the_version_before_the_current(registry: sqlite3.Connection) -> None:
    _verified(registry, "1.0", digest="sha256:" + "a" * 64, at="2026-08-08T10:00:00.000Z")
    _verified(registry, "1.1", digest="sha256:" + "b" * 64, at="2026-08-08T11:00:00.000Z")
    _verified(registry, "1.2", digest="sha256:" + "c" * 64, at="2026-08-08T12:00:00.000Z")

    previous = targets.rollback_target(registry, project_id=PROJECT, harness_id=HARNESS)
    assert previous.setup_version == "1.1"


def test_rollback_targets_the_immediately_previous_verified_event(
    registry: sqlite3.Connection,
) -> None:
    """Undoing a rollback may raise a version; history order remains the truth."""
    _verified(registry, "1.0", digest="sha256:" + "a" * 64, at="2026-08-08T10:00:00.000Z")
    _verified(registry, "1.2", digest="sha256:" + "c" * 64, at="2026-08-08T11:00:00.000Z")
    _verified(registry, "1.1", digest="sha256:" + "b" * 64, at="2026-08-08T12:00:00.000Z")

    previous = targets.rollback_target(registry, project_id=PROJECT, harness_id=HARNESS)
    assert previous.setup_version == "1.2", "the state verified immediately before the current"


def test_rollback_refuses_when_there_is_nothing_to_go_back_to(
    registry: sqlite3.Connection,
) -> None:
    _verified(registry, "1.0", digest="sha256:" + "a" * 64, at="2026-08-08T10:00:00.000Z")
    with pytest.raises(CliFailure) as raised:
        targets.rollback_target(registry, project_id=PROJECT, harness_id=HARNESS)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_rollback_on_an_untouched_pair_refuses(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure) as raised:
        targets.rollback_target(registry, project_id=PROJECT, harness_id=HARNESS)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


# The diff: what installing the selection would change.
def test_a_diff_names_what_would_change() -> None:
    found = _survey(
        selected_version="1.1",
        selected_stable_id="setup_b",
        installed_version="1.0",
        installed_stable_id="setup_a",
        catalog_version="1.2",
    )
    changes = targets.pending_changes(found)
    assert any("version: 1.0 -> 1.1" in item for item in changes)
    assert any("setup: setup_a -> setup_b" in item for item in changes)
    assert any("catalogue has 1.2" in item for item in changes)


def test_a_diff_names_each_thing_still_to_configure() -> None:
    found = _survey(selected_version="1.0", installed_version="1.0", missing_env=("A", "B"))
    changes = targets.pending_changes(found)
    assert "must be configured: A" in changes
    assert "must be configured: B" in changes


def test_a_diff_names_drift_as_drift_rather_than_as_work_to_do() -> None:
    """`REQ-818` forbids fixing it, so it must not read like a pending change."""
    found = _survey(
        selected_version="1.0",
        installed_version="1.0",
        verified_target_digest="sha256:" + "a" * 64,
        observed_target_digest="sha256:" + "b" * 64,
    )
    changes = targets.pending_changes(found)
    assert any("outside the provider" in item for item in changes)


def test_a_settled_pair_has_nothing_pending() -> None:
    found = _survey(
        selected_version="1.0",
        selected_stable_id="setup_a",
        installed_version="1.0",
        installed_stable_id="setup_a",
        verified_target_digest="sha256:" + "a" * 64,
        observed_target_digest="sha256:" + "a" * 64,
        catalog_version="1.0",
    )
    assert targets.pending_changes(found) == ()


def test_nothing_here_installs_anything() -> None:
    """`#177`: there is no automatic update, so there is nothing here that could."""
    from pathlib import Path

    source = Path("apps/cli/src/ai_stp_cli/local/targets.py").read_text("utf-8")
    # Call shapes, not words: a bare "subprocess" also matches the docstring
    # explaining why there is no subprocess here.
    for call in (
        "installation.begin(",
        "installation.applied(",
        "installation.propose(",
        "import subprocess",
        "subprocess.run(",
    ):
        assert call not in source


def _backed_up(
    connection: sqlite3.Connection,
    *,
    ref: str,
    version: str,
    at: str,
    settle: bool = True,
) -> str:
    """One `backup` operation that left a provider-owned copy behind."""
    plan = installation.propose(
        connection,
        action="backup",
        author="account_x",
        target_id=PAIR,
        expected_target_digest="sha256:" + "0" * 64,
        provider_version="1.0.0",
        effects=("copy the target",),
        recovery_action="restore",
        idempotency_key=f"backup-{ref}",
        at=at,
        expires_at="2099-01-01T00:00:00.000Z",
        setup_stable_id="setup_01J0000000000000000000000B",
        setup_version=version,
    )
    installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=at)
    installation.begin(
        connection,
        plan.operation_id,
        observed_target_digest="sha256:" + "0" * 64,
        at=at,
    )
    installation.applied(connection, plan.operation_id, at=at, backup_ref=ref)
    if settle:
        installation.verify(
            connection,
            plan.operation_id,
            postconditions_met=True,
            at=at,
            observed_target_digest="sha256:" + "1" * 64,
        )
    return plan.operation_id


def test_a_target_with_no_copies_says_so_rather_than_failing(
    registry: sqlite3.Connection,
) -> None:
    """Nothing to restore from is an answer, not a refusal.

    An agent asking "what can I go back to" before taking a copy is asking a
    reasonable question, and an error there would read as a broken command.
    """
    assert targets.backups(registry, project_id=PROJECT, harness_id=HARNESS) == ()


def test_every_copy_of_this_pair_comes_back_oldest_first(registry: sqlite3.Connection) -> None:
    """The order is the durable local one, as it is for verified versions.

    Millisecond timestamps tie and `operation_id` orders creation rather than
    completion, so neither is the order a reader wants.
    """
    _backed_up(registry, ref="provider:backup:one", version="1.0", at="2026-08-08T10:00:00.000Z")
    _backed_up(registry, ref="provider:backup:two", version="1.1", at="2026-08-08T10:00:00.000Z")

    found = targets.backups(registry, project_id=PROJECT, harness_id=HARNESS)

    assert [item.backup_ref for item in found] == ["provider:backup:one", "provider:backup:two"]
    assert [item.setup_version for item in found] == ["1.0", "1.1"]
    assert all(item.operation_id for item in found)


def test_a_copy_from_an_operation_that_never_settled_is_not_offered(
    registry: sqlite3.Connection,
) -> None:
    """`install recover` owns that one, and it knows what may still be done.

    Listing it here would read as "restorable" without anything having said so.
    """
    _backed_up(
        registry,
        ref="provider:backup:unsettled",
        version="1.0",
        at="2026-08-08T10:00:00.000Z",
        settle=False,
    )

    assert targets.backups(registry, project_id=PROJECT, harness_id=HARNESS) == ()


def test_a_copy_of_another_pair_is_not_offered_for_this_one(
    registry: sqlite3.Connection,
) -> None:
    """A `BackupRef` belongs to the target it was taken from (`REQ-1209`)."""
    _backed_up(registry, ref="provider:backup:ours", version="1.0", at="2026-08-08T10:00:00.000Z")

    other = targets.backups(registry, project_id=PROJECT, harness_id="codex")

    assert other == ()
    assert len(targets.backups(registry, project_id=PROJECT, harness_id=HARNESS)) == 1


def test_an_installation_without_a_copy_is_not_listed_as_one(
    registry: sqlite3.Connection,
) -> None:
    """Only operations that actually left a reference behind.

    An ordinary install verifies and records no `backup_ref`; reading the log
    without that condition would offer every operation as a copy.
    """
    _verified(registry, "1.0", digest="sha256:" + "a" * 64, at="2026-08-08T10:00:00.000Z")

    assert targets.backups(registry, project_id=PROJECT, harness_id=HARNESS) == ()


def test_setup_requirements_carry_what_the_setup_says_about_itself(
    registry: sqlite3.Connection,
) -> None:
    """A plan enumerates files; only the description says what changing them means.

    Raised by the setup-systems session while settling posture import: their
    `full-auto` turns off a product's sandbox and its prompting, and 690
    characters of its description carry the qualifications — including that the
    sandbox key reaches nothing on native Windows. Measured here rather than
    assumed: the browse card clamps to two lines but cannot install from there,
    the detail page shows the whole text, and `install plan` — the surface that
    actually precedes an install, and the primary consumer — carried none of it.
    """
    _selected_setup(
        registry,
        name="Full auto",
        description=(
            "Full auto: nothing is asked, nothing is sandboxed. Note that the "
            "sandbox key reaches nothing on native Windows."
        ),
    )
    held = targets.setup_requirements(
        registry, stable_id="setup_01J0000000000000000000000C", version="1.0"
    )
    assert held.name == "Full auto"
    assert "nothing is sandboxed" in held.description
    # The qualification is the part that must survive, not just the headline: a
    # description truncated to its first clause reads as a stronger claim than
    # the one its author made.
    assert "native Windows" in held.description
