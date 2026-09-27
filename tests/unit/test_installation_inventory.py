"""A failed or bounded discovery cannot assert component removal."""

import hashlib
import io
import json
import sqlite3
import zipfile
from contextlib import closing, nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from ai_stp_cli.application import installation_inventory
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.local import cache, components, installation, managed_diff
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.installation_inventory import (
    InstallationInventoryReceipt,
    InstallationInventorySnapshot,
)
from ai_stp_foundation.ids import new_id


def test_scanner_keeps_missing_project_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE project_link (local_project_id TEXT, remote_project_id TEXT, "
        "organization_id TEXT, state TEXT)"
    )
    connection.execute("CREATE TABLE project_root (stable_id TEXT, root TEXT)")
    connection.execute("INSERT INTO project_link VALUES ('local', 'remote', 'org', 'linked')")
    connection.execute("INSERT INTO project_root VALUES ('local', ?)", (str(tmp_path / "missing"),))
    component = SimpleNamespace(
        harness_id="codex",
        component_type="skill",
        native_path="skills/example",
        absolute=tmp_path / "skills" / "example",
        holds_secret=False,
    )
    monkeypatch.setattr(
        components,
        "discover_report",
        Mock(return_value=SimpleNamespace(components=(component,), complete=True)),
    )

    global_scope, project_scope = installation_inventory.scan(connection, "org")

    assert global_scope.complete is True
    assert len(global_scope.components) == 1
    assert global_scope.components[0].source == "external"
    assert "skills/example" not in global_scope.components[0].location_digest
    assert project_scope.project_id == "remote"
    assert project_scope.complete is False
    assert project_scope.components == ()
    connection.close()


def test_bounded_discovery_is_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE project_link (local_project_id TEXT, remote_project_id TEXT, "
        "organization_id TEXT, state TEXT)"
    )
    connection.execute("CREATE TABLE project_root (stable_id TEXT, root TEXT)")
    monkeypatch.setattr(
        components,
        "discover_report",
        Mock(return_value=SimpleNamespace(components=(), complete=False)),
    )

    (global_scope,) = installation_inventory.scan(connection, "org")

    assert global_scope.complete is False
    assert global_scope.components == ()
    connection.close()


def test_unverifiable_managed_baseline_never_labels_a_path_external(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE project_link (local_project_id TEXT, remote_project_id TEXT, "
        "organization_id TEXT, state TEXT)"
    )
    connection.execute("CREATE TABLE project_root (stable_id TEXT, root TEXT)")
    component = SimpleNamespace(
        harness_id="codex",
        component_type="skill",
        native_path="skills/example",
        absolute=Path("/home/example/skills/example"),
        holds_secret=False,
    )
    monkeypatch.setattr(
        components,
        "discover_report",
        Mock(return_value=SimpleNamespace(components=(component,), complete=True)),
    )
    monkeypatch.setattr(
        installation_inventory,
        "_managed_components",
        Mock(return_value=((), frozenset(), False)),
    )

    (scope,) = installation_inventory.scan(
        connection, "org", account_id="account", device_id="device"
    )

    assert scope.complete is False
    assert scope.components[0].source == "unknown"
    connection.close()


def test_inventory_queue_waits_for_acknowledgement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database = tmp_path / "registry.db"
    organization_id = new_id("organization")
    account_id = new_id("account")
    device_id = new_id("device")
    monkeypatch.setattr(
        installation_inventory,
        "scan",
        Mock(return_value=(installation_inventory.InventoryScope(None, "global", False, ()),)),
    )
    with closing(open_registry(database)) as connection:
        assert (
            installation_inventory.enqueue(
                connection,
                organization_id=organization_id,
                account_id=account_id,
                device_id=device_id,
            )
            == 1
        )
        row = connection.execute(
            "SELECT scan_id, payload_json FROM corporate_inventory_outbox"
        ).fetchone()
        assert row is not None
        scan_id = str(row["scan_id"])
        assert '"complete":false' in str(row["payload_json"])
    monkeypatch.setattr(installation_inventory, "configured_path", Mock(return_value=database))
    monkeypatch.setattr(installation_inventory, "open_client", Mock(return_value=nullcontext(None)))
    responses = [
        InstallationInventoryReceipt(rejected_ids=[scan_id]),
        InstallationInventoryReceipt(accepted_ids=[scan_id]),
    ]
    monkeypatch.setattr(installation_inventory, "call", Mock(side_effect=responses))
    endpoint = cast(Endpoint, SimpleNamespace(max_attempts=1))
    session = Session(
        account_id=account_id,
        device_id=device_id,
        access_token="test",
        refresh_token="test",
        expires_at="2026-09-26T00:00:00.000Z",
    )
    assert installation_inventory.sync(endpoint, session, organization_id).rejected_ids == [scan_id]
    with closing(open_registry(database)) as connection:
        assert (
            connection.execute("SELECT count(*) FROM corporate_inventory_outbox").fetchone()[0] == 1
        )
    assert installation_inventory.sync(endpoint, session, organization_id).accepted_ids == [scan_id]
    with closing(open_registry(database)) as connection:
        assert (
            connection.execute("SELECT count(*) FROM corporate_inventory_outbox").fetchone()[0] == 0
        )


def test_inventory_contract_rejects_paths() -> None:
    with pytest.raises(ValidationError):
        InstallationInventorySnapshot.model_validate(
            {
                "scan_id": "inventory:000000000000000000000003",
                "organization_id": new_id("organization"),
                "employee_id": new_id("account"),
                "device_id": new_id("device"),
                "scope": "global",
                "scanned_at": "2026-09-25T12:00:00.000Z",
                "complete": True,
                "components": [],
                "absolute_path": "C:/private/task",
            }
        )


def test_managed_scan_reports_exact_version_and_manual_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        managed_diff,
        "component_passport",
        Mock(return_value=SimpleNamespace(component_type="mcp", adaptations=[])),
    )
    target = tmp_path / "target"
    member = target / "skills" / "review" / "SKILL.md"
    member.parent.mkdir(parents=True)
    member.write_bytes(b"expected\n")
    expected = "sha256:" + hashlib.sha256(b"expected\n").hexdigest()
    component_id = new_id("component")
    setup_id = new_id("setup")
    document = {
        "managed_paths": ["skills/review/SKILL.md"],
        "files": [{"path": "skills/review/SKILL.md", "digest": expected}],
        "conversion_report": {"entries": [{"native_surface": "skills"}]},
        "setup": {"stable_id": setup_id, "version": "1.0", "passport_digest": expected},
        "component_adaptations": [
            {
                "stable_id": component_id,
                "version": "2.0",
                "passport_digest": expected,
                "provider_component_kind": "skill",
                "member_paths": ["skills/review/SKILL.md"],
            }
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bundle.json", json.dumps(document))
    archive_path = tmp_path / "bundle.zip"
    archive_path.write_bytes(buffer.getvalue())
    monkeypatch.setattr(cache, "stored_raw_artifact", Mock(return_value=archive_path))
    organization_id = new_id("organization")
    project_id = new_id("remote_project")
    account_id = new_id("account")
    device_id = new_id("device")
    at = "2026-09-25T10:00:00.000Z"
    digest = "sha256:" + "a" * 64
    with closing(open_registry(tmp_path / "registry.db")) as connection:
        plan = installation.propose(
            connection,
            action="install",
            author=account_id,
            target_id="project_test:codex",
            expected_target_digest=digest,
            provider_version="1.0.0",
            effects=("write managed paths",),
            recovery_action="restore",
            idempotency_key="inventory-managed",
            at=at,
            expires_at="2099-01-01T00:00:00.000Z",
            provider_target=str(target),
            bundle_artifact_digest=expected,
            setup_stable_id=setup_id,
            setup_version="1.0",
        )
        installation.bind_corporate(
            connection,
            plan.operation_id,
            organization_id=organization_id,
            project_id=project_id,
            account_id=account_id,
            device_id=device_id,
            scope="project",
            at=at,
        )
        installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=at)
        installation.begin(connection, plan.operation_id, observed_target_digest=digest, at=at)
        installation.applied(connection, plan.operation_id, at=at)
        installation.verify(
            connection,
            plan.operation_id,
            postconditions_met=True,
            observed_target_digest=digest,
            at=at,
        )

        def managed():
            return installation_inventory._managed_components(  # pyright: ignore[reportPrivateUsage]
                connection,
                organization_id=organization_id,
                account_id=account_id,
                device_id=device_id,
                project_id=project_id,
            )

        items, covered, complete = managed()
        assert complete and len(items) == 1 and covered
        assert items[0].kind == "mcp"  # Domain kind comes from the passport, not packaging.
        assert (items[0].stable_id, items[0].version, items[0].state) == (
            component_id,
            "2.0",
            "present",
        )
        member.write_bytes(b"edited by hand\n")
        assert managed()[0][0].state == "modified"
        member.unlink()
        assert managed()[0][0].state == "missing"
