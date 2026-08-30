"""Importing native configuration: read-only, secret-free, and honest about it."""

import json
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
        provider_ref="provider://backup/2026-08-08",
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
    assert held.provider_ref == "provider://backup/2026-08-08"
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


def test_an_oversized_file_does_not_prevent_registration(
    registry: sqlite3.Connection, native: Path
) -> None:
    """The size bound is a declared exclusion, not a gap in what was seen."""
    huge = native / "huge.json"
    huge.write_text("x" * (importing.MAX_FILE_BYTES + 1), encoding="utf-8")
    backup_id = _backup(registry)
    found = importing.inspect(native, harness_id="claude-code")
    assert found.oversized == ("huge.json",)
    assert found.unreadable == ()

    imported = importing.register(
        registry, found, backup_id=backup_id, owner_id=OWNER, device_id=DEVICE, at=AT
    )
    # Previously this raised AI_STP_PRECONDITION_FAILED, which made any harness
    # root holding a cache blob impossible to import at all.
    assert imported.stable_id
    assert imported.backup_id == backup_id


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
            "backup-ref": "provider://backup/2026-08-08",
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
                "backup-ref": "provider://backup/stale",
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
        "backup-ref": "provider://backup/unconfirmed",
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
