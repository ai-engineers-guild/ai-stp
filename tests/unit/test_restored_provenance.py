"""Rollback coordinates come from an exact prior bundle, or they stay unknown."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai_stp_cli.application import install, installation_inventory, installation_usage
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    cache,
    installation,
    managed_diff,
    passports,
    project_passport,
    restored_provenance,
)
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.provider import conformance, invocation, operation_v3, protocol_v3, usage_hooks
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

S0 = "sha256:" + "a0" * 32
S1 = "sha256:" + "a1" * 32
S2 = "sha256:" + "a2" * 32
S3 = "sha256:" + "a3" * 32
N1 = "sha256:" + "b1" * 32
N2 = "sha256:" + "b2" * 32
N3 = "sha256:" + "b3" * 32
N4 = "sha256:" + "b4" * 32


class _World:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp_path = tmp_path
        self.target = tmp_path / "target"
        self.target.mkdir()
        self.plans: dict[str, Path] = {}
        self.artifacts: dict[str, Path] = {}
        self.clock = 0
        self.organization_id = new_id("organization")
        self.project_id = new_id("remote_project")
        self.account_id = new_id("account")
        self.device_id = new_id("device")
        self.local_project_id = new_id("project")
        self.target_id = f"{self.local_project_id}:codex"
        self.scope = "project"
        self.connection = open_registry(tmp_path / "registry.db")

        def plan_path(digest: str) -> Path | None:
            return self.plans.get(digest)

        def artifact_path(digest: str) -> Path | None:
            return self.artifacts.get(digest)

        monkeypatch.setattr(cache, "stored_provider_plan", plan_path)
        monkeypatch.setattr(cache, "stored_raw_artifact", artifact_path)

    def close(self) -> None:
        self.connection.close()

    def stamp(self) -> str:
        self.clock += 1
        return f"2026-09-26T10:{self.clock:02d}:00.000Z"

    def bundle(self, setup_id: str, components: list[tuple[str, str, str]]) -> str:
        member = "members/tool.json"
        payload = b'{"status":"installed"}\n'
        (self.target / "members").mkdir(exist_ok=True)
        (self.target / member).write_bytes(payload)
        file_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        document = {
            "managed_paths": [member],
            "files": [{"path": member, "digest": file_digest}],
            "target_scope": self.scope,
            "setup": {"stable_id": setup_id, "version": "1.0", "passport_digest": file_digest},
            "component_adaptations": [
                {
                    "stable_id": stable_id,
                    "version": version,
                    "passport_digest": file_digest,
                    "provider_component_kind": kind,
                    "member_paths": [member],
                }
                for stable_id, version, kind in components
            ],
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("bundle.json", json.dumps(document))
        digest = "sha256:" + hashlib.sha256(buffer.getvalue()).hexdigest()
        path = self.tmp_path / f"{digest.removeprefix('sha256:')}.zip"
        path.write_bytes(buffer.getvalue())
        self.artifacts[digest] = path
        return digest

    def provider_plan(
        self,
        *,
        backup_ref: str | None,
        current: str,
        restore: str | None,
        restore_target: str | None,
    ) -> str:
        artifact: dict[str, JsonValue] = {
            "effects": ["capture the native target"],
            "backup_ref": backup_ref,
            "restore_target_digest": restore_target,
            "native_capture": {
                "roots": ["members/tool.json"],
                "excluded": [],
                "current_digest": current,
                "restore_digest": restore,
            },
        }
        digest = digest_canonical(protocol_v3.PLAN_DOMAIN, artifact)
        path = self.tmp_path / f"{digest.removeprefix('sha256:')}.json"
        path.write_bytes(canonize(artifact))
        self.plans[digest] = path
        return digest

    def settle(
        self,
        *,
        action: str,
        expected: str,
        verified: str,
        key: str,
        bundle: str = "",
        backup: str | None = None,
        setup_id: str = "",
        plan_digest: str = "",
        account_id: str | None = None,
        scope: str | None = None,
    ) -> installation.Plan:
        at = self.stamp()
        plan = installation.propose(
            self.connection,
            action=action,
            author=account_id or self.account_id,
            target_id=self.target_id,
            expected_target_digest=expected,
            provider_version="1.0.0",
            effects=("change the target",),
            recovery_action="restore",
            idempotency_key=key,
            at=at,
            expires_at="2099-01-01T00:00:00.000Z",
            provider_target=str(self.target),
            bundle_artifact_digest=bundle,
            provider_plan_digest=plan_digest,
            setup_stable_id=setup_id,
            setup_version="1.0" if setup_id else "",
        )
        installation.bind_corporate(
            self.connection,
            plan.operation_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            account_id=account_id or self.account_id,
            device_id=self.device_id,
            scope=scope or self.scope,
            at=at,
        )
        installation.approve(self.connection, plan.operation_id, plan_digest=plan.digest, at=at)
        installation.begin(
            self.connection, plan.operation_id, observed_target_digest=expected, at=at
        )
        installation.applied(self.connection, plan.operation_id, at=at, backup_ref=backup)
        installation.verify(
            self.connection,
            plan.operation_id,
            postconditions_met=True,
            observed_target_digest=verified,
            at=at,
        )
        return plan


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    held = _World(tmp_path, monkeypatch)
    yield held
    held.close()


def _kinds(components: Mapping[str, str]):
    def passport(_connection: sqlite3.Connection, binding: managed_diff.ComponentBinding):
        return SimpleNamespace(component_type=components[binding.stable_id], adaptations=[])

    return passport


def test_a_verified_rollback_reuses_the_bundle_captured_before_removal(world: _World) -> None:
    setup_id = new_id("setup")
    component_id = new_id("component")
    bundle = world.bundle(setup_id, [(component_id, "1.0", "mcp")])
    world.settle(
        action="install",
        expected=S0,
        verified=S1,
        key="install",
        bundle=bundle,
        setup_id=setup_id,
        backup="slot-install",
    )
    world.settle(
        action="remove",
        expected=S1,
        verified=S2,
        key="remove",
        backup="slot-selected",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    rollback = world.settle(
        action="rollback",
        expected=S2,
        verified=S1,
        key="rollback",
        backup="slot-before-restore",
        plan_digest=world.provider_plan(
            backup_ref="slot-selected", current=N2, restore=N1, restore_target=S1
        ),
    )

    found = restored_provenance.recovered_bundle(world.connection, rollback.operation_id)

    assert found is not None
    assert found.bundle_artifact_digest == bundle
    assert found.setup_stable_id == setup_id
    stored = world.connection.execute(
        "SELECT backup_ref FROM operation_plan WHERE operation_id = ?",
        (rollback.operation_id,),
    ).fetchone()
    assert stored is not None and stored["backup_ref"] == "slot-before-restore"


def test_digest_drift_ambiguity_account_change_and_partials_stay_unknown(world: _World) -> None:
    bundle = world.bundle(new_id("setup"), [(new_id("component"), "1.0", "mcp")])
    world.settle(
        action="install", expected=S0, verified=S1, key="install", bundle=bundle, backup="slot-i"
    )
    world.settle(
        action="remove",
        expected=S2,
        verified=S3,
        key="drift",
        backup="slot-drift",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    rollback = world.settle(
        action="rollback",
        expected=S3,
        verified=S2,
        key="drift-rollback",
        backup="slot-new",
        plan_digest=world.provider_plan(
            backup_ref="slot-drift", current=N2, restore=N1, restore_target=S2
        ),
    )
    assert restored_provenance.recovered_bundle(world.connection, rollback.operation_id) is None
    drifted = _pending_fact(world, rollback.operation_id)
    assert drifted.action == "rollback"
    assert not drifted.components_complete
    assert drifted.components == []
    assert drifted.setup_stable_id is None
    _managed, _covered, complete = installation_inventory._managed_components(  # pyright: ignore[reportPrivateUsage]
        world.connection,
        organization_id=world.organization_id,
        account_id=world.account_id,
        device_id=world.device_id,
        project_id=world.project_id,
    )
    assert not complete

    world.settle(
        action="remove",
        expected=S3,
        verified=S0,
        key="second-capture",
        backup="slot-drift",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N3, restore=None, restore_target=None
        ),
    )
    assert restored_provenance.recovered_bundle(world.connection, rollback.operation_id) is None
    ambiguous = _pending_fact(world, rollback.operation_id)
    assert not ambiguous.components_complete
    assert ambiguous.components == []


def test_a_rollback_does_not_treat_its_own_backup_column_as_the_selection(world: _World) -> None:
    rollback = world.settle(
        action="rollback",
        expected=S0,
        verified=S1,
        key="self",
        backup="slot-self",
        plan_digest=world.provider_plan(
            backup_ref="slot-self", current=N2, restore=N1, restore_target=S1
        ),
    )
    assert restored_provenance.recovered_bundle(world.connection, rollback.operation_id) is None


def test_a_different_account_and_a_partial_mutation_are_not_provenance(world: _World) -> None:
    bundle = world.bundle(new_id("setup"), [(new_id("component"), "1.0", "mcp")])
    world.settle(
        action="install",
        expected=S0,
        verified=S1,
        key="other-account",
        bundle=bundle,
        account_id=new_id("account"),
    )
    world.settle(
        action="remove",
        expected=S1,
        verified=S2,
        key="remove",
        backup="slot-selected",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    rollback = world.settle(
        action="rollback",
        expected=S2,
        verified=S1,
        key="rollback",
        backup="slot-new",
        plan_digest=world.provider_plan(
            backup_ref="slot-selected", current=N2, restore=N1, restore_target=S1
        ),
    )
    assert restored_provenance.recovered_bundle(world.connection, rollback.operation_id) is None

    world.settle(action="install", expected=S1, verified=S2, key="same-account", bundle=bundle)
    at = world.stamp()
    partial = installation.propose(
        world.connection,
        action="update",
        author=world.account_id,
        target_id=world.target_id,
        expected_target_digest=S2,
        provider_version="1.0.0",
        effects=("change the target",),
        recovery_action="restore",
        idempotency_key="partial",
        at=at,
        expires_at="2099-01-01T00:00:00.000Z",
        provider_target=str(world.target),
    )
    installation.bind_corporate(
        world.connection,
        partial.operation_id,
        organization_id=world.organization_id,
        project_id=world.project_id,
        account_id=world.account_id,
        device_id=world.device_id,
        scope=world.scope,
        at=at,
    )
    installation.approve(world.connection, partial.operation_id, plan_digest=partial.digest, at=at)
    installation.begin(world.connection, partial.operation_id, observed_target_digest=S2, at=at)
    installation.interrupted(
        world.connection, partial.operation_id, at=at, reason="provider timed out"
    )
    world.settle(
        action="remove",
        expected=S2,
        verified=S3,
        key="after-partial",
        backup="slot-after-partial",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N3, restore=None, restore_target=None
        ),
    )
    blocked = world.settle(
        action="rollback",
        expected=S3,
        verified=S2,
        key="blocked-rollback",
        backup="slot-blocked",
        plan_digest=world.provider_plan(
            backup_ref="slot-after-partial", current=N4, restore=N3, restore_target=S2
        ),
    )
    assert restored_provenance.recovered_bundle(world.connection, blocked.operation_id) is None


def test_a_rollback_chain_that_points_at_itself_stays_unknown(world: _World) -> None:
    bundle = world.bundle(new_id("setup"), [(new_id("component"), "1.0", "mcp")])
    world.settle(action="install", expected=S0, verified=S1, key="install", bundle=bundle)
    world.settle(
        action="remove",
        expected=S1,
        verified=S2,
        key="remove",
        backup="slot-1",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    # The inner restore's selected backup is the outer rollback's own column.
    # Following it walks forward in time and must stop.
    world.settle(
        action="rollback",
        expected=S2,
        verified=S1,
        key="inner",
        backup="slot-2",
        plan_digest=world.provider_plan(
            backup_ref="slot-4", current=N2, restore=N4, restore_target=S3
        ),
    )
    world.settle(
        action="update",
        expected=S1,
        verified=S3,
        key="replace",
        bundle=bundle,
        backup="slot-3",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N3, restore=None, restore_target=None
        ),
    )
    outer = world.settle(
        action="rollback",
        expected=S3,
        verified=S1,
        key="outer",
        backup="slot-4",
        plan_digest=world.provider_plan(
            backup_ref="slot-3", current=N4, restore=N3, restore_target=S1
        ),
    )
    assert restored_provenance.recovered_bundle(world.connection, outer.operation_id) is None


def test_nested_rollback_follows_the_rollback_that_produced_the_captured_state(
    world: _World,
) -> None:
    setup_id = new_id("setup")
    component_id = new_id("component")
    original = world.bundle(setup_id, [(component_id, "1.0", "mcp")])
    replacement = world.bundle(new_id("setup"), [(new_id("component"), "1.1", "mcp")])
    world.settle(
        action="install",
        expected=S0,
        verified=S1,
        key="install",
        bundle=original,
        setup_id=setup_id,
    )
    world.settle(
        action="remove",
        expected=S1,
        verified=S2,
        key="remove",
        backup="slot-1",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    world.settle(
        action="rollback",
        expected=S2,
        verified=S1,
        key="restore-original",
        backup="slot-2",
        plan_digest=world.provider_plan(
            backup_ref="slot-1", current=N2, restore=N1, restore_target=S1
        ),
    )
    world.settle(
        action="update",
        expected=S1,
        verified=S3,
        key="replace",
        bundle=replacement,
        backup="slot-3",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N3, restore=None, restore_target=None
        ),
    )
    outer = world.settle(
        action="rollback",
        expected=S3,
        verified=S1,
        key="restore-again",
        backup="slot-4",
        plan_digest=world.provider_plan(
            backup_ref="slot-3", current=N4, restore=N3, restore_target=S1
        ),
    )

    found = restored_provenance.recovered_bundle(world.connection, outer.operation_id)

    assert found is not None
    assert found.bundle_artifact_digest == original
    assert found.setup_stable_id == setup_id
    assert found.source_operation_id != outer.operation_id


def test_facts_inventory_and_hooks_use_the_recovered_bundle(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_id = new_id("setup")
    component_id = new_id("component")
    extra_id = new_id("component")
    bundle = world.bundle(setup_id, [(component_id, "1.0", "mcp"), (extra_id, "1.1", "skill")])
    monkeypatch.setattr(
        managed_diff,
        "component_passport",
        _kinds({component_id: "mcp", extra_id: "skill"}),
    )
    installed = world.settle(
        action="install",
        expected=S0,
        verified=S1,
        key="install",
        bundle=bundle,
        setup_id=setup_id,
    )
    facts = installation_usage.pending_facts(
        world.connection,
        organization_id=world.organization_id,
        account_id=world.account_id,
        device_id=world.device_id,
    )
    assert len(facts) == 1
    assert facts[0].components_complete
    assert {(item.stable_id, item.version, item.kind) for item in facts[0].components} == {
        (component_id, "1.0", "mcp"),
        (extra_id, "1.1", "skill"),
    }
    world.connection.execute(
        "UPDATE operation_corporate_binding SET delivered_at = CURRENT_TIMESTAMP "
        "WHERE operation_id = ?",
        (installed.operation_id,),
    )
    world.settle(
        action="remove",
        expected=S1,
        verified=S2,
        key="remove",
        backup="slot-selected",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    rollback = world.settle(
        action="rollback",
        expected=S2,
        verified=S1,
        key="rollback",
        backup="slot-new",
        plan_digest=world.provider_plan(
            backup_ref="slot-selected", current=N2, restore=N1, restore_target=S1
        ),
    )
    projected = installation_usage.pending_facts(
        world.connection,
        organization_id=world.organization_id,
        account_id=world.account_id,
        device_id=world.device_id,
    )
    assert [fact.action for fact in projected] == ["remove", "rollback"]
    assert not projected[0].components_complete
    assert projected[1].operation_id == rollback.operation_id
    assert projected[1].components_complete
    assert projected[1].setup_stable_id == setup_id
    assert {item.stable_id for item in projected[1].components} == {component_id, extra_id}

    managed, _covered, complete = installation_inventory._managed_components(  # pyright: ignore[reportPrivateUsage]
        world.connection,
        organization_id=world.organization_id,
        account_id=world.account_id,
        device_id=world.device_id,
        project_id=world.project_id,
    )
    assert complete
    assert {(item.stable_id, item.state) for item in managed} == {
        (component_id, "present"),
        (extra_id, "present"),
    }

    member = SimpleNamespace(native_ids=("mcp__github__create_issue", "github"))
    scope = SimpleNamespace(scope="project", members=(member,))

    def adaptation(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(scope_adaptations=(scope,))

    def unchanged(*_args: object, **_kwargs: object) -> frozenset[str]:
        return frozenset()

    monkeypatch.setattr(usage_hooks, "adaptation_for", adaptation)
    monkeypatch.setattr(managed_diff, "unchanged_contributions", unchanged)
    queued = usage_hooks.record_hook_usage(
        world.connection,
        rollback.operation_id,
        world.account_id,
        world.device_id,
        {
            "hook_event_name": "PostToolUse",
            "session_id": "session_1",
            "tool_use_id": "call_1",
            "tool_name": "mcp__github__create_issue",
            "tool_response": {"content": [{"type": "text", "text": "PRIVATE"}], "isError": False},
        },
        outbox_path=world.tmp_path / "outbox.sqlite3",
    )
    assert queued == "queued"


def _pending_fact(world: _World, operation_id: str):
    facts = installation_usage.pending_facts(
        world.connection,
        organization_id=world.organization_id,
        account_id=world.account_id,
        device_id=world.device_id,
    )
    matched = [fact for fact in facts if fact.operation_id == operation_id]
    assert len(matched) == 1
    return matched[0]


def _removed_after_install(
    world: _World, prefix: str, *, scope: str | None = None
) -> tuple[str, str, str]:
    setup_id = new_id("setup")
    component_id = new_id("component")
    bundle = world.bundle(setup_id, [(component_id, "1.0", "mcp")])
    world.settle(
        action="install",
        expected=S0,
        verified=S1,
        key=f"{prefix}-install",
        bundle=bundle,
        setup_id=setup_id,
        backup=f"{prefix}-install-slot",
        scope=scope,
    )
    world.settle(
        action="remove",
        expected=S1,
        verified=S2,
        key=f"{prefix}-remove",
        backup=f"{prefix}-selected",
        scope=scope,
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    return bundle, setup_id, component_id


def _open_rollback(world: _World, *, key: str, backup: str) -> installation.Plan:
    return installation.propose(
        world.connection,
        action="rollback",
        author=world.account_id,
        target_id=world.target_id,
        expected_target_digest=S2,
        provider_version="1.0.0",
        effects=("change the target",),
        recovery_action="restore",
        idempotency_key=key,
        at=world.stamp(),
        expires_at="2099-01-01T00:00:00.000Z",
        provider_target=str(world.target),
        provider_plan_digest=world.provider_plan(
            backup_ref=backup, current=N2, restore=N1, restore_target=S1
        ),
    )


def _settle_open(world: _World, plan: installation.Plan, *, backup: str) -> None:
    at = world.stamp()
    installation.approve(world.connection, plan.operation_id, plan_digest=plan.digest, at=at)
    installation.begin(world.connection, plan.operation_id, observed_target_digest=S2, at=at)
    installation.applied(world.connection, plan.operation_id, at=at, backup_ref=backup)
    installation.verify(
        world.connection,
        plan.operation_id,
        postconditions_met=True,
        observed_target_digest=S1,
        at=at,
    )


def _bind(world: _World, operation_id: str, scope: str) -> None:
    installation.bind_corporate(
        world.connection,
        operation_id,
        organization_id=world.organization_id,
        project_id=world.project_id,
        account_id=world.account_id,
        device_id=world.device_id,
        scope=scope,
        at=world.stamp(),
    )


def test_a_plan_records_scope_once_without_changing_its_digest(world: _World) -> None:
    plan = installation.propose(
        world.connection,
        action="remove",
        author=world.account_id,
        target_id=world.target_id,
        expected_target_digest=S0,
        provider_version="1.0.0",
        effects=("change the target",),
        recovery_action="restore",
        idempotency_key="scope",
        at=world.stamp(),
        expires_at="2099-01-01T00:00:00.000Z",
        provider_target=str(world.target),
    )
    assert installation.target_scope(world.connection, plan.operation_id) == ""
    assert installation.corporate_scope(world.connection, plan.operation_id, None) == "unknown"
    installation.remember_target_scope(world.connection, plan.operation_id, "global")
    installation.remember_target_scope(world.connection, plan.operation_id, "project")
    assert installation.target_scope(world.connection, plan.operation_id) == "global"
    assert installation.plan(world.connection, plan.operation_id).digest == plan.digest
    assert installation.corporate_scope(world.connection, plan.operation_id, None) == "global"
    assert installation.corporate_scope(world.connection, plan.operation_id, "project") == "project"
    assert (
        installation.corporate_scope(world.connection, plan.operation_id, "user_root") == "global"
    )
    assert installation.corporate_scope(world.connection, "missing", None) == "unknown"
    with pytest.raises(CliFailure, match="invalid planned installation scope"):
        installation.remember_target_scope(world.connection, plan.operation_id, "home")
    assert installation.target_scope(world.connection, plan.operation_id) == "global"


def test_a_sourceless_rollback_recovers_when_the_plan_recorded_its_scope(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, setup_id, component_id = _removed_after_install(world, "scoped", scope="global")
    monkeypatch.setattr(managed_diff, "component_passport", _kinds({component_id: "mcp"}))
    rollback = _open_rollback(world, key="scoped-rollback", backup="scoped-selected")
    installation.remember_target_scope(world.connection, rollback.operation_id, "global")
    scope = installation.corporate_scope(world.connection, rollback.operation_id, None)
    _bind(world, rollback.operation_id, scope)
    _settle_open(world, rollback, backup="scoped-before-restore")

    found = restored_provenance.recovered_bundle(world.connection, rollback.operation_id)
    fact = _pending_fact(world, rollback.operation_id)

    assert scope == "global"
    assert found is not None
    assert found.bundle_artifact_digest == bundle
    assert found.setup_stable_id == setup_id
    assert found.setup_version == "1.0"
    assert fact.scope == "global"
    assert fact.components_complete
    assert fact.setup_stable_id == setup_id
    assert fact.setup_version == "1.0"
    assert [(item.stable_id, item.version, item.kind) for item in fact.components] == [
        (component_id, "1.0", "mcp")
    ]


def test_a_sourceless_rollback_without_a_recorded_scope_stays_unknown(world: _World) -> None:
    _removed_after_install(world, "unscoped")
    rollback = _open_rollback(world, key="unscoped-rollback", backup="unscoped-selected")
    scope = installation.corporate_scope(world.connection, rollback.operation_id, None)
    _bind(world, rollback.operation_id, scope)
    _settle_open(world, rollback, backup="unscoped-before-restore")

    fact = _pending_fact(world, rollback.operation_id)

    assert scope == "unknown"
    assert restored_provenance.recovered_bundle(world.connection, rollback.operation_id) is None
    assert fact.scope == "unknown"
    assert not fact.components_complete
    assert fact.components == []
    assert fact.setup_stable_id is None
    assert fact.setup_version is None
    assert (
        usage_hooks.record_hook_usage(
            world.connection,
            rollback.operation_id,
            world.account_id,
            world.device_id,
            {
                "hook_event_name": "PostToolUse",
                "session_id": "session_1",
                "tool_use_id": "call_1",
                "tool_name": "mcp__github__create_issue",
                "tool_response": {
                    "content": [{"type": "text", "text": "PRIVATE"}],
                    "isError": False,
                },
            },
        )
        == "dropped"
    )


def test_a_prior_removal_leaves_the_rollback_fact_incomplete(world: _World) -> None:
    bundle = world.bundle(new_id("setup"), [(new_id("component"), "1.0", "mcp")])
    world.settle(
        action="install",
        expected=S0,
        verified=S1,
        key="before-empty",
        bundle=bundle,
        setup_id=new_id("setup"),
    )
    world.settle(
        action="remove",
        expected=S1,
        verified=S2,
        key="empty",
        backup="slot-empty",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N1, restore=None, restore_target=None
        ),
    )
    world.settle(
        action="update",
        expected=S2,
        verified=S3,
        key="after-empty",
        bundle=bundle,
        backup="slot-selected",
        plan_digest=world.provider_plan(
            backup_ref=None, current=N2, restore=None, restore_target=None
        ),
    )
    rollback = world.settle(
        action="rollback",
        expected=S3,
        verified=S2,
        key="restore-empty",
        backup="slot-new",
        plan_digest=world.provider_plan(
            backup_ref="slot-selected", current=N3, restore=N2, restore_target=S2
        ),
    )

    fact = _pending_fact(world, rollback.operation_id)
    _managed, _covered, complete = installation_inventory._managed_components(  # pyright: ignore[reportPrivateUsage]
        world.connection,
        organization_id=world.organization_id,
        account_id=world.account_id,
        device_id=world.device_id,
        project_id=world.project_id,
    )

    assert restored_provenance.recovered_bundle(world.connection, rollback.operation_id) is None
    assert fact.action == "rollback"
    assert not fact.components_complete
    assert fact.components == []
    assert fact.setup_stable_id is None
    assert not complete


def _scope_digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _argv_scope(arguments: Sequence[str]) -> str:
    if "--target-scope" not in arguments:
        return "global"
    return arguments[arguments.index("--target-scope") + 1]


def _projection_profile(profile_id: str, scope: str | None) -> dict[str, JsonValue]:
    digest_input: dict[str, JsonValue] = {
        "profile_id": profile_id,
        "component_kinds": ["skill"],
        "projection_kinds": ["native_files"],
        "native_namespaces": ["skills"],
        "bundle_formats": ["ai-stp-bundle/2"],
        "max_files": 10,
        "max_bytes": 1000,
    }
    if scope is not None:
        digest_input["target_scope"] = scope
    return {
        **digest_input,
        "digest": digest_canonical(protocol_v3.PROJECTION_DOMAIN, digest_input),
    }


@pytest.mark.parametrize("scope", ["project", "user_root"])
def test_a_sourceless_rollback_apply_reads_status_at_the_planned_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    """Status without the planned scope is a different digest, so apply would go stale."""
    before = {
        "global": _scope_digest("home-before"),
        "project": _scope_digest("project-before"),
        "user_root": _scope_digest("user-root-before"),
    }
    after = {
        "global": _scope_digest("home-after"),
        "project": _scope_digest("project-after"),
        "user_root": _scope_digest("user-root-after"),
    }
    root = tmp_path / "project"
    target = tmp_path / "target"
    root.mkdir()
    target.mkdir()
    executable = tmp_path / "provider"
    executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    os_name, architecture = install._release_platform().split("/", 1)  # pyright: ignore[reportPrivateUsage]
    build_digest = "sha256:" + "c" * 64
    info: dict[str, object] = {
        "protocol_version": protocol_v3.VERSION,
        "provider_id": "claude-setup-system",
        "harness_id": "claude-code",
        "provider_version": "3.0.0",
        "provider_build_digest": build_digest,
        "supported_commands": list(protocol_v3.CORE_COMMANDS),
        "supported_operations": sorted(item.value for item in protocol_v3.CORE_OPERATIONS),
        "supported_os": [os_name],
        "supported_arch": [architecture],
        "permission_profiles": [],
        "projection_profile": _projection_profile("claude/native-files/1", None),
        "scoped_projection_profiles": [
            _projection_profile("claude/project/1", "project"),
            _projection_profile("claude/user-root/1", "user_root"),
        ],
        "plan_request_fields": ["target_scope"],
        "status_request_fields": ["target_scope"],
    }
    capabilities = protocol_v3.parse_capabilities(info)
    calls: list[tuple[str, tuple[str, ...]]] = []
    state: dict[str, str] = {"applied": "", "plan_digest": "", "operation_id": "", "release": ""}

    def values(arguments: Sequence[str]) -> dict[str, str]:
        return dict(zip(arguments[0::2], arguments[1::2], strict=True))

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        calls.append((command, tuple(arguments)))
        asked = _argv_scope(arguments)
        if command == "provider-info":
            return cast(JsonValue, info)
        if command == "status":
            digest = (after if state["applied"] else before)[asked]
            if not state["applied"]:
                return {"state": "missing", "target_digest": digest}
            return {
                "state": "managed",
                "target_digest": digest,
                "provider_id": "claude-setup-system",
                "provider_version": "3.0.0",
                "provider_build_digest": build_digest,
                "provider_release_digest": state["release"],
                "operation_id": state["operation_id"],
                "provider_plan_digest": state["plan_digest"],
                "projection_profile_digest": operation_v3.profile_digest(capabilities, scope),
            }
        if command == "plan-operation":
            supplied = values(arguments)
            artifact: dict[str, JsonValue] = {
                "format": "ai-stp-provider-plan/3",
                "protocol_version": protocol_v3.VERSION,
                "provider_id": "claude-setup-system",
                "provider_version": "3.0.0",
                "provider_build_digest": build_digest,
                "provider_release_digest": supplied["--provider-release-digest"],
                "operation_id": supplied["--operation-id"],
                "operation": supplied["--operation"],
                "canonical_target": str(target.resolve()),
                "expected_target_digest": before[asked],
                "projection_profile_digest": operation_v3.profile_digest(capabilities, asked),
                "bundle": None,
                "backup_ref": supplied["--backup-ref"],
                "restore_target_digest": after[asked],
                "permission_profile": None,
                "platform": operation_v3._platform(),  # pyright: ignore[reportPrivateUsage]
                "expires_at": supplied["--expires-at"],
                "effects": ["restore the selected backup"],
            }
            digest = digest_canonical(protocol_v3.PLAN_DOMAIN, artifact)
            state["plan_digest"] = digest
            state["operation_id"] = supplied["--operation-id"]
            state["release"] = supplied["--provider-release-digest"]
            return {
                "state": "planned",
                "plan": artifact,
                "plan_digest": digest,
                "expected_target_digest": before[asked],
                "effects": artifact["effects"],
            }
        if command == "apply-operation":
            state["applied"] = "yes"
            return {
                "state": "verified",
                "plan_digest": state["plan_digest"],
                "expected_target_digest": before[scope],
                "backup_ref": "slot-after",
            }
        raise AssertionError(command)

    def invoker(
        _executable: str,
        provider_target: str,
        version: int,
        **_options: object,
    ) -> conformance.Invoker:
        assert provider_target == str(target.resolve())
        assert version == protocol_v3.VERSION
        return invoke

    monkeypatch.setattr(invocation, "provider_invoker", invoker)
    with closing(open_registry(configured_path(), create=True)) as connection:
        passports.init_developer(connection, device_id="device_test")
        passports.ensure_device(connection, device_id="device_test")
        found = project_passport.scan(connection, root)
        project_passport.record(connection, found, device_id="device_test")
        connection.commit()
        project_id = found.stable_id

    planned = install.plan(
        {
            "action": "rollback",
            "project": project_id,
            "harness": "claude-code",
            "provider": str(executable),
            "protocol-version": 3,
            "target": str(target),
            "unverified-provider": True,
            "backup-ref": "slot-selected",
            "scope": scope,
        }
    ).payload
    install.approve({"operation": planned.operation_id, "plan-digest": planned.plan_digest})
    done = install.apply({"operation": planned.operation_id, "provider": str(executable)}).payload

    status_calls = [arguments for command, arguments in calls if command == "status"]
    with closing(open_registry(configured_path())) as connection:
        recorded = installation.target_scope(connection, planned.operation_id)
        binding = connection.execute(
            "SELECT scope FROM operation_corporate_binding WHERE operation_id = ?",
            (planned.operation_id,),
        ).fetchone()

    assert done.state == "verified"
    assert status_calls
    assert all(_argv_scope(arguments) == scope for arguments in status_calls)
    assert binding is None
    assert recorded == ("" if scope == "user_root" else "project")
