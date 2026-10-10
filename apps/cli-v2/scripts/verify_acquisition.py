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
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_sources.definition import (
    EmbeddedDraft,
    freeze_setup_definition,
    validate_setup_definition,
)
from ai_stp_sources.models import SourceSnapshot

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


def embedded_setup(setup: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    document = copy.deepcopy(setup)
    document["stable_id"] = new_id("setup")
    payload = b'model_reasoning_effort = "high"\n'
    frozen = freeze_setup_definition(
        setup_id=document["stable_id"],
        version=document["version"],
        harness_id="codex",
        input_digest=document["facts"]["snapshot"]["value"],
        publisher_id=document["owner_id"],
        created_at=AT,
        catalog_members=tuple(ComponentRef.model_validate(ref) for ref in setup["components"]),
        embedded_members=(
            EmbeddedDraft(
                snapshot=SourceSnapshot(
                    kind="path",
                    canonical_coordinate="path:embedded-setting",
                    exact_identity="embedded-setting",
                    component_digest=digest_bytes("ai-stp:artifact:v1", payload),
                    files={"config.toml": payload},
                ),
                component_type="setting",
                name="embedded-setting",
                description="Explicit native setting for acquisition proof.",
                license_spdx="MIT",
                harness_id="codex",
                target_scope="global",
                stable_id=new_id("component"),
                managed_paths=("config.toml",),
            ),
        ),
        catalog_ids=frozenset(ref["stable_id"] for ref in setup["components"]),
    )
    document["components"] = frozen.document["components"]
    document["facts"]["members"]["value"] = frozen.document["components"]
    document["artifact_format"] = frozen.format
    return document, dict(frozen.document)


def prove(binary: Path, home: Path, state: Path, root: Path, run: Runner) -> None:
    responses, setup, component = fixture(root)
    initial_responses = dict(responses)
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
            db = sqlite3.connect(database)
            try:

                def native(arguments: list[str], expected: int) -> dict[str, Any]:
                    nonlocal db
                    assert not db.in_transaction
                    db.close()
                    result = run(binary, home, arguments, expected)
                    db = sqlite3.connect(database)
                    return result

                before = tuple(db.iterdump())
                plan = native(args, 0)["data"]
                assert tuple(db.iterdump()) == before, "planning changed the registry"
                server.protocol_version = "HTTP/1.1"
                connections = len(server.connections)
                plan = native(args, 0)["data"]
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
                native(apply, 4)
                assert tuple(db.iterdump()) == before, "revoked acquisition changed local state"
                responses[component_path] = metadata
                projection_path = next(
                    path
                    for path in responses
                    if "?digest=" in path and responses[path] != responses[path.split("?")[0]]
                )
                original = responses[projection_path]
                responses[projection_path] = b"corrupt"
                native(apply, 4)
                assert tuple(db.iterdump()) == before, "failed capture wrote a partial graph"
                responses[projection_path] = original
                db.execute(
                    "CREATE TRIGGER fail_acquisition BEFORE INSERT ON object_version "
                    "BEGIN SELECT RAISE(ABORT,'interrupted'); END"
                )
                db.commit()
                interrupted = tuple(db.iterdump())
                native(apply, 4)
                assert tuple(db.iterdump()) == interrupted, (
                    "failed transaction retained acquisition writes"
                )
                db.execute("DROP TRIGGER fail_acquisition")
                db.commit()
                result = native(apply, 0)["data"]
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
                assert native(apply, 0)["data"] == result
                assert len(server.requests) == calls, "completed replay opened the network"
                assert tuple(db.iterdump()) == after
                address = component["adaptations"][1]["scope_adaptations"][0][
                    "projection_artifact"
                ]["digest"]
                db.execute("UPDATE content SET bytes=? WHERE digest=?", (b"corrupt", address))
                db.commit()
                native(apply, 4)
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
                corpus_plan = native(corpus_args, 0)["data"]
                plan_path.write_text(json.dumps(corpus_plan["plan"]), encoding="utf-8")
                corpus_result = native([*apply[:-1], corpus_plan["plan_digest"]], 0)["data"]
                assert corpus_result["stable_id"] == corpus_setup["stable_id"]
                responses.update(initial_responses)
                mixed, definition = embedded_setup(setup)
                path = f"/v1/catalog/setups/{mixed['stable_id']}/versions/{mixed['version']}"
                template = json.loads(
                    initial_responses[
                        f"/v1/catalog/setups/{setup['stable_id']}/versions/{setup['version']}"
                    ]
                )

                def serve_definition(value: dict[str, Any]) -> None:
                    payload = canonize(value)
                    mixed["artifact"] = {
                        "digest": digest_bytes("ai-stp:artifact:v1", payload),
                        "size_bytes": len(payload),
                    }
                    mixed["revision_id"] = derive_revision_id(mixed)
                    template.update(
                        passport=mixed,
                        passport_digest=digest_canonical("ai-stp:passport:v1", mixed),
                        trust={
                            "trust_lane": "authoritative",
                            "author_verified": True,
                            "component_verified": True,
                        },
                    )
                    responses[path] = json.dumps(template).encode()
                    responses[path + "/artifact"] = payload

                mixed_args = [*args[:-4], "--id", mixed["stable_id"], "--version", "1.0"]
                before = tuple(db.iterdump())
                corrupt = copy.deepcopy(definition)
                corrupt["embedded"][0]["artifact_b64"] = "Y29ycnVwdA"
                serve_definition(corrupt)
                native(mixed_args, 4)
                excessive = copy.deepcopy(definition)
                excessive["embedded"] *= 501
                serve_definition(excessive)
                native(mixed_args, 4)
                assert tuple(db.iterdump()) == before
                serve_definition(definition)
                mixed_plan = native(mixed_args, 0)["data"]
                assert tuple(db.iterdump()) == before
                plan_path.write_text(json.dumps(mixed_plan["plan"]), encoding="utf-8")
                mixed_apply = [*apply[:-1], mixed_plan["plan_digest"]]
                db.execute(
                    "CREATE TRIGGER fail_embedded BEFORE INSERT ON object_version "
                    "BEGIN SELECT RAISE(ABORT,'interrupted'); END"
                )
                db.commit()
                interrupted = tuple(db.iterdump())
                native(mixed_apply, 4)
                assert tuple(db.iterdump()) == interrupted
                db.execute("DROP TRIGGER fail_embedded")
                db.commit()
                mixed_result = native(mixed_apply, 0)["data"]
                assert len(mixed_result["components"]) == 2
                embedded_id = definition["embedded"][0]["ref"]["stable_id"]
                assert not any(embedded_id in request for request in server.requests)
                assert db.execute(
                    "SELECT trust_lane,author_verified,component_verified "
                    "FROM acquired_trust WHERE stable_id=?",
                    (embedded_id,),
                ).fetchone() == ("experimental", 0, 0)
                after = tuple(db.iterdump())
                calls = len(server.requests)
                responses.clear()
                assert native(mixed_apply, 0)["data"] == mixed_result
                assert len(server.requests) == calls and tuple(db.iterdump()) == after
                exported = native(
                    [
                        "setup",
                        "export",
                        "plan",
                        "--state-dir",
                        str(state),
                        "--id",
                        mixed["stable_id"],
                        "--version",
                        "1.0",
                        "--passport-digest",
                        mixed_result["passport_digest"],
                        "--output",
                        str(root / "embedded-export"),
                    ],
                    0,
                )["data"]
                assert json.loads(exported["plan"]["files"]["setup-definition.json"]) == definition

                # The same embedded bytes must survive ordinary owned authoring.
                # A fork must not silently turn private embedded refs into catalog refs.
                def owned_apply(arguments: list[str]) -> dict[str, Any]:
                    before_plan = tuple(db.iterdump())
                    planned = native(arguments, 0)["data"]
                    assert tuple(db.iterdump()) == before_plan
                    plan_path.write_text(json.dumps(planned["plan"]), encoding="utf-8")
                    invocation = [*apply[:-1], planned["plan_digest"]]
                    result = native(invocation, 0)["data"]
                    retained = tuple(db.iterdump())
                    assert native(invocation, 0)["data"] == result
                    assert tuple(db.iterdump()) == retained
                    return result

                def stored_definition(document: dict[str, Any]) -> dict[str, Any]:
                    payload = db.execute(
                        "SELECT bytes FROM content WHERE digest=?",
                        (document["artifact"]["digest"],),
                    ).fetchone()[0]
                    assert (
                        digest_bytes("ai-stp:artifact:v1", payload)
                        == document["artifact"]["digest"]
                    )
                    return validate_setup_definition(payload)

                fork = owned_apply(
                    [
                        "setup",
                        "fork",
                        "plan",
                        "--state-dir",
                        str(state),
                        "--id",
                        mixed["stable_id"],
                        "--version",
                        "1.0",
                        "--passport-digest",
                        mixed_result["passport_digest"],
                    ]
                )
                assert fork["artifact_format"] == "ai-stp-setup-definition/2"
                assert stored_definition(fork)["embedded"] == definition["embedded"]
                request_path = root / "embedded-draft.json"
                request: dict[str, Any] = {
                    "harness_id": "codex",
                    "name": "Revised embedded setup",
                    "description": "Keep exact embedded bytes across authoring.",
                    "purpose": "Review changes",
                    "requirements": {},
                    "members": [
                        {key: ref[key] for key in ("stable_id", "version", "passport_digest")}
                        for ref in fork["components"]
                    ],
                }
                request_path.write_text(json.dumps(request), encoding="utf-8")
                update_args = [
                    "setup",
                    "passport",
                    "update",
                    "plan",
                    "--state-dir",
                    str(state),
                    "--id",
                    fork["stable_id"],
                    "--expected-revision",
                    fork["revision_id"],
                    "--request",
                    str(request_path),
                ]
                revised = owned_apply(update_args)
                assert stored_definition(revised)["embedded"] == definition["embedded"]
                released = owned_apply(
                    [
                        "setup",
                        "version",
                        "release",
                        "plan",
                        "--state-dir",
                        str(state),
                        "--id",
                        fork["stable_id"],
                        "--expected-revision",
                        revised["revision_id"],
                        "--increment",
                        "minor",
                    ]
                )
                retained_definition = stored_definition(released)
                assert released["version"] == "1.1"
                assert retained_definition["version"] == "1.1"
                assert retained_definition["embedded"] == definition["embedded"]
                # An explicit removal has a real format transition, while the old
                # immutable version and its embedded index remain available.
                request["members"] = [
                    ref for ref in request["members"] if ref["stable_id"] != embedded_id
                ]
                request_path.write_text(json.dumps(request), encoding="utf-8")
                update_args[update_args.index("--expected-revision") + 1] = revised["revision_id"]
                removed = owned_apply(update_args)
                assert removed["artifact_format"] == "ai-stp-setup-definition/1"
                assert "embedded" not in stored_definition(removed)
                assert stored_definition(released) == retained_definition
            finally:
                db.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
