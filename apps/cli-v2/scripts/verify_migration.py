"""Transfer real schema-53 state in place and recover across the credential boundary.

The Python engine creates only disposable fixture data. Native invocations have
no Python on PATH, and no real user keyring or production registry is opened.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from ai_stp_cli.local.database import open_registry


def fixture() -> None:
    from ai_stp_cli.identity import load_or_create, reset
    from ai_stp_cli.local.passports import ensure_device, init_developer, owner
    from ai_stp_cli.paths import data_dir
    from ai_stp_cli.secrets import store_json
    from ai_stp_foundation.ids import new_id

    load_or_create()
    identity, _ = reset()
    account = owner().account_id
    database = open_registry(data_dir() / "registry.sqlite")
    init_developer(database, device_id=identity.device_id)
    ensure_device(database, device_id=identity.device_id)
    task = new_id("task")
    at = "2026-10-14T00:00:00.000Z"
    database.execute(
        "INSERT INTO agent_task(task_id,revision,intent,state,goal_satisfied,idempotency_key,"
        "payload_json,outcome_json,questions_json,child_operation_ids_json,created_at,updated_at) "
        "VALUES (?,1,'inspect','completed',1,'legacy-inspect','{}',NULL,'[]','[]',?,?)",
        (task, at, at),
    )
    store_json(
        identity.store,
        "cloud-credentials",
        {
            "account_id": account,
            "device_id": identity.device_id,
            "expires_at": "2027-01-01T00:00:00.000Z",
            "state": "active",
            "access_token": "disposable-migration-access",
            "refresh_token": "disposable-migration-refresh",
        },
    )
    print(
        json.dumps(
            {"device": identity.report().model_dump(mode="json"), "account": account, "task": task}
        ),
        flush=True,
    )
    # Leave committed WAL frames, as a terminated legacy process would. Do not
    # checkpoint or close the connection before the native reader sees them.
    os._exit(0)


def prove(binary: Path, home: Path, root: Path, run: Any) -> None:
    place = root / "production-transfer"
    place.mkdir(mode=0o700)
    environment = dict(
        os.environ,
        HOME=str(place),
        USERPROFILE=str(place),
        XDG_DATA_HOME=str(place),
        XDG_CONFIG_HOME=str(place),
        XDG_CACHE_HOME=str(place),
        AI_STP_FORCE_FILE_CREDENTIAL_STORE="1",
    )
    original = json.loads(
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--fixture"],
            env=environment,
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout
    )
    state = place / "ai-stp"
    database = state / "registry.sqlite"
    assert database.with_name("registry.sqlite-wal").stat().st_size > 0
    identity = (database.stat().st_dev, database.stat().st_ino)

    def invoke(arguments: list[str], status: int = 0) -> dict[str, Any]:
        return run(binary, home, arguments, status)

    def plan() -> dict[str, Any]:
        return invoke(
            [
                "state",
                "migrate",
                "plan",
                "--state-dir",
                str(state),
                "--credential-store",
                "file",
                "--provider",
                "github",
            ]
        )["data"]

    def apply(value: dict[str, Any], status: int = 0) -> dict[str, Any]:
        path = place / "plan.json"
        path.write_text(json.dumps(value["plan"]), encoding="utf-8")
        return invoke(
            [
                "state",
                "migrate",
                "apply",
                "--plan",
                str(path),
                "--plan-digest",
                value["plan_digest"],
            ],
            status,
        )

    def records() -> dict[str, Any]:
        with closing(sqlite3.connect(database)) as connection:
            return {
                name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
                )
            }

    before = records()
    names = {
        p.name
        for p in state.iterdir()
        if p.name not in {"registry.sqlite-wal", "registry.sqlite-shm"}
    }
    reviewed = plan()
    assert {
        p.name
        for p in state.iterdir()
        if p.name not in {"registry.sqlite-wal", "registry.sqlite-shm"}
    } == names
    assert records() == before
    assert reviewed["plan"]["identity"]["public_key"] == original["device"]["public_key"]
    # Exact-byte preconditions and ordinary SQLite readers both prevent effects.
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("BEGIN")
        connection.execute("SELECT count(*) FROM agent_task").fetchone()
        assert apply(reviewed, 5)["error"]["retryable"]
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE agent_task SET revision=2")
        connection.commit()
    apply(reviewed, 4)
    reviewed = plan()
    before = records()
    # Hold the real account namespace lock: migration must persist its fence and
    # native device first, then refuse without publishing partial ownership.
    account = state / "ai-stp-v2-account"
    account.mkdir(mode=0o700)
    (account / "owner").write_bytes(b"ai-stp-cli-v2 isolated account sessions v1\n")
    (account / "owner").chmod(0o600)
    with (account / "lock").open("w+b") as lock:
        (account / "lock").chmod(0o600)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        child_environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR"}
        }
        child_environment.update(
            PATH="",
            HOME=str(home),
            USERPROFILE=str(home),
            XDG_DATA_HOME=str(home),
            XDG_CONFIG_HOME=str(home),
            XDG_CACHE_HOME=str(home),
        )
        path = place / "plan.json"
        path.write_text(json.dumps(reviewed["plan"]), encoding="utf-8")
        with subprocess.Popen(
            [
                str(binary),
                "state",
                "migrate",
                "apply",
                "--plan",
                str(path),
                "--plan-digest",
                reviewed["plan_digest"],
                "--json",
            ],
            env=child_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as child:
            deadline = time.monotonic() + 10
            while not (state / "ai-stp-v2-identity" / "identity.json").exists():
                assert child.poll() is None and time.monotonic() < deadline
                time.sleep(0.005)
            # Real process death after the SQL fence and device checkpoint,
            # while the retained account lock prevents completion.
            child.kill()
            stdout, stderr = child.communicate(timeout=10)
            assert child.returncode != 0 and not stdout and not stderr
        apply(reviewed, 5)
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 54
        invoke(["device", "show", "--state-dir", str(state)], 4)
        invoke(
            [
                "device",
                "initialize",
                "plan",
                "--state-dir",
                str(state),
                "--credential-store",
                "file",
            ],
            4,
        )
        try:
            open_registry(database)
        except Exception as error:
            assert "newer" in str(error)
        else:
            raise AssertionError("the previous writer accepted the transferred schema")
    result = apply(reviewed)["data"]
    assert result["state"] == "verified" and not result["registry_moved"]
    assert (database.stat().st_dev, database.stat().st_ino) == identity
    after = records()
    for name, rows in before.items():
        if name in {"operation", "operation_event"}:
            assert all(row in after[name] for row in rows)
        else:
            assert after[name] == rows, name
    assert apply(reviewed)["data"] == result
    assert invoke(["state", "migrate", "status", "--state-dir", str(state)])["data"] == result
    device = invoke(["device", "show", "--state-dir", str(state)])["data"]
    for key in ("device_id", "public_key", "created_at", "retired_device_ids"):
        assert device[key] == original["device"][key]
    session = invoke(["account", "status", "--state-dir", str(state)])["data"]
    assert (
        session["session"]["account_id"] == original["account"] and not session["online_verified"]
    )
    history = invoke(["task", "status", "--state-dir", str(state), "--task", original["task"]])[
        "data"
    ]
    assert history["state"] == "completed" and history["legacy_read_only"]
    assert (
        invoke(
            [
                "task",
                "continue",
                "--state-dir",
                str(state),
                "--task",
                original["task"],
                "--revision",
                "2",
            ]
        )["data"]
        == history
    )
    for name in ("cloud-credentials", f"device-key.{device['device_id']}"):
        assert not (state / "secrets" / f"{name}.secret").exists()
    assert not (state / "ai-stp-v2-state" / "registry.sqlite3").exists()
    source = place / "native-source"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: migrated-review\ndescription: Review migrated code.\n---\nRead the source.\n",
        encoding="utf-8",
    )
    request = place / "author.json"
    request.write_text(
        json.dumps(
            {
                "directory": str(source),
                "harness_id": "codex",
                "component_type": "skill",
                "name": "migrated-review",
                "license_spdx": "MIT",
            }
        ),
        encoding="utf-8",
    )
    authored = invoke(
        [
            "task",
            "start",
            "--intent",
            "author",
            "--state-dir",
            str(state),
            "--idempotency-key",
            "native-author-after-transfer",
            "--input",
            str(request),
        ]
    )["data"]
    assert authored["state"] == "completed" and authored["goal_satisfied"]
    # Historical migration replay must not reject or replace later native rows.
    after_authoring = records()
    assert apply(reviewed)["data"] == result and records() == after_authoring


if __name__ == "__main__":
    assert sys.argv[1:] == ["--fixture"]
    fixture()
