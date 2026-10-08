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

from ai_stp_contracts.cli.components import PassportView
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport

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
        "--provider-info",
        str(info),
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
    ComponentVersionPassport.model_validate(released)
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
    ComponentVersionPassport.model_validate(native_version)
    assert native_version["adaptations"] == native_draft["adaptations"]
    request = root / "setup.json"
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
    SetupVersionPassport.model_validate(setup)
    assert setup["owner_id"] == owner and setup["harness_id"] == "codex"
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
    assert (native / "config.toml").read_text(encoding="utf-8") == config
