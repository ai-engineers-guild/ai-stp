"""Native MCP result binding, provenance, deduplication, and payload privacy (SPEC-088)."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

from ai_stp_cli.application import usage_outbox
from ai_stp_cli.local import cache, content, installation, managed_diff
from ai_stp_cli.local.database import open_registry
from ai_stp_cli.provider import usage_hooks
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports import (
    ComponentVersionPassport,
    seal_adaptation,
    seal_envelope,
)

CREATED = "2026-09-26T10:00:00.000Z"
DIGEST = "sha256:" + "a" * 64


def _create_mcp_passport(
    component_id: str,
    harness: str = "codex",
    scope: str = "project",
    native_ids: list[str] | None = None,
    component_type: str = "mcp",
) -> tuple[ComponentVersionPassport, str]:
    artifact = {"digest": DIGEST, "size_bytes": 128}
    license_info = {"spdx_id": "MIT", "redistribution_allowed": True}
    harness_target = "grok-build" if harness in {"grok", "grok-build"} else harness

    adaptation = seal_adaptation(
        {
            "harness_id": harness_target,
            "implementation_mode": "native",
            "source_artifact": None,
            "transform": None,
            "logical_component_type": component_type,
            "scope_adaptations": [
                {
                    "scope": scope,
                    "projection_format": "ai-stp-adaptation-projection/1",
                    "projection_artifact": dict(artifact),
                    "provider_component_kind": component_type,
                    "projection_kind": "native_files",
                    "required_surface": {
                        "profile_id": f"{harness_target}/native/1",
                        "profile_digest": DIGEST,
                        "bundle_format": "ai-stp-bundle/1",
                    },
                    "members": [
                        {
                            "path": f"members/{component_id}.json",
                            "object_type": "file",
                            "mode": 420,
                            "content_artifact": dict(artifact),
                            "native_ids": list(native_ids or ["mcp__github__create_issue"]),
                            "content_format": "application/json",
                            "ownership": "whole",
                            "write_semantics": "replace",
                            "withdrawal_semantics": "remove_path",
                        }
                    ],
                    "technical_support": "supported",
                }
            ],
        }
    )

    data: dict[str, JsonValue] = {
        "kind": "component",
        "stable_id": component_id,
        "parent_revision_ids": [],
        "owner_id": new_id("account"),
        "created_at": CREATED,
        "name": f"test-{component_id}",
        "description": "Test MCP component.",
        "version": "1.0",
        "tags": ["test"],
        "artifact": dict(artifact),
        "license": dict(license_info),
        "component_type": component_type,
        "origin_harness_id": harness_target,
        "adaptations": [cast(JsonValue, adaptation.model_dump(mode="json"))],
    }
    sealed = seal_envelope(data)
    passport_doc = sealed.model_dump(mode="json")
    passport = ComponentVersionPassport.model_validate(passport_doc)
    passport_digest = digest_canonical("ai-stp:passport:v1", passport.model_dump(mode="json"))
    return passport, passport_digest


class _TestEnvironment:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harness: str = "codex"):
        self.tmp_path = tmp_path
        self.registry_path = tmp_path / "registry.sqlite3"
        self.outbox_path = tmp_path / "outbox.sqlite3"
        self.target_dir = tmp_path / "target"
        self.target_dir.mkdir(parents=True, exist_ok=True)

        self.organization_id = new_id("organization")
        self.project_id = new_id("remote_project")
        self.local_project_id = new_id("project")
        self.account_id = new_id("account")
        self.device_id = new_id("device")
        self.setup_id = new_id("setup")
        self.component_id = new_id("component")
        self.harness = harness
        self.scope = "project"

        # Passports and digests
        native_ids = (
            ["mcp__github__create_issue", "github"]
            if harness == "codex"
            else ["github__create_issue", "github"]
        )
        self.passport, self.component_passport_digest = _create_mcp_passport(
            self.component_id,
            harness=harness,
            scope=self.scope,
            native_ids=native_ids,
        )
        self.setup_passport_digest = DIGEST

        # Target member file
        self.member_path = f"members/{self.component_id}.json"
        member_file = self.target_dir / self.member_path
        member_file.parent.mkdir(parents=True, exist_ok=True)
        member_content = b'{"status": "installed"}\n'
        member_file.write_bytes(member_content)
        self.member_digest = "sha256:" + hashlib.sha256(member_content).hexdigest()

        # Bundle archive
        bundle_doc: dict[str, Any] = {
            "managed_paths": [self.member_path],
            "files": [{"path": self.member_path, "digest": self.member_digest}],
            "setup": {
                "stable_id": self.setup_id,
                "version": "1.0",
                "passport_digest": self.setup_passport_digest,
            },
            "component_adaptations": [
                {
                    "stable_id": self.component_id,
                    "version": "1.0",
                    "passport_digest": self.component_passport_digest,
                    "provider_component_kind": "setting" if harness == "grok-build" else "mcp",
                    "member_paths": [self.member_path],
                }
            ],
            "target_scope": self.scope,
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("bundle.json", json.dumps(bundle_doc))
        self.archive_path = tmp_path / "bundle.zip"
        self.archive_path.write_bytes(buffer.getvalue())
        self.bundle_artifact_digest = (
            "sha256:" + hashlib.sha256(self.archive_path.read_bytes()).hexdigest()
        )

        monkeypatch.setattr(cache, "stored_raw_artifact", Mock(return_value=self.archive_path))

        # Setup registry and installation
        with closing(open_registry(self.registry_path)) as connection:
            self._init_registry(connection)

    def _init_registry(self, connection: sqlite3.Connection) -> None:
        at = CREATED
        # Store component in object_version and revision
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
            (self.component_id, at),
        )
        connection.execute(
            "INSERT INTO revision (revision_id, stable_id, content, device_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                self.passport.revision_id,
                self.component_id,
                json.dumps(self.passport.model_dump(mode="json")),
                self.device_id,
                at,
            ),
        )
        connection.execute(
            "INSERT INTO object_version "
            "(stable_id, version, major, minor, passport_digest, revision_id, created_at) "
            "VALUES (?, '1.0', 1, 0, ?, ?, ?)",
            (self.component_id, self.component_passport_digest, self.passport.revision_id, at),
        )

        # Propose, bind, and verify installation
        target_id = f"{self.local_project_id}:{self.harness}"
        plan = installation.propose(
            connection,
            action="install",
            author=self.account_id,
            target_id=target_id,
            expected_target_digest=DIGEST,
            provider_version="1.0.0",
            effects=("install mcp component",),
            recovery_action="restore",
            idempotency_key="test-install-key",
            at=at,
            expires_at="2099-01-01T00:00:00.000Z",
            provider_target=str(self.target_dir),
            bundle_artifact_digest=self.bundle_artifact_digest,
            setup_stable_id=self.setup_id,
            setup_version="1.0",
        )
        self.operation_id = plan.operation_id
        installation.bind_corporate(
            connection,
            self.operation_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            account_id=self.account_id,
            device_id=self.device_id,
            scope=self.scope,
            at=at,
        )
        installation.approve(connection, self.operation_id, plan_digest=plan.digest, at=at)
        installation.begin(connection, self.operation_id, observed_target_digest=DIGEST, at=at)
        installation.applied(connection, self.operation_id, at=at)
        installation.verify(
            connection,
            self.operation_id,
            postconditions_met=True,
            observed_target_digest=DIGEST,
            at=at,
        )


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _TestEnvironment:
    return _TestEnvironment(tmp_path, monkeypatch, harness="codex")


@pytest.fixture
def grok_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _TestEnvironment:
    return _TestEnvironment(tmp_path, monkeypatch, harness="grok-build")


def _payload(harness: str, *, failed: bool = False) -> dict[str, object]:
    response = {"content": [{"type": "text", "text": "PRIVATE_OUTPUT"}], "isError": failed}
    if harness == "codex":
        return {
            "hook_event_name": "PostToolUse",
            "session_id": "session_1",
            "tool_use_id": "call_1",
            "tool_name": "mcp__github__create_issue",
            "tool_response": response,
            "tool_input": {"private": "PRIVATE_ARGUMENT"},
        }
    return {
        "hookEventName": "post_tool_use_failure" if failed else "post_tool_use",
        "hook_event_name": "PostToolUseFailure" if failed else "PostToolUse",
        "sessionId": "session_1",
        "toolUseId": "call_1",
        "toolName": "github__create_issue",
        "toolResult": {
            "type": "MCP",
            "server_name": "github",
            "tool_name": "create_issue",
            "output": {"OkayOutput": "PRIVATE_OUTPUT"},
            "is_error": failed,
        },
        "toolResultTruncated": False,
        "toolInput": {"private": "PRIVATE_ARGUMENT"},
    }


def _record(env: _TestEnvironment, payload: dict[str, object]) -> str:
    with closing(open_registry(env.registry_path)) as connection:
        return usage_hooks.record_hook_usage(
            connection,
            env.operation_id,
            env.account_id,
            env.device_id,
            payload,
            outbox_path=env.outbox_path,
        )


@pytest.mark.parametrize("harness", ["codex", "grok-build"])
@pytest.mark.parametrize("failed", [False, True])
def test_native_result_is_bound_deduplicated_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    harness: str,
    failed: bool,
) -> None:
    env = _TestEnvironment(tmp_path, monkeypatch, harness)
    payload = _payload(harness, failed=failed)
    assert _record(env, payload) == "queued"
    assert _record(env, payload) == "duplicate"
    with closing(usage_outbox.connect(env.outbox_path)) as connection:
        rows = connection.execute("SELECT payload FROM usage_outbox").fetchall()
    assert len(rows) == 1
    serialized = rows[0][0]
    assert "PRIVATE" not in serialized and str(tmp_path) not in serialized
    event = json.loads(serialized)
    assert event["component"]["kind"] == "mcp"  # Grok projects MCP as a provider setting.
    assert event["project_id"] == env.project_id  # Remote, not the local target identifier.
    assert event["setup"]["stable_id"] == env.setup_id
    assert event["outcome"] == ("failed" if failed else "succeeded")
    assert event["source"] == "native_hook"


@pytest.mark.parametrize(
    "patch",
    [
        {"hook_event_name": "PreToolUse"},
        {"hook_event_name": "PostToolUseFailure"},
        {"session_id": ""},
        {"tool_use_id": ""},
        {"tool_name": "shell"},
        {"tool_name": "mcp__unknown__tool"},
        {"tool_response": None},
        {"tool_response": {"permission_denied": True}},
        {"tool_response": "success"},
        {"tool_response": {"content": [], "isError": "false"}},
    ],
)
def test_unproven_invocation_is_dropped(env: _TestEnvironment, patch: dict[str, object]) -> None:
    assert _record(env, {**_payload("codex"), **patch}) == "dropped"


@pytest.mark.parametrize(
    "change", ["dispatch", "server", "truncated", "wrong_envelope", "failure_without_result"]
)
def test_grok_rejects_unproven_or_mismatched_results(
    grok_env: _TestEnvironment, change: str
) -> None:
    payload = _payload("grok-build")
    response = payload["toolResult"]
    assert isinstance(response, dict)
    response = cast(dict[str, object], response)
    if change == "dispatch":
        payload["hookEventName"] = "post_tool_use_failure"
        response.update(output={"Error": "PRIVATE_DISPATCH_FAILURE"}, is_error=True)
    elif change == "server":
        response["server_name"] = "another"
    elif change == "truncated":
        payload["toolResultTruncated"] = True
    elif change == "failure_without_result":
        payload["hookEventName"] = "post_tool_use_failure"
        payload.pop("toolResult")
        payload["error"] = "PRIVATE_TOOL_ERROR"
        payload["durationMs"] = 10
        payload["isInterrupt"] = False
    else:
        payload["toolResult"] = {"content": [], "isError": False}
    assert _record(grok_env, payload) == "dropped"


@pytest.mark.parametrize("change", ["unowned", "owned", "missing", "malformed", "whole"])
def test_contribution_verification_preserves_unowned_host_settings(
    env: _TestEnvironment, change: str
) -> None:
    with closing(open_registry(env.registry_path)) as connection:
        expected = b'{"command":"echo"}'
        stored = content.put(connection, expected, at=CREATED)
        adaptation = env.passport.adaptations[0]
        projection = adaptation.scope_adaptations[0]
        artifact = projection.members[0].content_artifact
        assert artifact is not None
        member = projection.members[0].model_copy(
            update={
                "content_artifact": artifact.model_copy(
                    update={"digest": stored.digest, "size_bytes": len(expected)}
                ),
                "ownership": "whole" if change == "whole" else "contribution",
                "ownership_key": "mcp_servers",
                "parser_id": "json/1",
            }
        )
        passport = env.passport.model_copy(
            update={
                "adaptations": [
                    adaptation.model_copy(
                        update={
                            "scope_adaptations": [
                                projection.model_copy(update={"members": [member]})
                            ]
                        }
                    )
                ]
            }
        )
        host: dict[str, object] = {"mcp_servers": {"command": "echo"}, "theme": "changed"}
        if change == "owned":
            host["mcp_servers"] = {"command": "another-command"}
        elif change == "missing":
            del host["mcp_servers"]
        (env.target_dir / env.member_path).write_text(
            "not JSON" if change == "malformed" else json.dumps(host), encoding="utf8"
        )
        unchanged = managed_diff.unchanged_contributions(
            connection, env.target_dir, passport, harness=env.harness, scope=env.scope
        )
        assert unchanged == (frozenset({env.member_path}) if change == "unowned" else frozenset())


@pytest.mark.parametrize(
    "change", ["account", "device", "missing", "modified", "removed", "stale", "passport"]
)
def test_invalid_provenance_is_dropped(env: _TestEnvironment, change: str) -> None:
    if change in {"missing", "modified"}:
        path = env.target_dir / env.member_path
        if change == "missing":
            path.unlink()
        else:
            path.write_text("modified", encoding="utf-8")
    else:
        with closing(open_registry(env.registry_path)) as connection:
            if change in {"account", "device"}:
                connection.execute(
                    f"UPDATE operation_corporate_binding SET {change}_id = 'another'"
                )
            elif change == "removed":
                connection.execute("UPDATE operation_plan SET action = 'remove'")
            elif change == "stale":
                connection.execute("UPDATE operation SET state = 'stale'")
            else:
                connection.execute(
                    "UPDATE revision SET content = '{}' WHERE revision_id = ?",
                    (env.passport.revision_id,),
                )
            connection.commit()
    assert _record(env, _payload("codex")) == "dropped"


def test_later_mutation_invalidates_old_binding_without_new_corporate_binding(
    env: _TestEnvironment,
) -> None:
    with closing(open_registry(env.registry_path)) as connection:
        at = "2026-09-26T11:00:00.000Z"
        plan = installation.propose(
            connection,
            action="remove",
            author=env.account_id,
            target_id=f"{env.local_project_id}:{env.harness}",
            expected_target_digest=DIGEST,
            provider_version="1.0.0",
            effects=("remove",),
            recovery_action="restore",
            idempotency_key="later",
            at=at,
            expires_at="2099-01-01T00:00:00.000Z",
            provider_target=str(env.target_dir),
        )
        installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=at)
        installation.begin(connection, plan.operation_id, observed_target_digest=DIGEST, at=at)
        connection.commit()
    assert _record(env, _payload("codex")) == "dropped"


def test_correlation_has_no_delimiter_collision() -> None:
    assert usage_hooks.derive_event_id("a:b", "c", "d") != usage_hooks.derive_event_id(
        "a", "b:c", "d"
    )


def test_hook_resolver_uses_current_project_link(env: _TestEnvironment) -> None:
    with closing(open_registry(env.registry_path)) as connection:
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
            (env.local_project_id, CREATED),
        )
        connection.execute(
            "INSERT INTO project_root (root, stable_id) VALUES (?, ?)",
            (str(env.target_dir), env.local_project_id),
        )
        connection.execute(
            "INSERT INTO project_link (local_project_id, organization_id, remote_project_id, "
            "state, local_revision, remote_revision, link_revision, updated_at) "
            "VALUES (?, ?, ?, 'linked', 'r1', 'r1', 1, ?)",
            (env.local_project_id, env.organization_id, env.project_id, CREATED),
        )
        assert (
            usage_hooks.resolve_operation(
                connection, env.account_id, env.device_id, "codex", "project", env.target_dir
            )
            == env.operation_id
        )
        assert (
            usage_hooks.resolve_operation(
                connection, env.account_id, env.device_id, "codex", "project", env.tmp_path
            )
            is None
        )
        connection.execute("UPDATE project_link SET remote_project_id = 'another'")
        assert (
            usage_hooks.resolve_operation(
                connection, env.account_id, env.device_id, "codex", "project", env.target_dir
            )
            is None
        )
