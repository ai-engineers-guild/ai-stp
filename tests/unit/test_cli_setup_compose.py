"""A new mixed setup is frozen and recorded as one immutable version."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.commands import setup_compose as command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, revisions, setup_compose, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import SetupComposePlan
from ai_stp_passports import SetupVersionPassport, verify_revision_id
from ai_stp_sources.models import SourceSnapshot

SETUP = "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OWNER = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
DEVICE = "device_01ARZ3NDEKTSV4RRFFQ69G5FAV"
AT = "2026-09-01T00:00:00.000Z"


def test_compose_accepts_an_explicit_public_source_page() -> None:
    manifest = setup_compose.parse_manifest(
        {
            "schema_version": 1,
            "name": "Sourced setup",
            "description": "A setup with an explicit source page.",
            "harness_id": "codex",
            "tags": ["source"],
            "components": [
                {
                    "source": {"kind": "path", "relative_path": "skill"},
                    "component_type": "skill",
                    "name": "skill",
                    "description": "A local skill.",
                    "license_spdx": "MIT",
                    "source_url": "https://pypi.org/project/example/",
                }
            ],
        }
    )
    assert manifest.components[0].source_url == "https://pypi.org/project/example/"
    with pytest.raises(CliFailure):
        setup_compose.parse_manifest(
            {
                "schema_version": 1,
                "name": "Unsafe setup",
                "description": "A setup with an unsafe source page.",
                "harness_id": "codex",
                "tags": ["source"],
                "components": [
                    {
                        "source": {"kind": "path", "relative_path": "skill"},
                        "component_type": "skill",
                        "name": "skill",
                        "description": "A local skill.",
                        "license_spdx": "MIT",
                        "source_url": "http://example.test/",
                    }
                ],
            }
        )


def test_path_component_composes_and_records_a_publishable_setup() -> None:
    manifest = setup_compose.parse_manifest(
        {
            "schema_version": 1,
            "name": "Frontend developer",
            "description": "An exact mixed frontend development setup.",
            "harness_id": "codex",
            "tags": ["frontend"],
            "components": [
                {
                    "source": {"kind": "path", "relative_path": "hooks/check"},
                    "component_type": "hook",
                    "name": "check",
                    "description": "Locally authored validation hook.",
                    "license_spdx": "MIT",
                    "redistribution_allowed": True,
                    "managed_paths": ["hooks/check.py"],
                }
            ],
        }
    )
    component = manifest.components[0]
    snapshot = SourceSnapshot(
        kind="path",
        canonical_coordinate="path:hooks/check",
        exact_identity="hooks/check",
        component_digest="sha256:" + "a" * 64,
        files={"check.py": b"print('ok')\n"},
    )
    resolved = setup_compose.compose(
        manifest=manifest,
        setup_id=SETUP,
        publisher_id=OWNER,
        created_at=AT,
        snapshots=[(component, snapshot)],
        catalog=[],
    )
    preview = setup_compose.plan_view(resolved)
    assert isinstance(preview, SetupComposePlan)
    assert preview.members[0].embedded is True
    assert preview.members[0].source == "path:hooks/check"

    with closing(open_registry(configured_path(), create=True)) as connection:
        result = setup_compose.apply(
            connection,
            resolved,
            expected_plan_digest=preview.plan_digest,
            device_id=DEVICE,
            publisher_id=OWNER,
            at=AT,
        )
        recorded = versions.held(connection, SETUP, "1.0")
        assert recorded is not None
        assert content.get(connection, result.definition_digest) == resolved.frozen.payload
        stored = revisions.get(connection, recorded.revision_id)
        assert stored is not None
        passport = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
        assert passport.visibility == "public"
        assert verify_revision_id(passport)
        assert passport.model_extra is not None
        assert passport.model_extra["harness_ids"] == [
            "antigravity",
            "claude-code",
            "codex",
            "cursor",
            "grok-build",
        ]


def test_cli_plan_and_apply_resolve_a_local_component(tmp_path: Path) -> None:
    hook = tmp_path / "hooks" / "check"
    hook.mkdir(parents=True)
    (hook / "check.py").write_text("print('ok')\n", encoding="utf-8")
    manifest = tmp_path / "setup.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Frontend developer",
                "description": "A mixed frontend setup.",
                "harness_id": "codex",
                "tags": ["frontend"],
                "components": [
                    {
                        "source": {"kind": "path", "relative_path": "hooks/check"},
                        "component_type": "hook",
                        "name": "check",
                        "description": "Locally authored validation hook.",
                        "license_spdx": "MIT",
                        "redistribution_allowed": True,
                        "managed_paths": ["hooks/check.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    preview = command.plan({"manifest": str(manifest), "root": str(tmp_path)}).payload
    result = command.apply(
        {
            "manifest": str(manifest),
            "root": str(tmp_path),
            "id": preview.setup_id,
            "created-at": preview.created_at,
            "expected-plan-digest": preview.plan_digest,
        }
    ).payload
    assert result.setup_id == preview.setup_id
    assert result.definition_digest == preview.definition_digest


def test_export_writes_a_review_tree_and_not_a_harness_tree(tmp_path: Path) -> None:
    hook = tmp_path / "hooks" / "check"
    hook.mkdir(parents=True)
    (hook / "check.py").write_text("print('ok')\n", encoding="utf-8")
    manifest = tmp_path / "setup.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Frontend developer",
                "description": "A mixed frontend setup.",
                "harness_id": "codex",
                "tags": ["frontend"],
                "components": [
                    {
                        "source": {"kind": "path", "relative_path": "hooks/check"},
                        "component_type": "hook",
                        "name": "check",
                        "description": "Locally authored validation hook.",
                        "license_spdx": "MIT",
                        "redistribution_allowed": True,
                        "managed_paths": ["hooks/check.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    preview = command.plan({"manifest": str(manifest), "root": str(tmp_path)}).payload
    applied = command.apply(
        {
            "manifest": str(manifest),
            "root": str(tmp_path),
            "id": preview.setup_id,
            "created-at": preview.created_at,
            "expected-plan-digest": preview.plan_digest,
        }
    ).payload
    destination = tmp_path / "exported-setup"
    result = command.export(
        {"id": applied.setup_id, "version": applied.version, "output": str(destination)}
    ).payload
    assert result.result == "local_setup_definition"
    assert result.storage == "local_registry"
    assert result.physical_target_tree_created is False
    assert result.definition_digest == applied.definition_digest
    assert result.export_format == "ai-stp-setup-export/1"
    assert (destination / "setup-passport.json").is_file()
    assert (destination / "setup-definition.json").is_file()
    manifest = json.loads((destination / "export-manifest.json").read_text(encoding="utf-8"))
    assert manifest["export_digest"] == result.export_digest
    assert manifest["definition_digest"] == applied.definition_digest
    assert set(manifest["files"]) == {"README.md", "setup-definition.json", "setup-passport.json"}
    readme = (destination / "README.md").read_text(encoding="utf-8")
    assert "physical harness tree is not created" in readme
    assert "Native harness state is not written" in readme
    with pytest.raises(CliFailure, match="must not already exist"):
        command.export({"id": applied.setup_id, "output": str(destination)})
