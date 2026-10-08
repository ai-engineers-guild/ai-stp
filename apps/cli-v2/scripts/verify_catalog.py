"""Published contract corpus through real TCP, including historical bytes and cache refusal."""

from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Callable
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ai_stp_contracts.cli.catalog import CatalogObjectView, CatalogSearchResult, CatalogVersionView
from ai_stp_contracts.fixtures import FixtureCase, load_cases
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports.versions import ComponentVersionPassport

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]
OPERATIONS = {
    "searchComponents",
    "searchSetups",
    "readComponent",
    "readSetup",
    "readComponentVersion",
    "readSetupVersion",
}


class CatalogServer(ThreadingHTTPServer):
    status: int = 200
    body: bytes = b"{}"
    schema: str = "1"
    requests: list[tuple[str, dict[str, str]]]

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), CatalogHandler)
        self.requests = []

    def serve(self, body: Any, status: int = 200) -> None:
        self.status = status
        self.body = json.dumps(body, ensure_ascii=False).encode()
        self.schema = "1"


class CatalogHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        assert isinstance(self.server, CatalogServer)
        server = self.server
        server.requests.append(
            (self.path, {key.lower(): value for key, value in self.headers.items()})
        )
        self.send_response(server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-AI-STP-Schema-Version", server.schema)
        self.send_header("Location", "/redirect-must-not-be-followed")
        self.send_header("Content-Length", str(len(server.body)))
        self.end_headers()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(server.body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def arguments(case: FixtureCase) -> list[str]:
    kind = "component" if "Component" in case.operation_id else "setup"
    args = ["registry"]
    if case.operation_id.startswith("search"):
        args.extend(["search", "--kind", kind])
        for key, flag in [("q", "--query"), ("page_size", "--limit")]:
            if key in case.request.query:
                args.extend([flag, str(case.request.query[key])])
        if case.request.query.get("include_experimental"):
            args.append("--include-experimental")
    else:
        command = "version" if case.operation_id.endswith("Version") else "show"
        args.extend([command, "--kind", kind, "--id", case.request.path_params["stable_id"]])
        if command == "version":
            args.extend(["--version", case.request.path_params["version"]])
    return args


def prove(binary: Path, home: Path, root: Path, run: Runner) -> None:
    with CatalogServer() as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            prove_reads(binary, home, root, run, server)
        finally:
            server.shutdown()
            thread.join(timeout=5)


def prove_reads(binary: Path, home: Path, root: Path, run: Runner, server: CatalogServer) -> None:
    config = root / "catalog.yaml"
    config.write_text(f"catalog:\n  url: http://127.0.0.1:{server.server_port}\n", encoding="utf-8")
    common = ["--config", str(config)]
    for case in load_cases():
        if case.operation_id not in OPERATIONS or case.kind == "rejected_request":
            continue
        server.serve(case.body)
        expected = 0 if case.kind == "positive" else 4
        result = run(binary, home, [*arguments(case), *common], expected)
        if expected == 0:
            view = result["data"]
            model = (
                CatalogSearchResult
                if case.operation_id.startswith("search")
                else CatalogVersionView
                if case.operation_id.endswith("Version")
                else CatalogObjectView
            )
            model.model_validate(view)
            assert view["source"] == "online", case.case_id
            if case.operation_id.endswith("Version"):
                assert case.body is not None
                assert view["passport"] == case.body["passport"], case.case_id
            if case.operation_id.startswith("search"):
                path, headers = server.requests[-1]
                query = parse_qs(urlsplit(path).query)
                assert query["page_size"] == [str(case.request.query.get("page_size", 20))]
                assert headers["x-ai-stp-schema-version"] == "1"
                assert "authorization" not in headers and "cookie" not in headers
    case = next(c for c in load_cases() if c.case_id == "readComponentVersion.published")
    body: dict[str, Any] = json.loads(json.dumps(dict(case.body or {})))
    corpus = json.loads(
        files("ai_stp_passports.fixtures")
        .joinpath("safe-markdown-v1.json")
        .read_text(encoding="utf-8")
    )
    for lane, expected in [("accepted", 0), ("rejected", 4)]:
        for vector in corpus[lane]:
            changed = copy.deepcopy(body)
            changed["passport"]["description"] = vector["source"]
            changed["passport_digest"] = digest_canonical("ai-stp:passport:v1", changed["passport"])
            server.serve(changed)
            run(binary, home, [*arguments(case), *common], expected)
    # Cross-field defects remain invalid even with a freshly recomputed digest.
    for defect in ["adaptation_id", "ownership", "parent", "duplicate_harness", "duplicate_tags"]:
        changed = copy.deepcopy(body)
        passport = changed["passport"]
        if defect == "adaptation_id":
            passport["adaptations"][0]["adaptation_id"] = "adaptation_" + "0" * 64
        elif defect == "ownership":
            passport["adaptations"][0]["scope_adaptations"][0]["members"][0]["ownership"] = (
                "contribution"
            )
        elif defect == "parent":
            passport["parent_revision_ids"] = ["revision_" + "0" * 64]
        elif defect == "duplicate_harness":
            passport["adaptations"].append(copy.deepcopy(passport["adaptations"][0]))
        else:
            passport["tags"].append(passport["tags"][0])
        try:
            ComponentVersionPassport.model_validate(passport)
        except ValueError:
            pass
        else:
            raise AssertionError(f"oracle did not reject {defect}")
        changed["passport_digest"] = digest_canonical("ai-stp:passport:v1", passport)
        server.serve(changed)
        run(binary, home, [*arguments(case), *common], 4)
    # A legitimate old snapshot omits a later nullable provenance field. The
    # catalog digest addresses these wire bytes, not a current model dump.
    body["passport"].pop("origin_harness_id", None)
    body["passport"]["unknown_future_field"] = "e\u0301"
    body["passport_digest"] = digest_canonical("ai-stp:passport:v1", body["passport"])
    server.serve(body)
    cache = root / "catalog-cache"
    cache.mkdir()
    args = [*arguments(case), *common, "--cache-dir", str(cache)]
    online = run(binary, home, args, 0)["data"]
    assert online["passport"] == body["passport"]
    assert online["passport_digest"] == body["passport_digest"]
    requests = len(server.requests)
    offline = run(binary, home, [*args, "--offline"], 0)["data"]
    assert len(server.requests) == requests
    assert offline == {**online, "source": "cache"}
    server.serve({}, 503)
    assert run(binary, home, args, 0)["data"] == offline
    for status, expected in [(404, 2), (403, 4), (301, 4)]:
        server.serve({}, status)
        requests = len(server.requests)
        run(binary, home, args, expected)
        assert len(server.requests) == requests + 1, "redirect or request was repeated"
    substituted = copy.deepcopy(body)
    substituted["passport"]["name"] = "substituted"
    server.serve(substituted)
    run(binary, home, args, 4)
    server.serve(body)
    server.schema = "2"
    run(binary, home, args, 4)
    server.serve(body)
    server.body = b'{"schema_version":1,"schema_version":1}'
    run(binary, home, args, 4)
    server.body = b" " * (8 * 1024 * 1024 + 1)
    run(binary, home, args, 4)
    assert run(binary, home, [*args, "--offline"], 0)["data"] == offline
    # Cache corruption must never become an answer, even when the server is down.
    entry = next((cache / "ai-stp-v2-catalog").glob("*.json"))
    held = entry.read_bytes()
    corrupted = json.loads(held)
    corrupted["document"]["passport"]["name"] = "corrupted"
    entry.write_text(json.dumps(corrupted), encoding="utf-8")
    run(binary, home, [*args, "--offline"], 4)
    entry.write_bytes(held)
    if os.name != "nt":
        import fcntl

        with (cache / "ai-stp-v2-catalog" / "lock").open("rb+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(binary, home, [*args, "--offline"], 4)
        entry.unlink()
        entry.symlink_to(config)
        run(binary, home, [*args, "--offline"], 4)
        entry.unlink()
        entry.write_bytes(held)
    # Fill through the public transport to exercise the real eviction boundary.
    held_args = [*args]
    for number in range(65):
        held_body = copy.deepcopy(body)
        identifier = f"component_{number:026d}"
        held_body["passport"]["stable_id"] = identifier
        held_body["passport_digest"] = digest_canonical("ai-stp:passport:v1", held_body["passport"])
        server.serve(held_body)
        held_args = [*args]
        held_args[held_args.index("--id") + 1] = identifier
        run(binary, home, held_args, 0)
    assert len(list((cache / "ai-stp-v2-catalog").glob("*.json"))) == 64
    assert run(binary, home, [*held_args, "--offline"], 0)["data"]["source"] == "cache"
    requests = len(server.requests)
    for url in [
        "http://example.com",
        "http://127.1",
        "https://user:secret@example.com",
        "https://example.com?q=x",
    ]:
        config.write_text(f"catalog:\n  url: {url}\n", encoding="utf-8")
        run(binary, home, args, 2)
    config.write_text("catalog:\n  enabled: false\n", encoding="utf-8")
    run(binary, home, args, 4)
    assert len(server.requests) == requests
    assert not list(home.iterdir()), "catalog read created ambient user state"
