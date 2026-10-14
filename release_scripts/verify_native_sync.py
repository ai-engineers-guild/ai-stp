"""Exercise the optimized native executable against the real API and PostgreSQL.

The existing test database helper creates and removes one disposable database.
Two temporary native installations use the real device flow and local commands;
only the test account and its web session are seeded. No native state is injected.
This is API compatibility evidence, not deployed GitHub login or writer cutover.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from alembic import command
from alembic.config import Config
from release_scripts._evidence import EvidenceError, without_credentials
from tests.support.api_settings import make_settings, make_test_auth
from tests.support.asgi_sync import SyncAsgiServer
from tests.support.postgres import TEST_DB_ENV, isolated_database

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Server(http.server.ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Bridge)
        self.origin = f"http://localhost:{self.server_port}"
        self.application: SyncAsgiServer | None = None
        self.drop_next_push = False
        self.pushes: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.failures: list[str] = []


class _Bridge(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def _forward(self) -> None:
        server = cast(_Server, self.server)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            assert 0 <= size <= 16 * 1024 * 1024
            payload = self.rfile.read(size)
            is_push = self.path == "/v1/sync/push"
            if is_push:
                server.pushes.append(json.loads(payload))
            assert server.application is not None and server.application.transport is not None
            request = httpx.Request(
                self.command,
                server.origin + self.path,
                headers=dict(self.headers),
                content=payload,
            )
            response = server.application.transport.handle_request(request)
            content = response.read()
            server.requests.append(
                {
                    "method": self.command,
                    "path": self.path.split("?")[0],
                    "status": response.status_code,
                }
            )
            if is_push and server.drop_next_push:
                assert response.status_code == 200
                assert json.loads(content)["receipts"][0]["state"] == "accepted"
                server.drop_next_push = False
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            self.send_response(response.status_code)
            for name, value in response.headers.multi_items():
                if name.lower() not in {"content-length", "transfer-encoding", "connection"}:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(content)
        except Exception as error:
            # A broken bridge must not masquerade as the intentional lost reply.
            server.failures.append(type(error).__name__)
            self.close_connection = True


class _Native:
    def __init__(self, binary: Path) -> None:
        self.binary = binary
        self.calls = 0
        self.scenarios: dict[str, str] = {}

    def invoke(self, root: Path, *args: str | Path, ok: bool = True) -> dict[str, Any]:
        environment = dict(
            os.environ,
            HOME=str(root / "home"),
            USERPROFILE=str(root / "home"),
            XDG_DATA_HOME=str(root / "data"),
            XDG_CONFIG_HOME=str(root / "config"),
            XDG_CACHE_HOME=str(root / "cache"),
            AI_STP_TELEMETRY_SUPPRESS="1",
        )
        result = subprocess.run(
            [str(self.binary), *map(str, args), "--json"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=50,
            check=False,
        )
        self.calls += 1
        if result.stderr:
            raise EvidenceError("native stderr is not empty")
        envelope = json.loads(result.stdout)
        without_credentials(envelope)
        if envelope["ok"] != ok or (result.returncode == 0) != ok:
            raise EvidenceError(f"unexpected native outcome for {' '.join(map(str, args[:2]))}")
        return envelope["data"] if ok else envelope

    def apply(
        self,
        root: Path,
        prepared: dict[str, Any],
        prefix: tuple[str, ...],
        *,
        sync: bool = False,
        ok: bool = True,
    ) -> dict[str, Any]:
        path = root / "plan.json"
        path.write_text(json.dumps(prepared["plan"]), encoding="utf-8")
        path.chmod(0o600)
        args: list[str | Path] = [
            *prefix,
            "--plan",
            path,
            "--plan-digest",
            prepared["plan_digest"],
        ]
        if sync:
            args += ["--config", root / "sync.yaml"]
        return self.invoke(root, *args, ok=ok)

    def account(self, root: Path, action: str, origin: str | None = None) -> dict[str, Any]:
        args: list[str | Path] = ["account", "plan", "--state-dir", root, "--action", action]
        if origin:
            args += ["--api-url", origin]
        return self.apply(root, self.invoke(root, *args), ("account", "apply"))

    def local(self, root: Path, command_path: str, **flags: str | Path) -> dict[str, Any]:
        args: list[str | Path] = [*command_path.split(), "--state-dir", root]
        for key, value in flags.items():
            args += ["--" + key.replace("_", "-"), value]
        return self.apply(root, self.invoke(root, *args), ("local", "apply"))

    def update(
        self,
        root: Path,
        document: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        path = root / "patch.json"
        path.write_text(json.dumps(patch), encoding="utf-8")
        return self.local(
            root,
            "passport developer update plan",
            expected_revision=document["revision_id"],
            patch=path,
        )

    def document(self, root: Path, expected: dict[str, Any]) -> None:
        view = self.invoke(
            root,
            "local",
            "passport",
            "show",
            "--state-dir",
            root,
            "--kind",
            "developer",
            "--id",
            expected["stable_id"],
        )
        keys = {
            "schema_version",
            "kind",
            "stable_id",
            "revision_id",
            "parent_revision_ids",
            "created_at",
            "owner_id",
            "facts",
        }
        assert view == {key: expected[key] for key in keys}
        database = root / "ai-stp-v2-state" / "registry.sqlite3"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute(
                "SELECT r.content FROM revision r JOIN head h ON h.revision_id=r.revision_id "
                "WHERE h.stable_id=?",
                (expected["stable_id"],),
            ).fetchall()
        assert len(rows) == 1 and json.loads(rows[0][0]) == expected

    def sync_plan(self, root: Path, action: str, **flags: str) -> dict[str, Any]:
        args: list[str | Path] = [
            "sync",
            action,
            "plan",
            "--state-dir",
            root,
            "--config",
            root / "sync.yaml",
        ]
        for key, value in flags.items():
            args += ["--" + key.replace("_", "-"), value]
        return self.invoke(root, *args)

    def sync_apply(self, root: Path, plan: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
        return self.apply(root, plan, ("sync", "apply"), sync=True, ok=ok)

    def push(self, root: Path, stable_id: str) -> dict[str, Any]:
        return self.sync_apply(root, self.sync_plan(root, "push", id=stable_id))["result"]

    def pull(self, root: Path) -> None:
        for _ in range(30):
            page = self.sync_apply(root, self.sync_plan(root, "pull", page_size="3"))["result"]
            if page["applied"] + page["replayed"] + len(page["skipped_event_ids"]) == 0:
                return
        raise EvidenceError("bounded native pull did not converge")

    def login(self, root: Path, origin: str, web: httpx.Client) -> dict[str, Any]:
        assert self.account(root, "start", origin)["outcome"] == "pending"
        pending = self.invoke(root, "account", "status", "--state-dir", root)
        response = web.post(
            "/v1/auth/device/approve",
            json={
                "schema_version": 1,
                "user_code": pending["session"]["user_code"],
            },
        )
        assert response.status_code == 200
        deadline = datetime.fromisoformat(pending["session"]["next_poll_at"].replace("Z", "+00:00"))
        seconds = max(0, (deadline - datetime.now(UTC)).total_seconds())
        assert seconds < 15
        time.sleep(seconds + 0.08)
        authorized = self.account(root, "poll")
        assert authorized["outcome"] == "authorized"
        return authorized

    def journey(self, root: Path, server: _Server, account: str, web: httpx.Client) -> None:
        a, b = root / "device-a", root / "device-b"
        devices = {}
        for state in (a, b):
            state.mkdir(mode=0o700)
            (state / "sync.yaml").write_text(
                "schema_version: 1\nsync:\n  enabled: true\n", encoding="utf-8"
            )
            initialization = self.invoke(
                state,
                "device",
                "initialize",
                "plan",
                "--state-dir",
                state,
                "--credential-store",
                "file",
            )
            devices[state] = self.apply(state, initialization, ("device", "initialize", "apply"))
            assert self.login(state, server.origin, web)["account_id"] == account
            assert self.account(state, "attach")["outcome"] == "attached"
        assert devices[a]["device_id"] != devices[b]["device_id"]

        developer = self.local(a, "passport developer initialize plan")
        stable_id = developer["stable_id"]
        developer = self.update(a, developer, {"role": "native API qualification"})
        assert self.push(a, stable_id)["state"] == "accepted"
        self.pull(b)
        self.document(b, developer)
        self.scenarios["first_transfer"] = "passed"
        developer = self.update(a, developer, {"preferred_languages": ["Rust"]})
        assert self.push(a, stable_id)["state"] == "accepted"
        self.pull(b)
        self.document(b, developer)
        self.scenarios["fast_forward"] = "passed"

        left = self.update(a, developer, {"role": "maintainer"})
        right = self.update(b, developer, {"priorities": ["correctness"]})
        assert self.push(a, stable_id)["state"] == "accepted"
        assert self.push(b, stable_id)["state"] == "conflict"
        self.pull(b)
        merged = self.local(b, "sync merge plan", id=stable_id)
        assert set(merged["parent_revision_ids"]) == {left["revision_id"], right["revision_id"]}
        assert self.push(b, stable_id)["state"] == "accepted"
        self.pull(a)
        self.document(a, merged)
        self.scenarios["divergence_clean_merge"] = "passed"

        changed = self.update(a, merged, {"preferred_harnesses": ["codex"]})
        pending = self.sync_plan(a, "push", id=stable_id)
        server.drop_next_push = True
        self.sync_apply(a, pending, ok=False)
        assert not server.drop_next_push and not server.failures
        lost = server.pushes[-1]
        assert self.sync_apply(a, pending)["result"]["state"] == "accepted"
        assert server.pushes[-1] == lost
        before = len(server.requests)
        assert self.sync_apply(a, pending)["result"]["state"] == "accepted"
        assert len(server.requests) == before
        self.pull(b)
        self.document(b, changed)
        self.scenarios["lost_committed_response_exact_retry"] = "passed"

        changed = self.update(a, changed, {"typical_tasks": ["Review native CLI changes"]})
        interrupted = self.sync_plan(a, "push", id=stable_id)
        server.drop_next_push = True
        self.sync_apply(a, interrupted, ok=False)
        assert not server.drop_next_push and not server.failures
        retired = server.pushes[-1]["events"][0]
        listing = web.get("/v1/devices")
        assert listing.status_code == 200
        (item,) = [v for v in listing.json()["items"] if v["device_id"] == devices[a]["device_id"]]
        assert (
            web.post(
                f"/v1/devices/{item['device_id']}/revoke", headers={"If-Match": item["etag"]}
            ).status_code
            == 200
        )
        assert self.account(a, "refresh")["outcome"] == "revoked"
        assert self.account(a, "recover")["outcome"] == "device_replaced"
        assert self.sync_apply(a, interrupted)["result"]["state"] == "interrupted"
        assert self.login(a, server.origin, web)["account_id"] == account
        recovery = self.sync_plan(a, "recover", event_id=retired["event_id"])
        recovered = self.sync_apply(a, recovery)
        assert recovered["result"]["remote_outcome"] == "unknown"
        assert recovered["result"]["state"] == "retired_device"
        self.pull(a)
        self.pull(b)
        self.document(a, changed)
        self.document(b, changed)
        assert self.sync_apply(a, recovery) == recovered
        self.scenarios["revoked_device_replacement_late_acceptance"] = "passed"

        self.update(a, changed, {"role": "left choice"})
        self.update(b, changed, {"role": "right choice"})
        assert self.push(a, stable_id)["state"] == "accepted"
        assert self.push(b, stable_id)["state"] == "conflict"
        self.pull(b)
        self.invoke(b, "sync", "merge", "plan", "--state-dir", b, "--id", stable_id, ok=False)
        self.scenarios["field_conflict_refuses_merge"] = "passed"
        for state in (a, b):
            assert self.account(state, "logout")["outcome"] == "closed"
        before = len(server.requests)
        assert self.sync_apply(a, recovery) == recovered
        assert len(server.requests) == before
        self.scenarios["terminal_replay_after_logout"] = "passed"


def _prove(native: _Native, root: Path, url: str) -> list[dict[str, Any]]:
    saved = os.environ.get("AI_STP_DB_URL")
    os.environ["AI_STP_DB_URL"] = url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if saved is None:
            os.environ.pop("AI_STP_DB_URL", None)
        else:
            os.environ["AI_STP_DB_URL"] = saved
    with _Server() as server:
        settings = make_settings(
            root / "logs", database_url=url, auth=make_test_auth(public_base_url=server.origin)
        )
        app = create_app(settings)
        with SyncAsgiServer(app) as service:
            server.application = service
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                account = new_id("account")

                async def seed() -> str:
                    async with app.state.sessionmaker() as db:
                        db.add(Account(id=account))
                        issued = await issue_session(
                            db, account_id=account, device_id=None, ttl_seconds=3600
                        )
                        await db.commit()
                        return issued.raw_token

                with httpx.Client(
                    base_url=server.origin,
                    trust_env=False,
                    timeout=20,
                    headers={"Authorization": f"Bearer {service.call(seed)}"},
                ) as web:
                    native.journey(root, server, account, web)
                assert not server.failures and not server.drop_next_push
                return server.requests
            finally:
                server.shutdown()
                thread.join(timeout=10)
                assert not thread.is_alive()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--binary-sha256", required=True)
    args = parser.parse_args()
    native = _Native(args.binary.resolve())
    previous_umask = os.umask(0o077)
    try:
        if not os.environ.get(TEST_DB_ENV):
            raise EvidenceError(f"{TEST_DB_ENV} must name a disposable PostgreSQL test service")
        expected = args.binary_sha256.removeprefix("sha256:")
        if _sha(native.binary) != expected:
            raise EvidenceError("the native executable differs from the reviewed digest")
        source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        with (
            isolated_database("PostgreSQL test service is required") as url,
            tempfile.TemporaryDirectory(prefix="ai-stp-native-sync-") as temporary,
        ):
            requests = _prove(native, Path(temporary), url)
        if _sha(native.binary) != expected:
            raise EvidenceError("the native executable changed during the proof")
        report = {
            "schema_version": 1,
            "state": "passed",
            "source_commit": source,
            "script_sha256": _sha(Path(__file__)),
            "binary_sha256": expected,
            "scenarios": native.scenarios,
            "native_calls": native.calls,
            "requests": requests,
            "actual_github_login": False,
            "boundary": "real API and disposable PostgreSQL; native devices; test web session",
        }
        print(json.dumps(without_credentials(report), sort_keys=True))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "state": "failed",
                    "error_type": type(error).__name__,
                    "reason": str(error)
                    if isinstance(error, EvidenceError)
                    else "native API proof failed",
                    "native_calls": native.calls,
                    "completed_scenarios": native.scenarios,
                }
            )
        )
        return 1
    finally:
        os.umask(previous_umask)


if __name__ == "__main__":
    raise SystemExit(main())
