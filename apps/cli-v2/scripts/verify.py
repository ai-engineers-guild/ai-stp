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

from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.cli.registry import MachineHelp
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.envelope import ErrorEnvelope, SuccessEnvelope


def run(binary: Path, home: Path, args: list[str], expected: int = 0) -> dict[str, Any]:
    environment = {
        name: value for name, value in os.environ.items() if name in {"SystemRoot", "WINDIR"}
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
    assert result.returncode == expected, result.stderr.decode(errors="replace")
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

    live = root / "live.sqlite"
    backup = root / "backup.sqlite"
    source = open_registry(live)
    try:
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
