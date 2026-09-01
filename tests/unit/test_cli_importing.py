"""Importing native configuration: read-only, secret-free, and honest about it."""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import importing, revisions
from ai_stp_cli.local.database import configured_path, open_registry

AT = "2026-08-08T10:00:00.000Z"
DEVICE = "device_test"
OWNER = "account_01J0000000000000000000000A"
SECRET = "sk-live-THIS-MUST-NOT-BE-STORED"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


@pytest.fixture
def native(tmp_path: Path) -> Path:
    """A configuration shaped like a real one: secrets at three depths."""
    root = tmp_path / "claude"
    root.mkdir()
    (root / "settings.json").write_text(
        json.dumps(
            {
                "model": "claude",
                "api_key": SECRET,
                "auth": {"token": SECRET, "user": "danil"},
                "servers": [{"url": "https://example.test", "password": SECRET}],
            }
        ),
        encoding="utf-8",
    )
    (root / "CLAUDE.md").write_text("# rules\n", encoding="utf-8")
    return root


@pytest.fixture
def unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make one fixture file unreadable without relying on host ACL semantics."""
    read_bytes = Path.read_bytes

    def read_or_deny(path: Path) -> bytes:
        if path.name == "locked.json":
            raise PermissionError("fixture file is unreadable")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_or_deny)


def _backup(connection: sqlite3.Connection, harness_id: str = "claude-code") -> str:
    return importing.record_backup(
        connection,
        harness_id=harness_id,
        target_id="pair_1",
        provider_ref="slot-202608080000",
        at=AT,
    ).backup_id


# Inspection reads and nothing more.
def test_inspection_changes_nothing_on_disk(native: Path) -> None:
    before = {item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()}
    importing.inspect(native, harness_id="claude-code")
    after = {item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()}
    assert after == before


def test_inspection_reads_configuration_and_skips_anything_else(native: Path) -> None:
    (native / "cache.bin").write_bytes(b"\x00\x01\x02")
    found = importing.inspect(native, harness_id="claude-code")
    assert [item.path for item in found.findings] == ["CLAUDE.md", "settings.json"]


def test_inspection_is_ordered_so_two_runs_agree(native: Path) -> None:
    assert importing.inspect(native, harness_id="claude-code") == importing.inspect(
        native, harness_id="claude-code"
    )


def test_import_plan_is_deterministic_and_changes_with_inspected_bytes(native: Path) -> None:
    first = importing.plan(importing.inspect(native, harness_id="claude-code"))
    repeated = importing.plan(importing.inspect(native, harness_id="claude-code"))
    assert repeated == first
    assert first.inspection_digest.startswith("sha256:")
    assert first.plan_digest.startswith("sha256:")
    assert [item.component_type for item in first.components] == ["instruction", "setting"]

    (native / "CLAUDE.md").write_text("# changed rules\n", encoding="utf-8")
    changed = importing.plan(importing.inspect(native, harness_id="claude-code"))
    assert changed.inspection_digest != first.inspection_digest
    assert changed.plan_digest != first.plan_digest


def test_import_plan_groups_native_component_families(native: Path) -> None:
    skill = native / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review\n", encoding="utf-8")
    (skill / "notes.md").write_text("bounded reference\n", encoding="utf-8")
    command = native / "commands"
    command.mkdir()
    (command / "ship.md").write_text("ship safely\n", encoding="utf-8")

    planned = importing.plan(importing.inspect(native, harness_id="claude-code"))
    by_type = {item.component_type: item for item in planned.components}
    assert by_type["skill"].paths == ("skills/review/SKILL.md", "skills/review/notes.md")
    assert by_type["command"].paths == ("commands/ship.md",)
    assert planned.blocked_by == ()
    assert planned.effects[-1].endswith("exact component references")


def test_an_oversized_file_is_excluded_and_does_not_block(native: Path) -> None:
    # It was read and hashed, so it is not unreadable. Real harness roots carry
    # caches — a live `~/.codex` holds multi-megabyte catalogue blobs — and
    # blocking on those made every such root unimportable.
    huge = native / "huge.json"
    huge.write_text("x" * (importing.MAX_FILE_BYTES + 1), encoding="utf-8")
    inspected = importing.inspect(native, harness_id="claude-code")
    assert inspected.oversized == ("huge.json",)
    assert inspected.unreadable == ()
    planned = importing.plan(inspected)
    assert planned.excluded == ("huge.json",)
    assert planned.blocked_by == ()


def test_an_oversized_file_is_still_hashed_rather_than_dropped(native: Path) -> None:
    huge = native / "huge.json"
    huge.write_text("x" * (importing.MAX_FILE_BYTES + 1), encoding="utf-8")
    inspected = importing.inspect(native, harness_id="claude-code")
    found = next(item for item in inspected.findings if item.path == "huge.json")
    assert found.digest.startswith("sha256:")
    assert found.byte_length > importing.MAX_FILE_BYTES
    assert found.unreadable == ""


def test_a_file_nobody_can_read_still_blocks_registration(native: Path, unreadable: None) -> None:
    blocked = native / "locked.json"
    blocked.write_text("{}", encoding="utf-8")
    inspected = importing.inspect(native, harness_id="claude-code")
    assert inspected.unreadable == ("locked.json",)
    assert inspected.oversized == ()
    planned = importing.plan(inspected)
    assert planned.blocked_by == ("unreadable:locked.json",)


def test_no_path_is_both_excluded_and_blocking(native: Path, unreadable: None) -> None:
    # The two lists answer different questions, and a caller told a path is
    # simultaneously left out and in the way has nothing to act on.
    huge = native / "huge.json"
    huge.write_text("x" * (importing.MAX_FILE_BYTES + 1), encoding="utf-8")
    locked = native / "locked.json"
    locked.write_text("{}", encoding="utf-8")
    planned = importing.plan(importing.inspect(native, harness_id="claude-code"))
    blocking = {entry.partition(":")[2] for entry in planned.blocked_by}
    assert blocking == {"locked.json"}
    assert set(planned.excluded) >= {"huge.json", "locked.json"}
    assert blocking & {"huge.json"} == set()


def test_a_missing_directory_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        importing.inspect(tmp_path / "absent", harness_id="claude-code")
    assert raised.value.code == "AI_STP_NOT_FOUND"


# Secrets: values never travel, names do.
def test_a_secret_value_is_removed_at_every_depth(native: Path) -> None:
    cleaned, names = importing.scrub((native / "settings.json").read_bytes())
    text = cleaned.decode("utf-8")
    assert SECRET not in text
    assert names == ("api_key", "auth.token", "servers[].password")


def test_scrubbing_keeps_everything_that_is_not_a_credential(native: Path) -> None:
    cleaned, _ = importing.scrub((native / "settings.json").read_bytes())
    document = json.loads(cleaned)
    assert document["model"] == "claude"
    assert document["auth"]["user"] == "danil"
    assert document["servers"][0]["url"] == "https://example.test"


def test_a_removed_value_is_marked_rather_than_blanked(native: Path) -> None:
    """An empty string reads as "this setting is off", which is a different thing."""
    cleaned, _ = importing.scrub((native / "settings.json").read_bytes())
    assert json.loads(cleaned)["api_key"] == importing.REDACTED


def test_an_unstructured_file_is_returned_untouched_with_nothing_claimed() -> None:
    """Guessing at its shape would either miss a secret or mangle the document."""
    raw = b"# notes\ntoken: not-really-parsed\n"
    cleaned, names = importing.scrub(raw)
    assert cleaned == raw
    assert names == ()


@pytest.mark.parametrize(
    "name", ["token", "API_KEY", "client-secret", "auth.password", "private_key"]
)
def test_a_name_that_says_credential_is_detected(name: str) -> None:
    assert importing.is_secret_key(name)


@pytest.mark.parametrize("name", ["model", "user", "url", "keyboard", "tokenizer"])
def test_a_name_that_does_not_say_credential_is_left_alone(name: str) -> None:
    assert not importing.is_secret_key(name)


def test_the_report_names_the_rule_it_used(native: Path) -> None:
    """A report that will not say how it looked cannot be told from a thorough one."""
    found = importing.inspect(native, harness_id="claude-code")
    assert found.detection_rule == importing.DETECTION_RULE == "key-name"


# The backup is the provider's, and it is a separate object.
def test_a_backup_holds_a_reference_and_never_bytes(registry: sqlite3.Connection) -> None:
    backup_id = _backup(registry)
    held = importing.backup(registry, backup_id)
    assert held is not None
    assert held.provider_ref == "slot-202608080000"
    columns = {str(row[1]) for row in registry.execute("PRAGMA table_info(backup_ref)").fetchall()}
    assert "bytes" not in columns, "the provider owns the backup; two owners cannot both restore"


def test_a_backup_without_a_provider_reference_is_refused(
    registry: sqlite3.Connection,
) -> None:
    with pytest.raises(CliFailure) as raised:
        importing.record_backup(
            registry, harness_id="claude-code", target_id="pair_1", provider_ref="", at=AT
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_registration_requires_a_backup_that_exists(
    registry: sqlite3.Connection, native: Path
) -> None:
    """`REQ-813` puts the provider's backup before registration."""
    found = importing.inspect(native, harness_id="claude-code")
    with pytest.raises(CliFailure) as raised:
        importing.register(
            registry,
            found,
            backup_id="backup_01J0000000000000000000000Z",
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_backup_for_another_harness_is_refused(
    registry: sqlite3.Connection, native: Path
) -> None:
    backup_id = _backup(registry, harness_id="codex")
    found = importing.inspect(native, harness_id="claude-code")
    with pytest.raises(CliFailure) as raised:
        importing.register(
            registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
        )
    assert raised.value.code == "AI_STP_CONFLICT"


def test_the_backup_is_not_the_setups_identity(registry: sqlite3.Connection, native: Path) -> None:
    """`REQ-814`: deleting a backup must not delete what it was protecting."""
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    imported = importing.register(
        registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
    )
    assert imported.stable_id != imported.backup_id
    assert imported.stable_id.startswith("setup_")
    assert imported.backup_id.startswith("backup_")

    registry.execute("DELETE FROM backup_ref WHERE backup_id = ?", (backup_id,))
    still = revisions.head(registry, imported.stable_id)
    assert still is not None, "the setup outlives the backup it references"


# The registered passport.
def test_no_secret_value_reaches_the_registry(registry: sqlite3.Connection, native: Path) -> None:
    """The one thing this whole module exists to guarantee."""
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    imported = importing.register(
        registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
    )

    stored = revisions.head(registry, imported.stable_id)
    assert stored is not None
    assert SECRET not in json.dumps(stored.envelope.model_dump(mode="json"))

    whole = registry.execute("SELECT group_concat(content) AS held FROM revision").fetchone()
    assert SECRET not in str(whole["held"])


def test_the_passport_carries_names_and_provenance(
    registry: sqlite3.Connection, native: Path
) -> None:
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    imported = importing.register(
        registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
    )
    stored = revisions.head(registry, imported.stable_id)
    assert stored is not None
    facts = stored.envelope.model_dump(mode="json")["facts"]

    assert facts["redacted_keys"]["value"] == list(found.redacted_keys)
    assert facts["backup_id"]["value"] == backup_id
    assert facts["origin"]["value"] == "imported"
    assert facts["detection_rule"]["value"] == "key-name"
    assert [item["path"] for item in facts["files"]["value"]] == ["CLAUDE.md", "settings.json"]
    assert all(item["digest"].startswith("sha256:") for item in facts["files"]["value"])


def test_an_imported_setup_is_private(registry: sqlite3.Connection, native: Path) -> None:
    """It is somebody's working machine; publishing it is a decision nobody made."""
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    imported = importing.register(
        registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
    )
    stored = revisions.head(registry, imported.stable_id)
    assert stored is not None
    assert stored.envelope.visibility == "private"


def test_registration_does_not_touch_the_source(registry: sqlite3.Connection, native: Path) -> None:
    before = {item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()}
    backup_id = _backup(registry)
    importing.register(
        registry,
        importing.inspect(native, harness_id="claude-code"),
        backup_id=backup_id,
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    after = {item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()}
    assert after == before


def test_an_empty_configuration_imports_nothing(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    backup_id = _backup(registry)
    with pytest.raises(CliFailure) as raised:
        importing.register(
            registry,
            importing.inspect(empty, harness_id="claude-code"),
            backup_id=backup_id,
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_configuration_with_an_unread_file_is_not_registered(
    registry: sqlite3.Connection, native: Path, unreadable: None
) -> None:
    """A setup registered from files nobody read would describe what it never saw."""
    locked = native / "locked.json"
    locked.write_text("{}", encoding="utf-8")
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    assert found.unreadable == ("locked.json",)

    with pytest.raises(CliFailure) as raised:
        importing.register(
            registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_capture_that_leaves_files_out_is_complete_or_refused(
    registry: sqlite3.Connection, native: Path
) -> None:
    """Registering part of a configuration as the whole of one needs saying so."""
    huge = native / "huge.json"
    huge.write_text("x" * (importing.MAX_FILE_BYTES + 1), encoding="utf-8")
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    assert found.oversized == ("huge.json",)
    assert found.unreadable == ()

    with pytest.raises(CliFailure) as refused:
        importing.register(
            registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
        )
    assert refused.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "huge.json" in str(refused.value.details.get("skipped", ""))


def test_a_partial_capture_registers_and_records_what_it_left_out(
    registry: sqlite3.Connection, native: Path
) -> None:
    """`partial` is the operator saying it out loud, and the passport keeps it."""
    huge = native / "huge.json"
    huge.write_text("x" * (importing.MAX_FILE_BYTES + 1), encoding="utf-8")
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")

    imported = importing.register(
        registry,
        found,
        backup_id=backup_id,
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
        partial=True,
    )
    assert imported.stable_id
    stored = revisions.head(registry, imported.stable_id)
    assert stored is not None
    facts = stored.envelope.model_dump(mode="json")["facts"]
    assert facts["capture_mode"]["value"] == "partial"
    assert facts["excluded_paths"]["value"] == ["huge.json"]


def test_a_complete_capture_says_so_in_its_passport(
    registry: sqlite3.Connection, native: Path
) -> None:
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    imported = importing.register(
        registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
    )
    stored = revisions.head(registry, imported.stable_id)
    assert stored is not None
    facts = stored.envelope.model_dump(mode="json")["facts"]
    assert facts["capture_mode"]["value"] == "complete"
    assert "excluded_paths" not in facts
    # The versions the capture was captured with and against are pinned facts:
    # the instrument always, the harness build when one answered, and an empty
    # harness version is the honest record of a tree imported where the
    # harness itself is not installed.
    assert facts["capture_tool_version"]["value"].startswith("ai-stp-cli=")
    assert facts["harness_version"]["value"] == ""
    imported_again = importing.register(
        registry,
        found,
        backup_id=_backup(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
        harness_version="2.1.223",
    )
    pinned = revisions.head(registry, imported_again.stable_id)
    assert pinned is not None
    held = pinned.envelope.model_dump(mode="json")["facts"]
    assert held["harness_version"]["value"] == "2.1.223"


def test_an_unreadable_file_is_not_the_same_as_a_clean_one(native: Path, unreadable: None) -> None:
    locked = native / "locked.json"
    locked.write_text("{}", encoding="utf-8")
    found = importing.inspect(native, harness_id="claude-code")
    named = {item.path: item for item in found.findings}
    assert named["locked.json"].unreadable
    assert named["locked.json"].oversized is False
    assert named["CLAUDE.md"].unreadable == ""
    assert named["CLAUDE.md"].redacted_keys == ()


def test_the_import_is_recorded_in_the_journal(registry: sqlite3.Connection, native: Path) -> None:
    backup_id = _backup(registry)
    importing.register(
        registry,
        importing.inspect(native, harness_id="claude-code"),
        backup_id=backup_id,
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    row = registry.execute("SELECT state FROM operation WHERE kind = 'setup.import'").fetchone()
    assert row is not None and row["state"] == "verified"


def test_nothing_in_this_module_writes_to_a_harness() -> None:
    """The invariant the whole import path exists to keep."""
    source = Path("apps/cli/src/ai_stp_cli/local/importing.py").read_text("utf-8")
    # Filesystem writes only. A bare `replace(` would also catch `str.replace`,
    # which is what a first version of this did — a test that fails on a string
    # operation teaches nothing and gets deleted.
    for verb in ("write_text(", "write_bytes(", "mkdir(", "unlink(", "rmtree(", "Path.replace("):
        assert verb not in source


def test_the_inspect_command_reports_without_writing(native: Path) -> None:
    from ai_stp_cli.commands import project

    before = {item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()}
    report = project.import_inspect({"root": str(native), "harness": "claude-code"}).payload
    assert [item.path for item in report.files] == ["CLAUDE.md", "settings.json"]
    assert report.redacted_keys == ["api_key", "auth.token", "servers[].password"]
    assert report.detection_rule == "key-name"
    assert {
        item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()
    } == before


def test_the_plan_command_reports_exact_components_without_writing(native: Path) -> None:
    from ai_stp_cli.commands import project

    before = {item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()}
    planned = project.import_plan({"root": str(native), "harness": "claude-code"}).payload
    assert planned.harness_id == "claude-code"
    assert planned.plan_digest.startswith("sha256:")
    assert [item.component_type for item in planned.components] == ["instruction", "setting"]
    assert {
        item: item.read_bytes() for item in sorted(native.rglob("*")) if item.is_file()
    } == before


def test_the_register_command_needs_the_providers_backup(native: Path) -> None:
    from ai_stp_cli.commands import project

    with pytest.raises(CliFailure) as raised:
        digest = project.import_plan(
            {"root": str(native), "harness": "claude-code"}
        ).payload.plan_digest
        project.import_register(
            {
                "root": str(native),
                "harness": "claude-code",
                "backup-ref": "",
                "plan-digest": digest,
                "confirm": True,
            }
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_the_register_command_stores_no_secret(registry: sqlite3.Connection, native: Path) -> None:
    from ai_stp_cli.commands import project

    del registry
    digest = project.import_plan(
        {"root": str(native), "harness": "claude-code"}
    ).payload.plan_digest
    imported = project.import_register(
        {
            "root": str(native),
            "harness": "claude-code",
            "backup-ref": "slot-202608080000",
            "plan-digest": digest,
            "confirm": True,
        }
    ).payload
    assert imported.stable_id.startswith("setup_")
    assert imported.backup_id.startswith("backup_")
    assert imported.redacted_keys == ["api_key", "auth.token", "servers[].password"]
    assert imported.plan_digest == digest
    assert len(imported.component_ids) == 2

    with closing(open_registry(configured_path(), create=True)) as connection:
        whole = connection.execute("SELECT group_concat(content) AS held FROM revision").fetchone()
        assert SECRET not in str(whole["held"])


def test_graph_registration_refuses_a_changed_plan_and_leaves_no_backup(
    registry: sqlite3.Connection, native: Path
) -> None:
    from ai_stp_cli.commands import project

    del registry
    digest = project.import_plan(
        {"root": str(native), "harness": "claude-code"}
    ).payload.plan_digest
    (native / "CLAUDE.md").write_text("changed after review", encoding="utf-8")

    with pytest.raises(CliFailure) as raised:
        project.import_register(
            {
                "root": str(native),
                "harness": "claude-code",
                "backup-ref": "slot-000000000009",
                "plan-digest": digest,
                "confirm": True,
            }
        )
    assert raised.value.code == "AI_STP_CONFLICT"
    with closing(open_registry(configured_path(), create=True)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM backup_ref").fetchone()[0] == 0


def test_graph_registration_requires_the_exact_plan_digest(native: Path) -> None:
    """The digest is the confirmation; a boolean beside it said only "yes".

    Registering an import writes the local registry and is reversible, so
    `ADR-0118` puts it inside the task's authority. What must still hold is that
    the caller names *which* plan — omitted is a malformed call, and a digest
    the plan no longer matches is refused by `register_graph` itself.
    """
    from ai_stp_cli.commands import project

    digest = project.import_plan(
        {"root": str(native), "harness": "claude-code"}
    ).payload.plan_digest
    base = {
        "root": str(native),
        "harness": "claude-code",
        "backup-ref": "slot-000000000007",
    }
    with pytest.raises(CliFailure) as missing:
        project.import_register(base)
    assert missing.value.code == "AI_STP_VALIDATION_ERROR"

    with pytest.raises(CliFailure) as stale:
        project.import_register({**base, "plan-digest": "sha256:" + "0" * 64})
    assert stale.value.code != "AI_STP_USER_DECISION_REQUIRED"
    assert digest not in str(stale.value)


@pytest.mark.parametrize("harness", ["", "undefined", "not-a-harness"])
def test_an_unsupported_harness_is_refused(native: Path, harness: str) -> None:
    from ai_stp_cli.commands import project

    with pytest.raises(CliFailure) as raised:
        project.import_inspect({"root": str(native), "harness": harness})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_the_configuration_directory_must_be_named() -> None:
    from ai_stp_cli.commands import project

    with pytest.raises(CliFailure) as raised:
        project.import_inspect({"harness": "claude-code"})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_camel_case_credential_names_are_redacted(native: Path) -> None:
    """Claude Code stores OAuth tokens as `accessToken`, not `access_token`.

    `is_secret_key` compares exactly against `SECRET_KEYS`, so a name has to be
    folded into that shape first. While it was not, a real `~/.claude`
    `.credentials.json` imported with nothing redacted at all.
    """
    (native / "creds.json").write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": SECRET,
                    "refreshToken": SECRET,
                    "expiresAt": 1,
                    "subscriptionType": "max",
                },
                "mcpOAuth": {"server": {"clientSecret": SECRET, "serverName": "figma"}},
            }
        ),
        encoding="utf-8",
    )
    found = importing.inspect(native, harness_id="claude-code")
    creds = next(item for item in found.findings if item.path == "creds.json")
    assert "claudeAiOauth.accessToken" in creds.redacted_keys
    assert "claudeAiOauth.refreshToken" in creds.redacted_keys
    assert "mcpOAuth.server.clientSecret" in creds.redacted_keys
    # Neighbours that merely sit beside a credential are not credentials.
    assert "claudeAiOauth.expiresAt" not in creds.redacted_keys
    assert "claudeAiOauth.subscriptionType" not in creds.redacted_keys
    assert "mcpOAuth.server.serverName" not in creds.redacted_keys


def test_one_name_written_three_ways_folds_to_one(native: Path) -> None:
    for spelling in ("accessToken", "access-token", "Access_Token", "ACCESS_TOKEN"):
        assert importing.is_secret_key(spelling), spelling


def test_harness_state_subtrees_are_not_read(native: Path) -> None:
    """A configuration root is also where the harness writes its own history."""
    (native / "jobs").mkdir()
    (native / "jobs" / "run.json").write_text('{"a": 1}', encoding="utf-8")
    (native / "sessions").mkdir()
    (native / "sessions" / "s.json").write_text('{"a": 1}', encoding="utf-8")
    found = importing.inspect(native, harness_id="claude-code")
    paths = {item.path for item in found.findings}
    assert "jobs/run.json" not in paths
    assert "sessions/s.json" not in paths
    assert "settings.json" in paths


def test_state_matching_is_by_whole_segment(native: Path) -> None:
    """A declared `cache` must not swallow a sibling that merely starts with it."""
    (native / "cache").mkdir()
    (native / "cache" / "x.json").write_text("{}", encoding="utf-8")
    (native / "cache-policy.json").write_text('{"keep": true}', encoding="utf-8")
    found = importing.inspect(native, harness_id="claude-code")
    paths = {item.path for item in found.findings}
    assert "cache/x.json" not in paths
    assert "cache-policy.json" in paths


def test_a_harness_with_no_declared_state_keeps_every_file(native: Path) -> None:
    """Silence in the catalog means "not known", never "exclude it"."""
    (native / "jobs").mkdir()
    (native / "jobs" / "run.json").write_text('{"a": 1}', encoding="utf-8")
    found = importing.inspect(native, harness_id="opencode")
    assert "jobs/run.json" in {item.path for item in found.findings}


def test_an_oversized_file_is_never_read_whole_into_memory(native: Path) -> None:
    """The declared bound has to bound something.

    `MAX_FILE_BYTES` was checked *after* `read_bytes()`, so the limit described
    the outcome and not the cost: a harness root holding a multi-gigabyte cache
    blob — a real `~/.codex` does — was allocated whole in order to discover
    that it would be excluded.

    `REQ-841` still holds: the file is read and hashed, and the finding carries
    the same digest and length it always did. What changed is that "read" no
    longer means "read into one object", which the requirement never said.

    Proven by watching the reads rather than by trusting the shape: the whole
    body must never arrive in a single call.
    """
    import pathlib

    huge = native / "huge.json"
    huge.write_bytes(b"x" * (importing.MAX_FILE_BYTES * 3))
    biggest: list[int] = []
    original = pathlib.Path.read_bytes

    def spy(self: pathlib.Path) -> bytes:
        payload = original(self)
        biggest.append(len(payload))
        return payload

    pathlib.Path.read_bytes = spy  # pyright: ignore[reportAttributeAccessIssue]
    try:
        inspected = importing.inspect(native, harness_id="codex")
    finally:
        pathlib.Path.read_bytes = original  # pyright: ignore[reportAttributeAccessIssue]

    assert "huge.json" in inspected.oversized
    assert max(biggest, default=0) <= importing.MAX_FILE_BYTES, (
        f"a single read returned {max(biggest, default=0)} bytes, "
        "so the declared bound bounds nothing"
    )
    # And the evidence is unchanged: the exclusion still names an exact digest.
    found = next(item for item in inspected.findings if item.path == "huge.json")
    assert found.digest.startswith("sha256:")
    assert found.byte_length == importing.MAX_FILE_BYTES * 3


def test_an_environment_block_keeps_its_names_and_loses_every_value() -> None:
    """`REQ-815` says an imported setup carries names of variables and nothing else.

    Measured on 2026-08-29, before this existed: an MCP configuration carrying

        "env": {"GITHUB_TOKEN": "ghp_realsecretvalue", "MODEL": "sonnet"}

    came back from `scrub` **unchanged**. `Authorization` beside it was redacted
    because that word is in `SECRET_KEYS`; `GITHUB_TOKEN` is not, and the
    comparison is exact against the folded key rather than a substring — for
    good reasons that do not help here.

    The platform's safety scanner had the same hole and it was closed on
    2026-08-27 (`mcp_secret_like` never matching JSON). This is the same defect
    one layer over, on the path that writes the registry, and closing one did
    not close the other.

    The rule is the contract rather than a longer word list: inside an `env`
    map every value is an environment variable's value, and `REQ-815` lets the
    name travel and nothing else. `MODEL` is not a secret and its value goes
    too, because a scrubber that decides which environment values are harmless
    is guessing at exactly the point it must not.
    """
    raw = json.dumps(
        {
            "mcpServers": {
                "demo": {
                    "command": "node",
                    "env": {"GITHUB_TOKEN": "ghp_realsecretvalue", "MODEL": "sonnet"},
                }
            }
        }
    ).encode("utf-8")

    cleaned, names = importing.scrub(raw)
    text = cleaned.decode("utf-8")
    assert "ghp_realsecretvalue" not in text
    document = json.loads(cleaned)
    block = document["mcpServers"]["demo"]["env"]
    # The names survive, which is what a passport is allowed to carry.
    assert sorted(block) == ["GITHUB_TOKEN", "MODEL"]
    assert block["GITHUB_TOKEN"] == importing.REDACTED
    assert block["MODEL"] == importing.REDACTED
    # And the command beside it is untouched: this is a rule about one map.
    assert document["mcpServers"]["demo"]["command"] == "node"
    assert "mcpServers.demo.env.GITHUB_TOKEN" in names


# The catalogue is the one owner of what a native path means (`ADR-0138`).
# Every row here was a real misclassification before import consumed it: the
# review of 2026-09-01 tabled them, and each was verified against the code
# before the resolver replaced the five-name guess.
def _classified(root: Path, harness_id: str) -> dict[str, str]:
    planned = importing.plan(importing.inspect(root, harness_id=harness_id))
    return {path: item.component_type for item in planned.components for path in item.paths}


def test_codex_surfaces_classify_by_the_catalogue(tmp_path: Path) -> None:
    root = tmp_path / "codex"
    (root / "prompts").mkdir(parents=True)
    (root / "prompts" / "deploy.md").write_text("ship\n", encoding="utf-8")
    (root / "agents").mkdir()
    (root / "agents" / "reviewer.toml").write_text('description = "r"\n', encoding="utf-8")
    (root / "AGENTS.md").write_text("# floor\n", encoding="utf-8")
    (root / "config.toml").write_text(
        'model = "gpt"\n[mcp_servers.github]\ncommand = "gh-mcp"\n', encoding="utf-8"
    )

    kinds = _classified(root, "codex")
    assert kinds["prompts/deploy.md"] == "command"
    assert kinds["agents/reviewer.toml"] == "agent"
    assert kinds["AGENTS.md"] == "instruction"

    planned = importing.plan(importing.inspect(root, harness_id="codex"))
    types = sorted((item.component_type, item.declared_key) for item in planned.components)
    assert ("setting", "") in types
    assert ("mcp", "mcp_servers") in types
    mcp = next(item for item in planned.components if item.component_type == "mcp")
    assert mcp.entry_names == ("github",)
    assert mcp.paths == ("config.toml",)


def test_claude_rules_and_hooks_in_settings_classify_by_the_catalogue(tmp_path: Path) -> None:
    root = tmp_path / "claude"
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "style.md").write_text("no hacks\n", encoding="utf-8")
    (root / "settings.json").write_text(
        json.dumps({"model": "claude", "hooks": {"PreToolUse": []}}), encoding="utf-8"
    )

    kinds = _classified(root, "claude-code")
    assert kinds["rules/style.md"] == "instruction"
    planned = importing.plan(importing.inspect(root, harness_id="claude-code"))
    settings_kinds = {
        item.component_type for item in planned.components if "settings.json" in item.paths
    }
    assert settings_kinds == {"setting", "hook"}
    hook = next(item for item in planned.components if item.component_type == "hook")
    assert hook.declared_key == "hooks"
    assert hook.entry_names == ("PreToolUse",)


def test_pi_extensions_and_prompts_classify_by_the_catalogue(tmp_path: Path) -> None:
    root = tmp_path / "pi"
    (root / "extensions" / "bridge").mkdir(parents=True)
    (root / "extensions" / "bridge" / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "prompts").mkdir()
    (root / "prompts" / "fix.md").write_text("fix\n", encoding="utf-8")

    kinds = _classified(root, "pi")
    assert kinds["extensions/bridge/manifest.json"] == "plugin"
    assert kinds["prompts/fix.md"] == "command"


def test_antigravity_workflows_and_hooks_classify_by_the_catalogue(tmp_path: Path) -> None:
    root = tmp_path / "gemini"
    (root / "config" / "global_workflows").mkdir(parents=True)
    (root / "config" / "global_workflows" / "release.md").write_text("go\n", encoding="utf-8")
    (root / "config" / "hooks.json").write_text("{}", encoding="utf-8")

    kinds = _classified(root, "antigravity")
    assert kinds["config/global_workflows/release.md"] == "command"
    assert kinds["config/hooks.json"] == "hook"


def test_cursor_local_plugins_are_one_component_each(tmp_path: Path) -> None:
    root = tmp_path / "cursor"
    for name in ("alpha", "beta"):
        place = root / "plugins" / "local" / name / ".cursor-plugin"
        place.mkdir(parents=True)
        (place / "plugin.json").write_text("{}", encoding="utf-8")
    (root / "rules").mkdir()
    (root / "rules" / "tone.mdc").write_text("calm\n", encoding="utf-8")
    (root / "hooks.json").write_text("{}", encoding="utf-8")

    planned = importing.plan(importing.inspect(root, harness_id="cursor"))
    plugins = [item for item in planned.components if item.component_type == "plugin"]
    assert len(plugins) == 2
    assert {item.paths[0].split("/")[2] for item in plugins} == {"alpha", "beta"}
    kinds = _classified(root, "cursor")
    assert kinds["rules/tone.mdc"] == "instruction"
    assert kinds["hooks.json"] == "hook"


def test_grok_toml_mcp_is_a_contribution_and_its_artifact_is_the_key(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The registered artifact holds the servers, scrubbed — never the file."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    root = tmp_path / "grok"
    root.mkdir()
    (root / "config.toml").write_text(
        "# the person's own comment\n"
        'model = "grok-4"\n'
        "[mcp_servers.github]\n"
        'command = "gh-mcp"\n'
        "[mcp_servers.github.env]\n"
        f'GITHUB_TOKEN = "{SECRET}"\n',
        encoding="utf-8",
    )
    found = importing.inspect(root, harness_id="grok-build")
    planned = importing.plan(found)
    imported = importing.register_graph(
        registry,
        found,
        expected_plan_digest=planned.plan_digest,
        target_id="pair_grok",
        provider_ref="slot-202609010000",
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    assert len(imported.component_ids) == 2

    from ai_stp_cli.local import content as content_store

    artifacts: dict[str, str] = {}
    for component_id in imported.component_ids:
        stored = revisions.head(registry, component_id)
        assert stored is not None
        facts = stored.envelope.model_dump(mode="json")["facts"]
        digest = facts["content_digest"]["value"]
        payload = content_store.get(registry, digest)
        assert payload is not None
        artifacts[facts["component_type"]["value"]] = payload.decode("utf-8")
        if facts["component_type"]["value"] == "mcp":
            assert facts["native_ids"]["value"] == ["github"]
            assert facts["declared_key"]["value"] == "mcp_servers"
            assert facts["source_locator"]["value"] == "config.toml#mcp_servers"
            assert facts["scope"]["value"] == "global"
            assert str(facts["source_root"]["value"]) == "~/grok"

    assert SECRET not in artifacts["mcp"]
    assert SECRET not in artifacts["setting"]
    mcp_files = json.loads(artifacts["mcp"])["files"]
    assert mcp_files[0]["path"] == "config.toml#mcp_servers"
    from base64 import b64decode

    value = b64decode(mcp_files[0]["content_base64"]).decode("utf-8")
    assert "github" in value
    assert "model" not in value
    assert importing.REDACTED in value


def test_toml_scrub_keeps_comments_and_removes_environment_values() -> None:
    raw = b'# keep me\nmodel = "grok-4"\n[mcp_servers.x.env]\nA_TOKEN = "live"\nMODEL = "sonnet"\n'
    cleaned, names = importing.scrub(raw, suffix=".toml")
    text = cleaned.decode("utf-8")
    assert "# keep me" in text
    assert "live" not in text
    assert "sonnet" not in text
    assert 'model = "grok-4"' in text
    assert set(names) == {"mcp_servers.x.env.A_TOKEN", "mcp_servers.x.env.MODEL"}


def test_jsonc_scrub_reads_the_dialect_and_removes_the_secret() -> None:
    raw = b'{\n  // a comment\n  "api_key": "live",\n  "model": "big"\n}\n'
    cleaned, names = importing.scrub(raw, suffix=".jsonc")
    document = json.loads(cleaned)
    assert document["api_key"] == importing.REDACTED
    assert document["model"] == "big"
    assert names == ("api_key",)


def test_yaml_scrub_removes_the_secret_and_keeps_the_rest() -> None:
    raw = b"model: big\nauth:\n  token: live\n"
    cleaned, names = importing.scrub(raw, suffix=".yaml")
    assert b"live" not in cleaned
    assert b"model: big" in cleaned
    assert names == ("auth.token",)


def test_a_malformed_structured_file_is_honest_about_not_being_scrubbed(tmp_path: Path) -> None:
    root = tmp_path / "codex"
    root.mkdir()
    (root / "config.toml").write_text("= not toml", encoding="utf-8")
    found = importing.inspect(root, harness_id="codex")
    item = next(entry for entry in found.findings if entry.path == "config.toml")
    assert item.scrub_format == "none"


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
def test_a_symlink_is_refused_and_blocks_a_complete_capture(
    registry: sqlite3.Connection, native: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"secret": "outside"}), encoding="utf-8")
    (native / "linked.json").symlink_to(outside)

    found = importing.inspect(native, harness_id="claude-code")
    item = next(entry for entry in found.findings if entry.path == "linked.json")
    assert item.refused == "link"
    assert item.digest == ""

    backup_id = _backup(registry)
    with pytest.raises(CliFailure) as refused:
        importing.register(
            registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
        )
    assert "linked.json" in str(refused.value.details.get("skipped", ""))


def test_a_hardlink_is_refused_rather_than_captured(native: Path) -> None:
    target = native / "settings.json"
    try:
        os.link(target, native / "twin.json")
    except OSError:
        pytest.skip("this filesystem refuses hardlinks")
    found = importing.inspect(native, harness_id="claude-code")
    refused = {entry.path: entry.refused for entry in found.findings if entry.refused}
    assert refused.get("twin.json") == "hardlink"
    assert refused.get("settings.json") == "hardlink"


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
def test_a_symlinked_directory_is_not_descended_into(native: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "leak.json").write_text(json.dumps({"secret": "outside"}), encoding="utf-8")
    (native / "portal").symlink_to(outside, target_is_directory=True)

    found = importing.inspect(native, harness_id="claude-code")
    assert all("leak.json" not in item.path for item in found.findings)


@pytest.mark.parametrize(
    ("harness_id", "state_file"),
    [
        ("claude-code", ".credentials.json"),
        ("codex", "auth.json"),
        ("pi", "auth.json"),
        ("grok-build", "auth.json"),
        ("grok-build", "sessions/2026-09-01.json"),
        ("cursor", "chats/one.json"),
        ("cursor", "agent-cli-state.json"),
    ],
)
def test_product_state_and_credential_files_are_not_configuration(
    tmp_path: Path, harness_id: str, state_file: str
) -> None:
    """Measured 2026-09-01 on live homes: products keep credentials and
    runtime state inside the configuration root, and import used to capture
    them as authored configuration — `~/.codex/auth.json` holds OAuth tokens.
    """
    root = tmp_path / "home"
    place = root / state_file
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_text(json.dumps({"access_token": SECRET}), encoding="utf-8")
    (root / "kept.json").write_text("{}", encoding="utf-8")

    found = importing.inspect(root, harness_id=harness_id)
    assert [item.path for item in found.findings] == ["kept.json"]


def test_a_backup_reference_must_have_the_providers_shape(
    registry: sqlite3.Connection,
) -> None:
    """`slot-############` is the vendored kit's own pattern for a BackupRef.

    The reference used to be checked for nothing but non-emptiness, so a typo
    registered a recovery path that no provider would ever answer for.
    """
    with pytest.raises(CliFailure) as refused:
        importing.record_backup(
            registry,
            harness_id="claude-code",
            target_id="pair_1",
            provider_ref="provider://backup/typo",
            at=AT,
        )
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"
    assert "slot-" in str(refused.value.details.get("expected", ""))


def test_the_setup_passport_says_the_backup_was_recorded_not_verified(
    registry: sqlite3.Connection, native: Path
) -> None:
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    imported = importing.register(
        registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
    )
    stored = revisions.head(registry, imported.stable_id)
    assert stored is not None
    facts = stored.envelope.model_dump(mode="json")["facts"]
    assert facts["backup_verification"]["value"] == "recorded_unverified"


def test_replaying_the_same_confirmed_plan_returns_the_same_setup(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotency is part of the operation, not a courtesy.

    Measured with five kill-and-retry rounds against one root: every retry of
    the exact same confirmed `plan_digest` minted a fresh setup identity and a
    fresh copy of every component — four complete setups for one directory,
    with nothing saying which one is *the* one. A client that dies after the
    commit and before the answer retries the same digest; the retry must
    return the graph that already exists, not another one beside it.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    root = tmp_path / "claude"
    (root / "skills" / "one").mkdir(parents=True)
    (root / "skills" / "one" / "SKILL.md").write_text("# One\ncontent.\n", encoding="utf-8")

    found = importing.inspect(root, harness_id="claude-code")
    planned = importing.plan(found)
    first = importing.register_graph(
        registry,
        found,
        expected_plan_digest=planned.plan_digest,
        target_id="pair_claude",
        provider_ref="slot-202609010001",
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    second = importing.register_graph(
        registry,
        importing.inspect(root, harness_id="claude-code"),
        expected_plan_digest=planned.plan_digest,
        target_id="pair_claude",
        provider_ref="slot-202609010001",
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )

    assert second.stable_id == first.stable_id
    assert second.component_ids == first.component_ids
    setups = registry.execute("SELECT COUNT(*) FROM entity WHERE kind = 'setup'").fetchone()[0]
    assert setups == 1, "one root, one confirmed plan, one setup"


def test_the_imported_envelope_expands_through_the_one_decoder() -> None:
    """`#63`: the format `impact` could read and the compiler could not.

    `setup import register` stores a captured component as
    `ai-stp-imported-component/1`. `impact._files` held a reader for it;
    `components.expand` — the owner of "what a stored artifact contains" — had
    never been taught the name. So an imported setup released its components,
    composed, confirmed into a real `SetupVersion`, and then refused at
    `install plan` with `the component content format is unsupported`. One
    decoding with two readers, and only one of them taught.

    The bounds are the ones a stored tree already has, because this artifact is
    built from bytes found on somebody's machine.
    """
    from base64 import b64encode

    from ai_stp_cli.local import components, impact

    def envelope(files: list[dict[str, str]]) -> bytes:
        return json.dumps(
            {"format": components.IMPORTED_COMPONENT_FORMAT, "files": files},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    payload = envelope(
        [
            {"path": "AGENTS.md", "content_base64": b64encode(b"# Agents\n").decode("ascii")},
            {
                "path": "config.toml#mcp_servers",
                "content_base64": b64encode(b'[probe]\ncommand = "p"\n').decode("ascii"),
            },
        ]
    )
    expanded = components.expand(payload, components.IMPORTED_COMPONENT_FORMAT)
    assert [item.path for item in expanded] == ["AGENTS.md", "config.toml#mcp_servers"]
    assert expanded[0].content == b"# Agents\n"

    # The second reader is now the same reader: `impact` re-exports the name
    # from its owner instead of holding a second copy of the decoding.
    assert impact.IMPORTED_COMPONENT_FORMAT == components.IMPORTED_COMPONENT_FORMAT

    for refused in (
        [{"path": "/etc/passwd", "content_base64": b64encode(b"x").decode("ascii")}],
        [{"path": "../escape", "content_base64": b64encode(b"x").decode("ascii")}],
        [
            {"path": "twice", "content_base64": b64encode(b"x").decode("ascii")},
            {"path": "twice", "content_base64": b64encode(b"y").decode("ascii")},
        ],
    ):
        with pytest.raises(CliFailure) as corrupt:
            components.expand(envelope(refused), components.IMPORTED_COMPONENT_FORMAT)
        assert corrupt.value.code == "AI_STP_CONFLICT"
