"""The four commands `#72` ships, exercised through their handlers."""

import json
import os
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli import runtime
from ai_stp_cli.commands import config_show, doctor, machine_help, version

# POSIX mode widening checks are skipped in production when os.name == "nt".
_POSIX = os.name != "nt"


def test_version_reports_the_build_and_both_contract_versions() -> None:
    report = version.run({}).payload
    assert report.cli_version
    assert report.wire_schema_version == 1
    assert report.python_version.count(".") == 2


def test_a_source_checkout_says_so_instead_of_inventing_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A made-up version is worse than an honest unknown: it is what a bug report
    # would quote.
    def missing(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(runtime, "package_version", missing)
    assert runtime.cli_version() == runtime.UNKNOWN_VERSION


def test_doctor_reports_a_fresh_installation_as_needing_action_not_as_broken() -> None:
    report = doctor.run({}).payload
    assert report.state == "needs_user_action"
    assert {check.name for check in report.checks} == {
        "python_runtime",
        "configuration",
        "local_registry",
        "catalog",
        "credential_store",
        "device_identity",
        "file_permissions",
        "interrupted_operations",
        "component_layouts",
        "composition_passports",
        "provider_binding",
    }


def test_doctor_names_the_composition_preconditions_without_narrowing_ready() -> None:
    """`REQ-1124`, and the reason `#356` was not patched the obvious way.

    `doctor` used to answer `ready` on an installation where `select propose`
    had just refused, and nothing in nine green checks named what would refuse.

    Turning the report `needs_user_action` was rejected: somebody who only
    searches and installs never needs either passport, so every fresh
    installation would report needing action and the summary word would stop
    carrying information for the callers who read only it.

    So the state stays `ready` and the detail carries the fact.
    """
    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "composition_passports")

    assert check.state == "ready", "an installation without passports is still sound"
    assert "passport developer init --json" in check.detail
    assert "passport device refresh --json" in check.detail


def test_doctor_names_the_tool_provider_binding_shells_out_to() -> None:
    """`provider fetch` runs `gh`, and nothing said so before the refusal.

    Installing a published setup goes through `provider fetch`, which binds an
    attested OpenNetwork release by running `gh attestation verify`. On a
    machine installed from PyPI there is no reason for `gh` to be present, and
    on one where it is present but has no usable `GH_CONFIG_DIR` the call fails
    too. The refusal itself is honest — `AI_STP_DEPENDENCY_UNAVAILABLE` with
    `dependency: gh` — but it arrives only after an agent has decided to
    install, and nothing in the diagnostic named it beforehand.

    Same shape as `composition_passports` and for the same reason: an
    installation without `gh` is still sound, and somebody who only searches the
    catalogue never needs it. So the state stays `ready` and the detail carries
    the fact, per `SPEC-011` `REQ-1124`.
    """
    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "provider_binding")

    assert check.state == "ready", "a machine without gh is still a sound installation"
    assert "gh" in check.detail
    assert "provider fetch" in check.detail


def test_the_command_that_creates_a_passport_is_named_in_one_place() -> None:
    """The refusal and the diagnostic must never name different commands.

    `doctor` says what composing will need; `select propose` says it again when
    it refuses. Two tables would agree until one of the commands is renamed.
    """
    from ai_stp_cli.commands import doctor as doctor_command
    from ai_stp_cli.commands import select as select_command
    from ai_stp_cli.local import passports

    for module in (doctor_command, select_command):
        source = Path(module.__file__ or "").read_text(encoding="utf-8")
        assert "passport developer init --json" not in source, (
            f"{module.__name__} restates a command that `passports.CREATES_PASSPORT` owns"
        )

    assert set(passports.COMPOSITION_PASSPORT_KINDS) <= set(passports.CREATES_PASSPORT)


def test_doctor_summarises_as_the_worst_check_it_found() -> None:
    # A summary of `ready` beside a failed check would be read by exactly the
    # callers who only read the summary.
    assert doctor.worst(["ready", "failed", "needs_user_action"]) == "failed"
    assert doctor.worst(["ready", "partial"]) == "partial"
    assert doctor.worst(["ready", "ready"]) == "ready"
    assert doctor.worst([]) == "ready"


def test_doctor_reads_an_existing_configuration_rather_than_only_noticing_it(
    tmp_path: Path,
) -> None:
    from ai_stp_cli import config

    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("catalog:\n  enabled: false\n", encoding="utf-8")
    registry = Path(
        str(next(v for v in config.effective_config().values if v.path == "registry.path").value)
    )
    from ai_stp_cli.local.database import open_registry

    open_registry(registry).close()

    from ai_stp_cli.commands import device

    device.init({})

    report = doctor.run({}).payload
    by_name = {check.name: check for check in report.checks}
    assert by_name["configuration"].detail == "read from file"
    assert by_name["local_registry"].state == "ready"
    assert "disabled" in by_name["catalog"].detail
    assert by_name["device_identity"].state == "ready"
    assert by_name["file_permissions"].state == "ready"
    assert report.state == "ready"


def test_doctor_fails_loudly_when_the_configuration_cannot_be_read() -> None:
    # The difference between "I looked and you are not ready" and "I could not
    # look" is the whole reason `doctor` exits 0 in the first case.
    from ai_stp_cli import config
    from ai_stp_cli.errors import CliFailure

    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("catalog:\n  - [unclosed\n", encoding="utf-8")
    with pytest.raises(CliFailure):
        doctor.run({})


def test_capabilities_is_the_cheap_orientation_call() -> None:
    report = machine_help.capabilities({}).payload
    assert report.wire_schema_version == 1
    assert report.supported_harnesses == sorted(report.supported_harnesses)
    assert "claude-code" in report.supported_harnesses
    assert report.catalog_enabled is True
    assert report.sync_enabled is False


def test_machine_help_carries_the_global_option_once() -> None:
    report = machine_help.registry({}).payload
    assert [option.name for option in report.global_options] == ["json"]
    for descriptor in report.commands:
        assert "json" not in {parameter.name for parameter in descriptor.parameters}


def test_config_show_reports_every_declared_field() -> None:
    from ai_stp_cli import config

    report = config_show.run({}).payload
    assert [value.path for value in report.values] == [
        field.path for field in config.declared_fields()
    ]


def test_an_unsupported_interpreter_is_reported_as_a_failed_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unreachable on a supported interpreter, which is exactly why it would
    # otherwise first run on the machine of the user it is meant to help.
    monkeypatch.setattr(sys, "version_info", (3, 11, 0))
    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "python_runtime")
    assert check.state == "failed"
    assert report.state == "failed"


def test_device_init_creates_the_identity_and_is_idempotent() -> None:
    from ai_stp_cli.commands import device

    first = device.init({})
    second = device.init({})
    assert first.payload.device_id == second.payload.device_id
    # The repository fixture removes the operating system store, so the
    # fallback is in effect and must be stated rather than assumed.
    assert first.payload.credential_store == "file"
    assert first.warnings and "owner-only file" in first.warnings[0]


def test_device_reset_without_confirmation_asks_for_a_decision() -> None:
    from ai_stp_cli.commands import device
    from ai_stp_cli.errors import CliFailure

    device.init({})
    with pytest.raises(CliFailure) as raised:
        device.reset({})
    # A decision the user has not made, not a malformed command: an agent reads
    # exit class 4 as "ask the user" and class 2 as "you called it wrong".
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"
    assert raised.value.exit_code == 4


def test_device_reset_with_confirmation_produces_a_new_identity() -> None:
    from ai_stp_cli.commands import device

    before = device.init({}).payload
    after = device.reset({"confirm": True}).payload
    assert after.device_id != before.device_id
    assert after.public_key != before.public_key


def test_auth_status_is_local_only_before_any_sign_in() -> None:
    from ai_stp_cli.commands import auth_status

    answer = auth_status.run({})
    # Not a fault: the whole local contour works without an account.
    assert answer.payload.state == "local_only"
    assert answer.payload.account_id is None
    # No store is named for a credential that does not exist: naming one would
    # suggest something is held.
    assert answer.payload.credential_store is None


def test_auth_status_reports_a_held_credential() -> None:
    from ai_stp_cli.cloud import session
    from ai_stp_cli.commands import auth_status
    from ai_stp_cli.secrets import open_store
    from ai_stp_foundation.ids import new_id

    store, _warning = open_store()
    account, device = new_id("account"), new_id("device")
    session.save(
        store,
        session.Session(
            account_id=account,
            device_id=device,
            access_token="secret-access",
            refresh_token="secret-refresh",
            expires_at="2099-09-01T00:00:00.000Z",
        ),
    )
    answer = auth_status.run({})
    assert answer.payload.state == "authenticated"
    assert answer.payload.account_id == account
    assert answer.payload.credential_store == "file"
    # A token is never part of the answer.
    assert "secret-" not in answer.payload.model_dump_json()


def test_doctor_reports_the_credential_store_it_would_actually_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_stp_cli.secrets.selected_backend", lambda: "keyring.backends.SecretService.Keyring"
    )
    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "credential_store")
    assert check.detail == "SecretService"


def test_doctor_does_not_create_an_identity_while_looking_at_it() -> None:
    from ai_stp_cli import paths

    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "device_identity")
    assert check.state == "needs_user_action"
    # `doctor` is declared `read`; creating state here would make the class a lie.
    assert not paths.device_file().exists()


@pytest.mark.skipif(
    not _POSIX,
    reason="POSIX mode widening is not enforced on Windows (doctor skips st_mode checks)",
)
def test_doctor_notices_a_file_whose_permissions_widened() -> None:
    from ai_stp_cli import paths
    from ai_stp_cli.commands import device

    device.init({})
    paths.device_file().chmod(0o644)
    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "file_permissions")
    assert check.state == "failed"
    assert "device.json" in check.detail
    assert report.state == "failed"


def test_doctor_reports_a_damaged_identity_as_failed_rather_than_raising() -> None:
    from ai_stp_cli import paths
    from ai_stp_cli.commands import device

    device.init({})
    paths.write_private(paths.device_file(), "{not json")
    report = doctor.run({}).payload
    check = next(item for item in report.checks if item.name == "device_identity")
    assert check.state == "failed"


def test_doctor_reports_a_revoked_identity_as_needing_action() -> None:
    from ai_stp_cli import paths
    from ai_stp_cli.commands import device

    current = device.init({}).payload
    paths.write_private(
        paths.device_file(),
        json.dumps(
            {
                "device_id": current.device_id,
                "created_at": current.created_at,
                "state": "revoked",
                "retired": [],
            }
        ),
    )
    check = next(item for item in doctor.run({}).payload.checks if item.name == "device_identity")
    assert check.state == "needs_user_action"
    assert "revoked" in check.detail


def test_doctor_finds_a_registry_at_the_path_it_would_actually_open() -> None:
    # The regression: the check once tested a redacted `~/...` string, which
    # `Path.exists` resolves against the working directory.
    from ai_stp_cli import config

    report = doctor.run({}).payload
    assert next(c for c in report.checks if c.name == "local_registry").state == "needs_user_action"

    registry = Path(
        str(next(v for v in config.effective_config().values if v.path == "registry.path").value)
    )
    assert registry.is_absolute()
    from ai_stp_cli.local.database import open_registry

    open_registry(registry).close()
    report = doctor.run({}).payload
    assert next(c for c in report.checks if c.name == "local_registry").state == "ready"


def test_doctor_never_reaches_the_machines_real_credential_store() -> None:
    # The repository fixture replaces detection, and `doctor` has to consult it
    # through the module for that to hold: a name imported at module load cannot
    # be replaced, and once it was not.
    check = next(item for item in doctor.run({}).payload.checks if item.name == "credential_store")
    assert check.detail.startswith("owner-only file")


def test_passport_commands_work_without_an_account_or_a_network() -> None:
    # `offline-capability.md` puts developer passport read, change and revisions
    # in the offline column; nothing here opens a socket.
    from ai_stp_cli.commands import passport
    from ai_stp_cli.errors import CliFailure

    with pytest.raises(CliFailure, match="does not exist yet"):
        passport.developer_show({})

    created = passport.developer_init({}).payload
    assert created.kind == "developer"
    assert created.owner_id.startswith("account_")
    assert passport.developer_init({}).payload.revision_id == created.revision_id
    assert passport.developer_show({}).payload.revision_id == created.revision_id

    updated = passport.developer_update(
        {"set": ("role=backend", "preferred_languages=python,rust")}
    )
    assert updated.payload.parent_revision_ids == [created.revision_id]
    facts = cast(dict[str, dict[str, object]], updated.payload.facts)
    assert facts["role"]["value"] == "backend"
    assert facts["preferred_languages"]["value"] == ["python", "rust"]


def test_the_device_passport_holds_the_environment_and_the_developer_does_not() -> None:
    # `ADR-0025`: one owner per fact. The split is enforced, not trusted.
    from ai_stp_cli.commands import passport
    from ai_stp_cli.errors import CliFailure

    device = passport.device_refresh({}).payload
    # `SPEC-014` REQ-1418 puts the harness survey here and nowhere else.
    assert sorted(device.facts) == [
        "architecture",
        "harness_versions",
        "installed_harnesses",
        "operating_system",
        "tool_versions",
    ]
    tool_versions = cast(dict[str, object], device.facts["tool_versions"])["value"]
    assert cast(list[str], tool_versions)[0].startswith("ai-stp-cli=")

    passport.developer_init({})
    developer = passport.developer_show({}).payload
    assert not set(developer.facts) & set(device.facts)

    with pytest.raises(CliFailure, match="belongs to the device passport") as raised:
        passport.developer_update({"set": ("operating_system=linux",)})
    assert raised.value.details["owner"] == "device"


def test_a_rescan_that_found_nothing_new_writes_nothing() -> None:
    from ai_stp_cli.commands import passport

    first = passport.device_refresh({}).payload
    second = passport.device_refresh({}).payload
    assert first.revision_id == second.revision_id
    assert second.parent_revision_ids == []


def test_a_malformed_declaration_is_refused() -> None:
    from ai_stp_cli.commands import passport
    from ai_stp_cli.errors import CliFailure

    passport.developer_init({})
    with pytest.raises(CliFailure, match="field=value"):
        passport.developer_update({"set": ("role",)})
    for nothing in ({"set": ()}, {}):
        with pytest.raises(CliFailure, match="nothing was declared"):
            passport.developer_update(nothing)
    with pytest.raises(CliFailure, match="unknown developer passport field"):
        passport.developer_update({"set": ("favourite_colour=blue",)})


def test_doctor_reports_a_registry_written_by_a_newer_build_as_failed() -> None:
    import sqlite3

    from ai_stp_cli.commands import passport
    from ai_stp_cli.local.database import SCHEMA_VERSION, configured_path

    passport.developer_init({})
    connection = sqlite3.connect(configured_path())
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    connection.close()

    check = next(item for item in doctor.run({}).payload.checks if item.name == "local_registry")
    assert check.state == "failed"
    assert "newer build" in check.detail


def test_doctor_reports_a_registry_awaiting_migration() -> None:
    import sqlite3

    from ai_stp_cli.commands import passport
    from ai_stp_cli.local.database import configured_path

    passport.developer_init({})
    connection = sqlite3.connect(configured_path())
    connection.execute("PRAGMA user_version=0")
    connection.close()

    check = next(item for item in doctor.run({}).payload.checks if item.name == "local_registry")
    assert check.state == "needs_user_action"
    assert "migrates it" in check.detail


@pytest.mark.skipif(
    not _POSIX,
    reason="POSIX mode widening is not enforced on Windows (doctor skips st_mode checks)",
)
def test_doctor_reports_a_world_readable_registry_as_failed() -> None:
    from ai_stp_cli.commands import passport
    from ai_stp_cli.local.database import configured_path

    passport.developer_init({})
    configured_path().chmod(0o644)
    check = next(item for item in doctor.run({}).payload.checks if item.name == "local_registry")
    assert check.state == "failed"


def test_showing_a_passport_needs_no_declarations() -> None:
    from ai_stp_cli.commands import passport

    passport.developer_init({})
    assert passport.developer_show({"set": None}).payload.kind == "developer"


def test_showing_the_developer_passport_of_a_registry_that_has_none() -> None:
    # A registry can exist without a developer passport: `passport device show`
    # creates one and the other. Reading then reports absence rather than
    # initialising, which is what `SPEC-009` REQ-902 asks of a read.
    from ai_stp_cli.commands import passport
    from ai_stp_cli.errors import CliFailure
    from ai_stp_cli.local.database import configured_path

    passport.device_refresh({})
    assert configured_path().exists()
    with pytest.raises(CliFailure, match="no developer passport yet") as raised:
        passport.developer_show({})
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_doctor_surfaces_an_interrupted_local_mutation() -> None:
    # The journal exists to be read after a run that stopped. Writing entries
    # nobody surfaces would make it write-only.
    from contextlib import closing

    from ai_stp_cli.commands import passport
    from ai_stp_cli.local import journal, passports
    from ai_stp_cli.local.database import configured_path, open_registry

    passport.developer_init({})
    check = next(c for c in doctor.run({}).payload.checks if c.name == "interrupted_operations")
    assert check.state == "ready"
    assert check.detail == "none"

    with closing(open_registry(configured_path())) as connection:
        stuck = journal.begin(connection, "passport.developer.update", passports.moment())
        journal.settle(connection, stuck, "applied_unverified", passports.moment())

    report = doctor.run({}).payload
    check = next(c for c in report.checks if c.name == "interrupted_operations")
    assert check.state == "needs_user_action"
    assert "applied_unverified" in check.detail
    assert report.state == "needs_user_action"


def test_device_reports_what_it_retired() -> None:
    from ai_stp_cli.commands import device

    first = device.init({}).payload
    assert first.retired_device_ids == []
    second = device.reset({"confirm": True}).payload
    assert second.retired_device_ids == [first.device_id]


def test_doctor_reports_an_unreadable_registry_rather_than_raising() -> None:
    from ai_stp_cli import paths
    from ai_stp_cli.commands import passport
    from ai_stp_cli.local.database import configured_path

    passport.developer_init({})
    paths.write_private(configured_path(), "this is not a database")
    check = next(c for c in doctor.run({}).payload.checks if c.name == "interrupted_operations")
    assert check.state == "failed"


def test_doctor_says_nothing_to_show_before_a_registry_exists() -> None:
    check = next(c for c in doctor.run({}).payload.checks if c.name == "interrupted_operations")
    assert check.state == "ready"
    assert "no local registry" in check.detail


def test_showing_a_version_needs_a_kind_too() -> None:
    from ai_stp_cli.commands import registry as registry_commands
    from ai_stp_cli.errors import CliFailure

    with pytest.raises(CliFailure, match="kind"):
        registry_commands.version({"id": "x", "version": "1.0"})


def test_showing_a_device_identity_that_does_not_exist_creates_nothing() -> None:
    from ai_stp_cli import paths
    from ai_stp_cli.commands import device
    from ai_stp_cli.errors import CliFailure

    # `device show` used to mint one, while declaring itself `read`. Observing an
    # installation must not be what brings it into existence.
    with pytest.raises(CliFailure, match="no device identity yet") as raised:
        device.show({})
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert raised.value.next_actions == ["device init --json"]
    assert not paths.device_file().exists()


def test_showing_a_device_passport_that_does_not_exist_creates_nothing() -> None:
    from ai_stp_cli.commands import device, passport
    from ai_stp_cli.errors import CliFailure

    # It was honestly declared `apply`, but `show` is what an agent reads, and a
    # command that writes history has no business being called one.
    device.init({})
    # A registry exists but holds no device passport; without one the earlier
    # "no registry" answer would be what this saw.
    passport.developer_init({})
    with pytest.raises(CliFailure, match="no device passport yet") as raised:
        passport.device_show({})
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert raised.value.next_actions == ["passport device refresh --json"]


def test_showing_an_identity_that_exists_reports_it_without_changing_it() -> None:
    from ai_stp_cli import paths
    from ai_stp_cli.commands import device

    made = device.init({}).payload
    before = paths.device_file().read_bytes()

    shown = device.show({}).payload

    assert shown.device_id == made.device_id
    assert shown.public_key == made.public_key
    assert paths.device_file().read_bytes() == before


def test_the_device_passport_is_read_after_it_is_refreshed() -> None:
    from ai_stp_cli.commands import device, passport

    device.init({})
    written = passport.device_refresh({}).payload
    read = passport.device_show({}).payload
    assert read.revision_id == written.revision_id
    # Reading twice is still one revision: the read does not observe anything.
    assert passport.device_show({}).payload.revision_id == written.revision_id


def test_the_configuration_commands_write_validate_and_leave_show_a_read() -> None:
    """The four machine-first commands, exercised through their handlers.

    `config show --set` and `config set` look alike and are not: one overrides a
    single call and rewrites nothing, the other is the write. Both are here so
    the difference is asserted rather than described.
    """
    from ai_stp_cli import config
    from ai_stp_cli.commands import config_show
    from ai_stp_cli.errors import CliFailure

    created = config_show.init({}).payload
    assert created.config_path is not None
    assert config.config_path().exists()

    written = config_show.set_({"set": ("catalog.enabled=false", "search.result_limit=5")}).payload
    by_path = {value.path: value for value in written.values}
    assert (by_path["catalog.enabled"].value, by_path["catalog.enabled"].source) == (
        False,
        "config_file",
    )

    # An override for one call, and the file is not touched by it.
    before = config.config_path().read_bytes()
    overridden = config_show.run({"set": ("search.result_limit=99",)}).payload
    assert {value.path: value.value for value in overridden.values}["search.result_limit"] == 99
    assert config.config_path().read_bytes() == before

    assert config_show.validate({}).payload.config_path is not None

    removed = config_show.unset({"field": ("catalog.enabled",)}).payload
    restored = {value.path: value for value in removed.values}["catalog.enabled"]
    assert (restored.value, restored.source) == (True, "default")

    for call in (
        lambda: config_show.set_({}),
        lambda: config_show.unset({}),
        lambda: config_show.set_({"set": ("no-equals-sign",)}),
    ):
        with pytest.raises(CliFailure, match=r"nothing was set|nothing was unset|path=value"):
            call()


def test_validating_a_broken_configuration_file_names_where_it_is() -> None:
    from ai_stp_cli import config
    from ai_stp_cli.commands import config_show
    from ai_stp_cli.errors import CliFailure

    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("catalog:\n  urll: https://elsewhere.test/v1\n", encoding="utf-8")

    with pytest.raises(CliFailure, match=r"unknown configuration key: catalog\.urll") as raised:
        config_show.validate({})
    assert raised.value.details["at"] == "catalog.urll"
