"""Cross-language envelope/registry and real schema-53 backup proof.

Python is the development oracle, never a dependency of the native process.
Every child runs with an empty PATH and an isolated, initially empty home.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import statistics
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import verify_catalog
import verify_environment
import verify_identity
import verify_projects
import verify_selection

from ai_stp_cli.local import revisions, versions
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.cli.components import PassportView, VersionLine
from ai_stp_contracts.cli.registry import MachineHelp
from ai_stp_contracts.cli.runtime import ConfigReport
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.envelope import ErrorEnvelope, SuccessEnvelope


def run(binary: Path, home: Path, args: list[str], expected: int = 0) -> dict[str, Any]:
    environment = {
        # Python normalizes Windows environment keys to uppercase. Winsock needs
        # SYSTEMROOT even when the child needs neither PATH nor user state.
        name: value
        for name, value in os.environ.items()
        if name.upper() in {"SYSTEMROOT", "WINDIR"}
    }
    environment.update(
        PATH="",
        HOME=str(home),
        USERPROFILE=str(home),
        XDG_DATA_HOME=str(home),
        XDG_CONFIG_HOME=str(home),
        XDG_CACHE_HOME=str(home),
    )
    result = subprocess.run(
        [str(binary), *args, "--json"],
        capture_output=True,
        check=False,
        timeout=15,
        env=environment,
    )
    assert result.returncode == expected, (
        args,
        result.stdout.decode(errors="replace"),
        result.stderr.decode(errors="replace"),
    )
    assert not result.stderr, result.stderr
    model = SuccessEnvelope if expected == 0 else ErrorEnvelope
    envelope = model.model_validate_json(result.stdout)
    return envelope.model_dump(mode="json")


def prove(binary: Path, root: Path) -> None:
    home = root / "home"
    home.mkdir()
    help_data = run(binary, home, ["help", "--agent"])["data"]
    MachineHelp.model_validate(help_data)
    registry: JsonValue = {
        "commands": help_data["commands"],
        "global_options": help_data["global_options"],
        "error_codes": [
            {key: row[key] for key in ("code", "exit_class", "handling")}
            for row in help_data["error_codes"]
        ],
    }
    digest = digest_canonical("ai-stp:cli-registry:v1", registry)
    capabilities = run(binary, home, ["capabilities"])["data"]
    assert capabilities["registry_digest"] == help_data["registry_digest"] == digest
    assert capabilities["command_paths"] == [" ".join(row["path"]) for row in help_data["commands"]]
    assert capabilities["task_intents"] == capabilities["supported_harnesses"] == []
    assert run(binary, home, ["version"])["data"]["runtime"] == "rust"
    run(binary, home, ["unknown"], 2)
    prove_config(binary, home, root)
    prove_template(binary, home, root)
    prove_scaffold(binary, home, root)
    verify_identity.prove(binary, home, root, run)
    prove_objects(binary, home, root)
    verify_projects.prove(binary, home, root, run)
    verify_catalog.prove(binary, home, root, run)
    verify_environment.prove(binary, home, root, run)
    verify_selection.prove(binary, home, root, run)

    live = root / "live.sqlite"
    backup = root / "backup.sqlite"
    source = open_registry(live)
    try:
        # The native clean bootstrap keeps the complete persisted format,
        # including constraints and indexes, without the migration history.
        bootstrap = Path(__file__).resolve().parents[1] / "src" / "store" / "schema.sql"
        with closing(sqlite3.connect(":memory:")) as fresh:
            fresh.executescript(bootstrap.read_text(encoding="utf-8"))
            query = (
                "SELECT type, name, tbl_name, coalesce(sql, '') FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            )
            expected_schema = [
                (kind, name, table, " ".join(sql.split()))
                for kind, name, table, sql in source.execute(query)
            ]
            actual_schema = [
                (kind, name, table, " ".join(sql.split()))
                for kind, name, table, sql in fresh.execute(query)
            ]
            assert actual_schema == expected_schema, "native state format drifted"
            assert fresh.execute("PRAGMA user_version").fetchone()[0] == 53
        source.execute("PRAGMA wal_autocheckpoint=0")
        source.execute(
            "INSERT INTO entity(stable_id, kind, created_at) VALUES (?, ?, ?)",
            ("component_01ARZ3NDEKTSV4RRFFQ69G5FAV", "component", "2026-01-01T00:00:00Z"),
        )
        # Keep the live WAL open: copying only its main file would miss the row.
        assert Path(str(live) + "-wal").stat().st_size > 0
        with closing(sqlite3.connect(backup)) as destination:
            source.backup(destination)
            destination.execute("PRAGMA journal_mode=DELETE")
        expected_counts = {
            row[0]: source.execute(
                'SELECT count(*) FROM "' + row[0].replace('"', '""') + '"'
            ).fetchone()[0]
            for row in source.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        }
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.iterdir()
            if path.is_file()
        }
        snapshot_digest = "sha256:" + before[backup.name]
        data = run(
            binary,
            home,
            ["snapshot", "inspect", "--snapshot", str(backup), "--sha256", snapshot_digest],
        )["data"]
        assert data["row_counts"] == expected_counts
        assert data["row_counts"]["entity"] == 1 and data["table_count"] == 51
        assert data["local_schema_version"] == 53 and data["read_only"] is True
        assert tuple(map(int, data["sqlite_version"].split("."))) >= (3, 53, 2)
        run(
            binary,
            home,
            ["snapshot", "inspect", "--snapshot", str(backup), "--sha256", "sha256:" + "0" * 64],
            4,
        )
        run(
            binary,
            home,
            [
                "snapshot",
                "inspect",
                "--snapshot",
                str(live),
                "--sha256",
                "sha256:" + before[live.name],
            ],
            4,
        )
        after = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.iterdir()
            if path.is_file()
        }
        assert before == after, "native reads changed database bytes or created sidecars"
    finally:
        source.close()
    with closing(sqlite3.connect(backup)) as newer:
        newer.execute("PRAGMA user_version=54")
    newer_digest = "sha256:" + hashlib.sha256(backup.read_bytes()).hexdigest()
    run(
        binary,
        home,
        ["snapshot", "inspect", "--snapshot", str(backup), "--sha256", newer_digest],
        4,
    )
    assert not list(home.iterdir()), "metadata created persistent state"
    print(
        json.dumps(
            {
                "registry_digest": digest,
                "snapshot_tables": 51,
                "sqlite_version": data["sqlite_version"],
                "result": "passed",
            }
        )
    )


def prove_config(binary: Path, home: Path, root: Path) -> None:
    defaults = ConfigReport.model_validate(run(binary, home, ["config", "show"])["data"])
    assert defaults.config_path is None
    assert len(defaults.values) == 19
    assert all(item.source == "default" for item in defaults.values)
    config = root / "preview.yaml"
    content = (
        "schema_version: 1\ncatalog:\n  enabled: false\nsearch:\n  result_limit: 7\n"
        "provider:\n  paths.codex: ''\nprojects:\n  discovery_roots: []\n"
    )
    config.write_text(content, encoding="utf-8")
    shown = ConfigReport.model_validate(
        run(
            binary,
            home,
            ["config", "show", "--config", str(config), "--set", "search.result_limit=9"],
        )["data"]
    )
    values = {item.path: item for item in shown.values}
    assert values["catalog.enabled"].value is False
    assert values["catalog.enabled"].source == "config_file"
    assert values["search.result_limit"].value == 9
    assert values["search.result_limit"].source == "command_argument"
    assert config.read_text(encoding="utf-8") == content
    ConfigReport.model_validate(
        run(binary, home, ["config", "validate", "--config", str(config)])["data"]
    )
    for malformed in (
        "schema_version: 2\n",
        "catalog:\n  enabled: definitely-not-a-boolean\n",
        "catalog:\n  enabled: true\n  enabled: false\n",
        "password: must-not-be-echoed\n",
        "provider:\n  paths:\n    codex: /tmp/provider\n",
        "---\n{}\n---\n{}\n",
        "catalog: !include secrets.yaml\n",
        "update:\n  check_ttl_hours: 0\n",
    ):
        config.write_text(malformed, encoding="utf-8")
        answer = run(binary, home, ["config", "validate", "--config", str(config)], 2)
        assert "must-not-be-echoed" not in json.dumps(answer)
    config.unlink()
    run(binary, home, ["config", "show", "--config", str(config)], 2)


def prove_scaffold(binary: Path, home: Path, root: Path) -> None:
    from ai_stp_contracts.authoring import ComponentTemplateDescriptor
    from ai_stp_contracts.component_passport import ComponentPassportPatch

    folder = root / "scaffold"
    folder.mkdir()
    pairs = [(kind, "none") for kind in ("instruction", "skill", "command", "agent")]
    pairs.extend(
        ("cli", language)
        for language in ("python", "typescript", "javascript", "rust", "go", "dart-flutter")
    )
    for kind, language in pairs:
        output = folder / f"{kind}-{language}"
        response = run(
            binary,
            home,
            [
                "component",
                "scaffold",
                "plan",
                "--type",
                kind,
                "--language",
                language,
                "--name",
                "safe-component",
                "--output",
                str(output),
            ],
        )["data"]
        plan = response["plan"]
        expected = response["plan_digest"]
        assert digest_canonical("ai-stp:scaffold-plan:v1", plan) == expected
        assert not output.exists()
        ComponentTemplateDescriptor.model_validate_json(plan["files"][".ai-stp-template.json"])
        ComponentPassportPatch.model_validate_json(plan["files"]["component-passport.json"])
        path = folder / f"{kind}-{language}.plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        apply = ["component", "scaffold", "apply", "--plan", str(path), "--plan-digest", expected]
        result = run(binary, home, apply)["data"]
        assert result["outcome"] == "created" and result["publication_ready"] is False
        assert result["staging_cleanup_pending"] is False
        assert result["files_written"] == len(plan["files"]) == 4
        for name, content in plan["files"].items():
            assert (output / name).read_bytes() == content.encode()
        assert run(binary, home, apply)["data"]["outcome"] == "already_matches"
        assert not any(output.rglob("README.md"))
        assert not (output / ".git").exists()
        assert not (output / "eval-profile.json").exists()
        assert not list(folder.glob(".ai-stp-scaffold-*"))
        inspect = ["component", "source", "inspect", "--root", str(output)]
        captured = run(binary, home, inspect)["data"]
        assert captured["source_ready"] is False
        assert captured["execution"] == "not_run" and captured["publication"] == "not_assessed"
        assert {item["code"] for item in captured["issues"]} == {
            "description_incomplete",
            "scaffold_marker",
        }
        assert len(captured["files"]) == 1
        patch = json.loads((output / "component-passport.json").read_bytes())
        patch["description"] = "A bounded implementation for local review."
        (output / "component-passport.json").write_text(json.dumps(patch), encoding="utf-8")
        described = run(binary, home, inspect)["data"]
        assert described["source_ready"] is False
        assert described["source_digest"] == captured["source_digest"]
        assert described["snapshot_digest"] != captured["snapshot_digest"]
        assert [item["code"] for item in described["issues"]] == ["scaffold_marker"]
    assert not list(home.iterdir())


def prove_template(binary: Path, home: Path, root: Path) -> None:
    from ai_stp_cli.local import authoring
    from ai_stp_contracts.cli.components import ComponentTemplateView

    template = root / "template.md"
    source = authoring.scaffold("skill", "review-kit")
    template.write_bytes(source.replace("\n", "\r\n").encode())
    arguments = [
        "component",
        "template",
        "render",
        "--template",
        str(template),
        "--name",
        "review-kit",
        "--component-root",
        "skills/review-kit",
        "--harness",
    ]
    for harness in sorted(authoring.HARNESSES):
        actual = ComponentTemplateView.model_validate(
            run(binary, home, [*arguments, harness])["data"]
        )
        expected = authoring.render(
            source,
            harness_id=harness,
            component_name="review-kit",
            component_root="skills/review-kit",
        )
        assert actual.content == expected.content
        assert actual.placeholders == list(expected.placeholders)
        assert actual.source_digest == "sha256:" + hashlib.sha256(source.encode()).hexdigest()
        assert (
            actual.rendered_digest
            == "sha256:" + hashlib.sha256(actual.content.encode()).hexdigest()
        )
    # CommonMark owns code boundaries, including a longer outer fence, quote
    # containers, indentation and valid fences that continue to end of input.
    for literal in (
        "````text\n```\n{{unknown}}\n````\n",
        "> ```text\n> {{unknown}}\n> ```\n",
        "    {{unknown}}\n",
        "```text\n{{unknown}}\n",
    ):
        template.write_text("Before {{component_name}}.\n\n" + literal, encoding="utf-8")
        actual = ComponentTemplateView.model_validate(
            run(binary, home, [*arguments, "codex"])["data"]
        )
        assert actual.content == "Before review-kit.\n\n" + literal
        assert actual.placeholders == ["component_name"]
    for malformed in (
        "{{unknown}}\n",
        "{{component_name\n",
        "{{/harness}}\n",
        "{{#harness:codex,codex}}\nx\n{{/harness}}\n",
        "{{#harness:codex}}\n{{#harness:pi}}\n",
        "{{#harness:undefined}}\nx\n{{/harness}}\n",
        "{{#harness:codex}}\n",
        "x" * (64 * 1024 + 1),
    ):
        template.write_text(malformed, encoding="utf-8")
        run(binary, home, [*arguments, "codex"], 2)
    template.write_text("{{component_root}}\n" * 300, encoding="utf-8")
    expanded_arguments = arguments.copy()
    expanded_arguments[expanded_arguments.index("--component-root") + 1] = "segment/" * 40 + "leaf"
    run(binary, home, [*expanded_arguments, "codex"], 2)
    assert list(home.iterdir()) == []


def prove_objects(binary: Path, home: Path, root: Path) -> None:
    state = root / "objects.sqlite"
    backup = root / "objects-backup.sqlite"
    device = "device_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    owner = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    component = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    at = "2026-10-08T00:00:00.000Z"
    with closing(open_registry(state)) as connection:
        for kind in ("developer", "device", "component"):
            content: dict[str, JsonValue] = {
                "schema_version": 1,
                "kind": kind,
                "stable_id": f"{kind}_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "owner_id": owner,
                "created_at": at,
                "facts": {},
            }
            if kind == "component":
                content["version"] = "1.0"
            stored = revisions.commit(connection, content, device_id=device)
            if kind == "component":
                versions.record(
                    connection,
                    stable_id=component,
                    version="1.0",
                    passport_digest=digest_canonical(
                        "ai-stp:passport:v1", stored.envelope.model_dump(mode="json")
                    ),
                    revision_id=stored.revision_id,
                    at=at,
                )
        with closing(sqlite3.connect(backup)) as destination:
            connection.backup(destination)
            destination.execute("PRAGMA journal_mode=DELETE")
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.iterdir()
            if path.is_file()
        }
        options = ["--snapshot", str(backup), "--sha256", "sha256:" + before[backup.name]]
        for command, kind in (
            (["passport", "developer", "show"], "developer"),
            (["passport", "device", "show"], "device"),
            (["component", "passport", "show", "--id", component], "component"),
        ):
            data = run(binary, home, command + options)["data"]
            PassportView.model_validate(data)
            expected = revisions.head(connection, f"{kind}_01ARZ3NDEKTSV4RRFFQ69G5FAV")
            assert expected is not None
            assert data["revision_id"] == expected.revision_id
            assert data["facts"] == expected.envelope.model_dump(mode="json")["facts"]
        command = ["component", "version", "list", "--id", component]
        line = VersionLine.model_validate(run(binary, home, command + options)["data"])
        assert line.next_minor == "1.1" and len(line.versions) == 1
        assert line.versions[0].revision_id == stored.revision_id
        after = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.iterdir()
            if path.is_file()
        }
        assert before == after, "object reads changed snapshot or live state"
    original = backup.read_bytes()
    # The file digest is deliberately updated: the record itself must be verified.
    for sql, parameters, command, code in (
        (
            "UPDATE revision SET content = replace(content, ?, ?) WHERE stable_id = ?",
            ("private", "public", component),
            ["component", "passport", "show", "--id", component],
            "AI_STP_PRECONDITION_FAILED",
        ),
        (
            "UPDATE object_version SET passport_digest = ?",
            ("sha256:" + "0" * 64,),
            ["component", "version", "list", "--id", component],
            "AI_STP_PRECONDITION_FAILED",
        ),
        (
            "UPDATE object_version SET created_at = ?",
            ("invalid",),
            ["component", "version", "list", "--id", component],
            "AI_STP_PRECONDITION_FAILED",
        ),
        (
            "INSERT INTO head (stable_id, revision_id) "
            "SELECT ?, revision_id FROM revision WHERE stable_id = ?",
            (component, device),
            ["component", "passport", "show", "--id", component],
            "AI_STP_CONFLICT",
        ),
    ):
        backup.write_bytes(original)
        with closing(sqlite3.connect(backup)) as corrupt:
            corrupt.execute(sql, parameters)
            corrupt.commit()
        options = [
            "--snapshot",
            str(backup),
            "--sha256",
            "sha256:" + hashlib.sha256(backup.read_bytes()).hexdigest(),
        ]
        answer = run(binary, home, command + options, 4)
        assert answer["error"]["code"] == code


def benchmark(binary: Path, root: Path) -> None:
    samples: list[float] = []
    for _ in range(50):
        started = time.perf_counter_ns()
        run(binary, root, ["version"])
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    print(
        json.dumps(
            {
                "command": "version --json",
                "processes": len(samples),
                "median_ms": statistics.median(samples),
                "p95_ms": sorted(samples)[47],
                "binary_bytes": binary.stat().st_size,
                "python_on_child_path": False,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    binary = (args.binary.with_suffix(".exe") if os.name == "nt" else args.binary).resolve(
        strict=True
    )
    with tempfile.TemporaryDirectory(prefix="ai-stp-native-proof-") as temporary:
        root = Path(temporary)
        if args.benchmark:
            benchmark(binary, root)
        else:
            prove(binary, root)


if __name__ == "__main__":
    main()
