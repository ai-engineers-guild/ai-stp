"""One real TCP-to-SQLite acquisition journey, including refusal and offline replay."""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from verify_impact_sources import AT, record_setup, release_instruction

from ai_stp_cli.local import content
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.cli.catalog import CatalogSetupAcquisition
from ai_stp_contracts.first_party import family
from ai_stp_contracts.fixtures import load_cases
from ai_stp_foundation.canonical import canonize
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_passports.envelope import derive_revision_id

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]


class Server(ThreadingHTTPServer):
    responses: dict[str, bytes]
    requests: list[str]
    connections: set[tuple[str, int]]
    protocol_version = "HTTP/1.0"

    def __init__(self, responses: dict[str, bytes]) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.responses = responses
        self.requests = []
        self.connections = set()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        assert isinstance(self.server, Server)
        self.protocol_version = self.server.protocol_version
        self.close_connection = self.protocol_version == "HTTP/1.0"
        self.server.requests.append(self.path)
        self.server.connections.add(self.client_address)
        assert "Authorization" not in self.headers and "Cookie" not in self.headers
        path = urlsplit(self.path)
        query = parse_qs(path.query)
        key = path.path + ("?digest=" + query["digest"][0] if "digest" in query else "")
        payload = self.server.responses.get(key)
        self.send_response(200 if payload is not None else 404)
        payload = payload if payload is not None else b"{}"
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-AI-STP-Schema-Version", "1")
        self.end_headers()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(payload)
        if self.protocol_version == "HTTP/1.0":
            # A delayed FIN must not make a nonpersistent connection reusable.
            time.sleep(0.1)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def fixture(root: Path) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    templates = {
        kind: copy.deepcopy(dict(next(c.body or {} for c in load_cases() if c.case_id == case)))
        for kind, case in [
            ("component", "readComponentVersion.published"),
            ("setup", "readSetupVersion.published"),
        ]
    }
    with closing(open_registry(root / "acquisition-source.sqlite3", create=True)) as source:
        secondary = content.put(source, "A distinct café Codex instruction.\n".encode(), at=AT)
        coordinate = release_instruction(
            source,
            harness_id="claude-code",
            payload=b"Primary Claude instructions.\n",
            managed_path="CLAUDE.md",
            extra_adaptations=[
                {
                    "harness_id": "codex",
                    "content_digest": secondary.digest,
                    "content_format": "ai-stp-component-file/1",
                    "managed_paths": ["AGENTS.md"],
                    "scope": "global",
                    "projection_kind": "native_files",
                    "declared_key": "",
                    "source_locator": "AGENTS.md",
                    "native_ids": [],
                }
            ],
        )
        component = json.loads(
            source.execute(
                "SELECT r.content FROM revision r JOIN object_version v "
                "ON v.revision_id=r.revision_id WHERE v.stable_id=? AND v.version=?",
                coordinate[:2],
            ).fetchone()[0]
        )
        # A complete historical passport may omit a later optional reference field.
        component.pop("runtime_requirements", None)
        component["revision_id"] = derive_revision_id(component)
        component_digest = digest_canonical("ai-stp:passport:v1", component)
        setup_id, _ = record_setup(source, harness_id="codex", member=coordinate)
        setup = json.loads(
            source.execute(
                "SELECT r.content FROM revision r JOIN object_version v "
                "ON v.revision_id=r.revision_id WHERE v.stable_id=? AND v.version='1.0'",
                (setup_id,),
            ).fetchone()[0]
        )
        setup["components"][0]["passport_digest"] = component_digest
        payload = json.loads(content.get(source, setup["artifact"]["digest"]))
        payload["components"][0]["passport_digest"] = component_digest
        setup_bytes = canonize(payload)
        setup["artifact"] = {
            "digest": digest_bytes("ai-stp:artifact:v1", setup_bytes),
            "size_bytes": len(setup_bytes),
        }
        setup["revision_id"] = derive_revision_id(setup)
        responses: dict[str, bytes] = {}
        for document in [component, setup]:
            kind = document["kind"]
            path = f"/v1/catalog/{kind}s/{document['stable_id']}/versions/{document['version']}"
            response = templates[kind]
            response.update(
                passport=document,
                passport_digest=digest_canonical("ai-stp:passport:v1", document),
                distribution_visibility="public",
            )
            responses[path] = json.dumps(response).encode()
            responses[path + "/artifact"] = (
                setup_bytes
                if kind == "setup"
                else content.get(source, document["artifact"]["digest"])
            )
            if kind == "component":
                for adaptation in document["adaptations"]:
                    for scope in adaptation["scope_adaptations"]:
                        address = scope["projection_artifact"]["digest"]
                        responses[path + "/artifact?digest=" + address] = content.get(
                            source, address
                        )
        return responses, setup, component


def prove(binary: Path, home: Path, state: Path, root: Path, run: Runner) -> None:
    responses, setup, component = fixture(root)
    database = state / "ai-stp-v2-state" / "registry.sqlite3"
    plan_path = root / "acquisition-plan.json"
    config = root / "acquisition.yaml"
    with Server(responses) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config.write_text(
                f"catalog:\n  url: http://127.0.0.1:{server.server_port}\n", encoding="utf-8"
            )
            args = [
                "registry",
                "acquire",
                "plan",
                "--state-dir",
                str(state),
                "--config",
                str(config),
                "--id",
                setup["stable_id"],
                "--version",
                "1.0",
            ]
            with closing(sqlite3.connect(database)) as db:
                before = tuple(db.iterdump())
                plan = run(binary, home, args, 0)["data"]
                assert tuple(db.iterdump()) == before, "planning changed the registry"
                server.protocol_version = "HTTP/1.1"
                connections = len(server.connections)
                plan = run(binary, home, args, 0)["data"]
                assert tuple(db.iterdump()) == before, "pooled planning changed the registry"
                assert len(server.connections) == connections + 1, (
                    "HTTP/1.1 did not reuse its socket"
                )
                assert digest_canonical("ai-stp:plan:v1", plan["plan"]) == plan["plan_digest"]
                plan_path.write_text(json.dumps(plan["plan"]), encoding="utf-8")
                apply = [
                    "local",
                    "apply",
                    "--plan",
                    str(plan_path),
                    "--plan-digest",
                    plan["plan_digest"],
                ]
                component_path = f"/v1/catalog/components/{component['stable_id']}/versions/1.0"
                metadata = responses[component_path]
                blocked = json.loads(metadata)
                blocked["lifecycle"] = "blocked"
                responses[component_path] = json.dumps(blocked).encode()
                run(binary, home, apply, 4)
                assert tuple(db.iterdump()) == before, "revoked acquisition changed local state"
                responses[component_path] = metadata
                projection_path = next(
                    path
                    for path in responses
                    if "?digest=" in path and responses[path] != responses[path.split("?")[0]]
                )
                original = responses[projection_path]
                responses[projection_path] = b"corrupt"
                run(binary, home, apply, 4)
                assert tuple(db.iterdump()) == before, "failed capture wrote a partial graph"
                responses[projection_path] = original
                db.execute(
                    "CREATE TRIGGER fail_acquisition BEFORE INSERT ON object_version "
                    "BEGIN SELECT RAISE(ABORT,'interrupted'); END"
                )
                db.commit()
                interrupted = tuple(db.iterdump())
                run(binary, home, apply, 4)
                assert tuple(db.iterdump()) == interrupted, (
                    "failed transaction retained acquisition writes"
                )
                db.execute("DROP TRIGGER fail_acquisition")
                db.commit()
                result = run(binary, home, apply, 0)["data"]
                assert (
                    CatalogSetupAcquisition.model_validate(result).model_dump(mode="json") == result
                )
                assert result["passport_digest"] == digest_canonical("ai-stp:passport:v1", setup)
                assert (
                    db.execute(
                        "SELECT count(*) FROM acquired_trust WHERE stable_id IN (?,?)",
                        (setup["stable_id"], component["stable_id"]),
                    ).fetchone()[0]
                    == 2
                )
                retained = db.execute(
                    "SELECT r.content FROM revision r JOIN object_version v "
                    "ON v.revision_id=r.revision_id WHERE v.stable_id=?",
                    (component["stable_id"],),
                ).fetchone()[0]
                assert json.loads(retained) == component, (
                    "acquisition normalized immutable historical bytes"
                )
                for adaptation in component["adaptations"]:
                    for scope in adaptation["scope_adaptations"]:
                        address = scope["projection_artifact"]["digest"]
                        held = db.execute(
                            "SELECT bytes FROM content WHERE digest=?", (address,)
                        ).fetchone()[0]
                        assert digest_bytes("ai-stp:artifact:v1", held) == address
                after = tuple(db.iterdump())
                calls = len(server.requests)
                responses.clear()
                assert run(binary, home, apply, 0)["data"] == result
                assert len(server.requests) == calls, "completed replay opened the network"
                assert tuple(db.iterdump()) == after
                address = component["adaptations"][1]["scope_adaptations"][0][
                    "projection_artifact"
                ]["digest"]
                db.execute("UPDATE content SET bytes=? WHERE digest=?", (b"corrupt", address))
                db.commit()
                run(binary, home, apply, 4)
                assert len(server.requests) == calls
                # This is a disposable fixture, and subsequent authoring proofs share its registry.
                db.execute("UPDATE content SET bytes=? WHERE digest=?", (original, address))
                db.commit()
                # Exercise the unchanged published corpus, whose input provenance
                # lives in its artifact without a duplicate passport snapshot fact.
                corpus_setup: dict[str, Any] | None = None
                for item in family("codex", "nddev-builder"):
                    document = item.passport.model_dump(mode="json")
                    kind = item.kind
                    template = next(
                        c.body or {}
                        for c in load_cases()
                        if c.case_id
                        == (
                            "readComponentVersion.published"
                            if kind == "component"
                            else "readSetupVersion.published"
                        )
                    )
                    response = copy.deepcopy(dict(template))
                    response.update(
                        passport=document,
                        passport_digest=item.passport_digest,
                        distribution_visibility="public",
                    )
                    path = (
                        f"/v1/catalog/{kind}s/{document['stable_id']}"
                        f"/versions/{document['version']}"
                    )
                    responses[path] = json.dumps(response).encode()
                    responses[path + "/artifact"] = item.artifact
                    if kind == "setup":
                        corpus_setup = document
                assert corpus_setup is not None
                corpus_args = [
                    *args[:-4],
                    "--id",
                    corpus_setup["stable_id"],
                    "--version",
                    corpus_setup["version"],
                ]
                corpus_plan = run(binary, home, corpus_args, 0)["data"]
                plan_path.write_text(json.dumps(corpus_plan["plan"]), encoding="utf-8")
                corpus_result = run(binary, home, [*apply[:-1], corpus_plan["plan_digest"]], 0)[
                    "data"
                ]
                assert corpus_result["stable_id"] == corpus_setup["stable_id"]
        finally:
            server.shutdown()
            thread.join(timeout=5)
