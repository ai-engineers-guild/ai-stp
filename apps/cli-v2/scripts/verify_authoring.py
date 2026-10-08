"""One real CLI journey from private identity and source to immutable setup."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import unicodedata
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from verify_context import prove as prove_context

from ai_stp_cli.local import content as stored_content
from ai_stp_cli.local import revisions, setup_versions, versions
from ai_stp_contracts.cli.components import (
    ComponentPassportValidation,
    ComponentQualityReport,
    PassportView,
)
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport
from ai_stp_passports.envelope import verify_revision_id

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]


def prove(binary: Path, home: Path, temporary: Path, run: Runner) -> None:
    if os.name == "nt":
        # The Windows native credential roundtrip is exercised in Rust. This
        # contract oracle uses disposable Unix file credentials only.
        return
    root = temporary / "local-authoring"
    root.mkdir()
    state = root / "state"
    state.mkdir()

    def invoke(args: list[str], status: int = 0) -> Any:
        response = run(binary, home, args, status)
        return response["data"] if status == 0 else response

    def plan_file(result: dict[str, Any], name: str, domain: str = "ai-stp:plan:v1") -> Path:
        assert digest_canonical(domain, result["plan"]) == result["plan_digest"]
        path = root / f"{name}.json"
        path.write_text(json.dumps(result["plan"]), encoding="utf-8")
        return path

    def apply(result: dict[str, Any], name: str) -> Any:
        path = plan_file(result, name)
        args = ["local", "apply", "--plan", str(path), "--plan-digest", result["plan_digest"]]
        value = invoke(args)
        assert invoke(args) == value, "replay changed the operation result"
        return value

    source = root / "review"
    scaffold = invoke(
        [
            "component",
            "scaffold",
            "plan",
            "--type",
            "skill",
            "--language",
            "none",
            "--name",
            "review",
            "--output",
            str(source),
        ]
    )
    path = plan_file(scaffold, "scaffold", "ai-stp:scaffold-plan:v1")
    invoke(
        [
            "component",
            "scaffold",
            "apply",
            "--plan",
            str(path),
            "--plan-digest",
            scaffold["plan_digest"],
        ]
    )
    patch_file = source / "component-passport.json"
    patch = json.loads(patch_file.read_text(encoding="utf-8"))
    patch.update(
        description="Review code and report actionable findings.",
        tags=["code-review"],
        license={"spdx_id": "MIT", "redistribution_allowed": True},
    )
    patch_file.write_text(json.dumps(patch), encoding="utf-8")
    skill = source / "source" / "SKILL.md"
    content = (
        "---\nname: review\ndescription: Review code.\n---\n"
        "Review changed files and report findings.\n"
    )
    skill.write_text(content, encoding="utf-8")
    declarations = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "provider-declarations.json"
        ).read_text(encoding="utf-8")
    )
    info = root / "provider.json"
    info.write_text(
        json.dumps(next(d for d in declarations if d["harness_id"] == "codex")), encoding="utf-8"
    )
    cursor_info = root / "cursor-provider.json"
    cursor_info.write_text(
        json.dumps(next(d for d in declarations if d["harness_id"] == "cursor")), encoding="utf-8"
    )
    bind = [
        "component",
        "source",
        "bind",
        "plan",
        "--state-dir",
        str(state),
        "--root",
        str(source),
        "--target",
        "codex:user_root",
        "--target",
        "cursor:project",
        "--provider-info",
        str(info),
        "--provider-info",
        str(cursor_info),
    ]
    invoke(bind, 4)
    assert not list(state.iterdir())
    identity = invoke(
        ["device", "initialize", "plan", "--state-dir", str(state), "--credential-store", "file"]
    )
    path = plan_file(identity, "identity")
    invoke(
        [
            "device",
            "initialize",
            "apply",
            "--plan",
            str(path),
            "--plan-digest",
            identity["plan_digest"],
        ]
    )
    planned = invoke(bind)
    assert {p.name for p in state.iterdir()} == {"ai-stp-v2-identity"}
    forged = json.loads(json.dumps(planned))
    forged["plan"]["operation"]["identity"]["account_id"] = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    forged["plan_digest"] = digest_canonical("ai-stp:plan:v1", forged["plan"])
    path = plan_file(forged, "forged-owner")
    invoke(["local", "apply", "--plan", str(path), "--plan-digest", forged["plan_digest"]], 4)
    assert {p.name for p in state.iterdir()} == {"ai-stp-v2-identity"}
    path = plan_file(planned, "binding")
    invoke(["local", "apply", "--plan", str(path), "--plan-digest", "sha256:" + "0" * 64], 2)
    assert {p.name for p in state.iterdir()} == {"ai-stp-v2-identity"}
    skill.write_text(content + "Changed after planning.\n", encoding="utf-8")
    invoke(["local", "apply", "--plan", str(path), "--plan-digest", planned["plan_digest"]], 4)
    database = state / "ai-stp-v2-state" / "registry.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        for table in (
            "entity",
            "revision",
            "head",
            "content",
            "component_source_binding",
            "operation",
        ):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    skill.write_text(content, encoding="utf-8")
    component = apply(planned, "binding")
    prove_context(root, state, invoke, apply)
    owner = identity["plan"]["account_id"]
    assert component["owner_id"] == owner
    component_id = component["stable_id"]
    show = [
        "local",
        "passport",
        "show",
        "--state-dir",
        str(state),
        "--kind",
        "component",
        "--id",
        component_id,
    ]
    view = invoke(show)
    PassportView.model_validate(view)
    assert view["revision_id"] == component["revision_id"]
    review_args = ["--state-dir", str(state), "--id", component_id]
    with closing(sqlite3.connect(database)) as connection:
        before_review = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("revision", "content", "operation", "object_version")
        }
    validation = invoke(["component", "passport", "validate", *review_args])
    ComponentPassportValidation.model_validate(validation)
    assert validation["ready"] is False and validation["missing_fields"] == ["source"]
    assert validation["invalid_fields"] == []
    quality = invoke(["component", "passport", "quality", *review_args])
    ComponentQualityReport.model_validate(quality)
    assert quality["informational_only"] is True
    assert quality["affects_trust_lane"] is False
    assert invoke(["component", "passport", "quality", *review_args]) == quality
    with closing(sqlite3.connect(database)) as connection:
        assert all(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == count
            for table, count in before_review.items()
        )
    patch = root / "patch.json"
    patch.write_text(json.dumps({"tags": ["review", "quality"]}), encoding="utf-8")
    update = invoke(
        [
            "component",
            "passport",
            "update",
            "plan",
            "--state-dir",
            str(state),
            "--id",
            component_id,
            "--expected-revision",
            component["revision_id"],
            "--patch",
            str(patch),
        ]
    )
    updated = apply(update, "update")
    assert apply(planned, "binding-replay") == component
    assert invoke(show)["revision_id"] == updated["revision_id"]
    release = invoke(
        [
            "component",
            "version",
            "release",
            "plan",
            "--state-dir",
            str(state),
            "--id",
            component_id,
            "--expected-revision",
            updated["revision_id"],
            "--increment",
            "minor",
        ]
    )
    released = apply(release, "release")
    released_model = ComponentVersionPassport.model_validate(released)
    assert released_model.model_dump(mode="json") == released
    assert verify_revision_id(released_model)
    digest = digest_canonical("ai-stp:passport:v1", released)
    assert (
        invoke(
            [
                "local",
                "version",
                "show",
                "--state-dir",
                str(state),
                "--kind",
                "component",
                "--id",
                component_id,
                "--version",
                "1.0",
            ]
        )
        == released
    )
    assert invoke(["local", "version", "list", "--state-dir", str(state), "--id", component_id])
    fork = invoke(
        [
            "component",
            "fork",
            "plan",
            "--state-dir",
            str(state),
            "--id",
            component_id,
            "--version",
            "1.0",
            "--passport-digest",
            digest,
        ]
    )
    forked = apply(fork, "fork")
    assert forked["owner_id"] == owner and forked["stable_id"] != component_id
    native_home = root / "native-home"
    native_skill = native_home / ".agents/skills/native-review/SKILL.md"
    native_skill.parent.mkdir(parents=True)
    native_body = (
        "---\nname: native-review\ndescription: Review native code.\n---\nKeep native bytes.\n"
    )
    native_skill.write_text(native_body, encoding="utf-8")
    candidates = invoke(
        [
            "component",
            "discover",
            "--root",
            str(native_home),
            "--harness",
            "undefined",
            "--scope",
            "global",
            "--root-kind",
            "home",
        ]
    )
    native_candidate = next(c for c in candidates["components"] if c["component_type"] == "skill")
    shared_adoption = [
        "component",
        "adopt",
        "plan",
        "--state-dir",
        str(state),
        "--root",
        str(native_home),
        "--scope",
        "global",
        "--root-kind",
        "home",
        "--candidate-id",
        native_candidate["candidate_id"],
        "--harness",
    ]
    invoke([*shared_adoption, "undefined"], 2)
    shared = apply(invoke([*shared_adoption, "codex"]), "shared-adopt")
    assert shared["facts"]["native_ids"]["value"] == ["native-review"]
    assert shared["facts"]["harness_id"]["value"] == "codex"
    assert shared["facts"]["harness_id"]["origin"] == "declared"
    assert shared["facts"]["observed_harness_id"]["value"] is None
    sources = root / "native-sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "scope": "user_root",
                    "source": {
                        "root": {
                            "display": unicodedata.normalize("NFC", str(native_home)),
                            "utf8_base64": base64.b64encode(
                                str(native_home).encode("utf-8")
                            ).decode("ascii"),
                        },
                        "harness_id": "undefined",
                        "scope": "global",
                        "root_kind": "home",
                        "candidate_id": native_candidate["candidate_id"],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    edit = invoke(
        [
            "component",
            "adaptation",
            "edit",
            "plan",
            "--state-dir",
            str(state),
            "--id",
            forked["stable_id"],
            "--expected-revision",
            forked["revision_id"],
            "--sources",
            str(sources),
            "--provider-info",
            str(info),
        ]
    )
    native_draft = apply(edit, "native-edit")
    assert native_draft["adaptations"][0]["implementation_mode"] == "native"
    assert native_skill.read_text(encoding="utf-8") == native_body
    native_release = invoke(
        [
            "component",
            "version",
            "release",
            "plan",
            "--state-dir",
            str(state),
            "--id",
            forked["stable_id"],
            "--expected-revision",
            native_draft["revision_id"],
            "--increment",
            "minor",
        ]
    )
    native_version = apply(native_release, "native-release")
    native_model = ComponentVersionPassport.model_validate(native_version)
    assert native_model.model_dump(mode="json") == native_version
    assert verify_revision_id(native_model)
    assert native_version["adaptations"] == native_draft["adaptations"]
    setup_root = root / "setup-authoring"
    starter = invoke(
        [
            "setup",
            "scaffold",
            "plan",
            "--harness",
            "codex",
            "--name",
            "review",
            "--output",
            str(setup_root),
        ]
    )
    starter_path = plan_file(starter, "setup-starter", "ai-stp:setup-scaffold-plan:v1")
    starter_args = [
        "setup",
        "scaffold",
        "apply",
        "--plan",
        str(starter_path),
        "--plan-digest",
        starter["plan_digest"],
    ]
    assert invoke(starter_args)["files_written"] == 1
    assert invoke(starter_args)["files_written"] == 0
    assert [p.name for p in setup_root.iterdir()] == ["setup-request.json"]
    request = setup_root / "setup-request.json"
    invoke(["setup", "compose", "plan", "--state-dir", str(state), "--request", str(request)], 2)
    request.write_text(
        json.dumps(
            {
                "harness_id": "codex",
                "name": "Review",
                "description": "Review changed files.",
                "purpose": "code-review",
                "members": [
                    {"stable_id": component_id, "version": "1.0", "passport_digest": digest}
                ],
            }
        ),
        encoding="utf-8",
    )
    compose = invoke(
        ["setup", "compose", "plan", "--state-dir", str(state), "--request", str(request)]
    )
    setup = apply(compose, "compose")
    setup_model = SetupVersionPassport.model_validate(setup)
    assert setup_model.model_dump(mode="json") == setup
    assert verify_revision_id(setup_model)
    assert setup["owner_id"] == owner and setup["harness_id"] == "codex"
    source = {
        "stable_id": setup["stable_id"],
        "version": "1.0",
        "passport_digest": digest_canonical("ai-stp:passport:v1", setup),
    }
    setup_source_args = [
        "--state-dir",
        str(state),
        "--id",
        source["stable_id"],
        "--version",
        "1.0",
        "--passport-digest",
        source["passport_digest"],
    ]
    output = root / "setup-export-cafe\u0301"
    exported = invoke(["setup", "export", "plan", *setup_source_args, "--output", str(output)])
    assert not output.exists()
    export_path = plan_file(exported, "setup-export-plan")
    export_args = [
        "setup",
        "export",
        "apply",
        "--plan",
        str(export_path),
        "--plan-digest",
        exported["plan_digest"],
    ]
    result = invoke(export_args)
    assert result["outcome"] == "created" and result["files_written"] == 3
    assert result["physical_target_tree_created"] is False
    assert sorted(p.name for p in output.iterdir()) == [
        "export-manifest.json",
        "setup-definition.json",
        "setup-passport.json",
    ]
    exported_passport = json.loads((output / "setup-passport.json").read_bytes())
    SetupVersionPassport.model_validate(exported_passport)
    assert exported_passport == setup
    manifest = json.loads((output / "export-manifest.json").read_bytes())
    assert manifest.pop("export_digest") == result["export_digest"]
    assert digest_canonical("ai-stp:setup-export:v1", manifest) == result["export_digest"]
    for name, expected in manifest["files"].items():
        assert digest_bytes("ai-stp:artifact:v1", (output / name).read_bytes()) == expected
    assert manifest["definition_digest"] == setup["artifact"]["digest"]
    replay = invoke(export_args)
    assert replay["outcome"] == "already_matches" and replay["files_written"] == 0
    for action in ["fork", "recast"]:
        target = ["--target-harness", "cursor"] if action == "recast" else []
        copy_plan = invoke(["setup", action, "plan", *setup_source_args, *target])
        copied = apply(copy_plan, f"setup-{action}")
        SetupVersionPassport.model_validate(copied)
        assert copied["stable_id"] != setup["stable_id"]
        assert copied["components"] == setup["components"]
        assert copied["related_setup_ids"] == [setup["stable_id"]]
        assert copied["ported_from"] == (source if action == "recast" else None)
        assert copied["harness_id"] == ("cursor" if action == "recast" else "codex")
    assert (
        invoke(
            [
                "local",
                "version",
                "show",
                "--state-dir",
                str(state),
                "--kind",
                "setup",
                "--id",
                setup["stable_id"],
                "--version",
                "1.0",
            ]
        )
        == setup
    )

    # Read an actual production-builder setup without rewriting its immutable
    # three-field definition references to the passport's explicit null defaults.
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        document = setup_versions.passport_content(
            connection,
            stable_id=new_id("setup"),
            version="1.0",
            owner_id=owner,
            project_id=new_id("project"),
            harness_id="codex",
            snapshot=setup["facts"]["snapshot"]["value"],
            members=(setup_versions.MemberRef(component_id, "1.0", digest),),
            at=setup["created_at"],
        )
        held = revisions.commit(connection, document, device_id=identity["plan"]["device_id"])
        legacy = held.envelope.model_dump(mode="json")
        legacy_digest = digest_canonical("ai-stp:passport:v1", legacy)
        versions.record(
            connection,
            stable_id=held.stable_id,
            version="1.0",
            passport_digest=legacy_digest,
            revision_id=held.revision_id,
            at=setup["created_at"],
        )
        legacy_definition = stored_content.get(connection, legacy["artifact"]["digest"])
        connection.commit()
    assert legacy["components"][0]["variant_id"] is None
    assert "variant_id" not in json.loads(legacy_definition)["components"][0]
    legacy_args = [
        "--state-dir",
        str(state),
        "--id",
        held.stable_id,
        "--version",
        "1.0",
        "--passport-digest",
        legacy_digest,
    ]
    copied = apply(invoke(["setup", "fork", "plan", *legacy_args]), "python-setup-fork")
    assert copied["components"] == legacy["components"]
    legacy_output = root / "python-setup-export"
    export_plan = invoke(
        [
            "setup",
            "export",
            "plan",
            *legacy_args,
            "--output",
            str(legacy_output),
        ]
    )
    path = plan_file(export_plan, "python-setup-export-plan")
    invoke(
        [
            "setup",
            "export",
            "apply",
            "--plan",
            str(path),
            "--plan-digest",
            export_plan["plan_digest"],
        ]
    )
    assert (legacy_output / "setup-definition.json").read_bytes() == legacy_definition
    assert json.loads((legacy_output / "setup-passport.json").read_bytes()) == legacy

    native = root / "native-codex"
    native.mkdir()
    config = "model = 'unowned-setting'\n[mcp_servers.example]\ncommand = 'example-server'\n"
    (native / "config.toml").write_text(config, encoding="utf-8")
    source_args = [
        "--root",
        str(native),
        "--harness",
        "codex",
        "--scope",
        "global",
        "--root-kind",
        "config",
    ]
    discovered = invoke(["component", "discover", *source_args])
    assert discovered["complete"]
    candidate = next(row for row in discovered["components"] if row["component_type"] == "mcp")
    adopt = invoke(
        [
            "component",
            "adopt",
            "plan",
            "--state-dir",
            str(state),
            *source_args,
            "--candidate-id",
            candidate["candidate_id"],
        ]
    )
    adopted = apply(adopt, "adopt")
    assert adopted["owner_id"] == owner
    assert adopted["facts"]["native_ids"]["value"] == ["example"], "MCP IDs must identify servers"
    assert (native / "config.toml").read_text(encoding="utf-8") == config

    before_forget = invoke(show)
    with closing(sqlite3.connect(database)) as connection:
        retained = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("revision", "content", "object_version", "component_source_binding")
        }
    forget = invoke(
        [
            "component",
            "forget",
            "plan",
            "--state-dir",
            str(state),
            "--id",
            component_id,
            "--expected-revision",
            before_forget["revision_id"],
        ]
    )
    forgotten = apply(forget, "forget")
    assert forgotten == {
        "schema_version": 1,
        "stable_id": component_id,
        "revision_id": before_forget["revision_id"],
        "state": "forgotten",
    }
    assert invoke(show) == before_forget
    assert (
        invoke(
            [
                "local",
                "version",
                "show",
                "--state-dir",
                str(state),
                "--kind",
                "component",
                "--id",
                component_id,
                "--version",
                "1.0",
            ]
        )
        == released
    )
    invoke(bind, 4)
    invoke(["setup", "compose", "plan", "--state-dir", str(state), "--request", str(request)], 4)
    validation = invoke(["component", "passport", "validate", *review_args])
    assert validation["ready"] is False
    assert validation["blocking_checks"][0]["details"]["constraint"] == "object_forgotten"
    with closing(sqlite3.connect(database)) as connection:
        assert all(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == count
            for table, count in retained.items()
        )
    assert skill.read_text(encoding="utf-8") == content

    project_root = root / "registered-project"
    project_root.mkdir()
    (project_root / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    (project_root / ".env").write_text("TOKEN=synthetic-project-secret", encoding="utf-8")
    # The Python marker remains unrelated to the isolated preview identity.
    production_marker = project_root / ".ai-stp" / "project-id"
    production_marker.parent.mkdir()
    production_marker.write_text("project_01ARZ3NDEKTSV4RRFFQ69G5FAV\n", encoding="ascii")
    project_args = ["project", "passport", "plan", "--state-dir", str(state), "--root"]
    project_plan = invoke([*project_args, str(project_root)])
    assert not (project_root / ".ai-stp-v2-project").exists()
    assert "synthetic-project-secret" not in str(project_plan)
    project = apply(project_plan, "project")
    PassportView.model_validate(project)
    assert project["stable_id"] != production_marker.read_text(encoding="ascii").strip()
    assert project["facts"]["languages"]["value"] == ["rust"]
    project_show = [
        "local",
        "passport",
        "show",
        "--state-dir",
        str(state),
        "--kind",
        "project",
        "--id",
        project["stable_id"],
    ]
    assert invoke(project_show) == project
    assert apply(invoke([*project_args, str(project_root)]), "project-unchanged") == project
    moved_root = root / "moved-project"
    project_root.rename(moved_root)
    moved = apply(invoke([*project_args, str(moved_root)]), "project-moved")
    assert moved["stable_id"] == project["stable_id"]
    assert moved["parent_revision_ids"] == [project["revision_id"]]
    assert apply(project_plan, "project-replay") == project
    assert invoke(project_show) == moved
    assert (moved_root / ".ai-stp" / "project-id").read_text(encoding="ascii") == (
        "project_01ARZ3NDEKTSV4RRFFQ69G5FAV\n"
    )
    assert (moved_root / "main.rs").read_text(encoding="utf-8") == "fn main() {}\n"
