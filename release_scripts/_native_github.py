"""Selected private source evidence; only upstream GitHub is synthetic."""

from __future__ import annotations

import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
from release_scripts._evidence import EvidenceError, without_credentials
from release_scripts._native_client import NativeClient
from tests.api.platform.test_github_connector import COMMIT, ROOT, GitHub


@dataclass
class SelectedGitHub(GitHub):
    source: Path | None = None
    snapshots: int = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/tarball/" + COMMIT):
            return super().handle(request)
        assert self.source is not None and request.method == "GET"
        assert request.headers["authorization"] == f"Bearer {self.token}"
        self.snapshots += 1
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            payload = self.source.read_bytes()
            member = tarfile.TarInfo("snapshot/skills/review-beta/SKILL.md")
            member.size, member.mode = len(payload), 0o644
            archive.addfile(member, io.BytesIO(payload))
        return httpx.Response(200, content=output.getvalue())


def connect(web: httpx.Client) -> None:
    response = web.post(
        ROOT + "/connect", json={"purpose": "source", "confirmed": True, "mode": "authorize"}
    )
    assert response.status_code == 200
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    response = web.get(ROOT + "/callback", params={"state": state, "code": uuid4().hex})
    assert response.status_code == 303


def prepare(
    native: NativeClient, root: Path, document: dict[str, Any], upstream: SelectedGitHub
) -> dict[str, Any]:
    upstream.source = root / "review-beta" / "source" / "SKILL.md"
    status = native.invoke(root, "github", "status", "--state-dir", root)
    without_credentials(status)
    connection = next(v for v in status["response"]["connections"] if v["purpose"] == "source")
    repositories = connection["repositories"]
    assert [v["repository_id"] for v in repositories] == [42]
    path = root / "selected-source-request.json"
    request = {
        "installation_id": 3,
        "repository_id": 42,
        "commit": COMMIT,
        "subpath": "skills/review-beta",
        "idempotency_key": "native-publication-selected-source",
    }
    path.write_text(json.dumps(request))
    args = ("github", "source", "plan", "--state-dir", root, "--request", path)
    prepared = native.invoke(root, *args)
    # The bridge commits this request and then drops its response once.
    lost = native.apply(root, prepared, ("github", "source", "apply"), ok=False)
    assert lost["error"]["code"] == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert native.account(root, "refresh")["outcome"] == "authorized"
    stale = native.apply(root, prepared, ("github", "source", "apply"), ok=False)
    assert stale["error"]["code"] == "AI_STP_PRECONDITION_FAILED"
    fresh = native.invoke(root, *args)
    assert fresh["plan"]["request"] == prepared["plan"]["request"] == request
    result = native.apply(root, fresh, ("github", "source", "apply"))
    without_credentials(result)
    binding = result["response"]
    sources = [v["source_artifact"] for v in document["adaptations"]]
    if not sources or any(v["digest"] != binding["content_digest"] for v in sources):
        raise EvidenceError("selected source bytes differ from the authored component artifact")
    if any(v["size_bytes"] != binding["size_bytes"] for v in sources):
        raise EvidenceError("selected source byte count differs from the authored artifact")
    assert binding["content_digest"] != document["artifact"]["digest"]
    if binding["artifact_inventory"] != ["SKILL.md"]:
        raise EvidenceError("selected source inventory differs from the authored skill")
    if binding["source_visibility"] != "private" or document["source"] is not None:
        raise EvidenceError("selected private source acquired public coordinates or visibility")
    # A successful historical binding cannot bypass current selected access.
    upstream.selected = False
    try:
        refusal = native.apply(root, fresh, ("github", "source", "apply"), ok=False)
        assert refusal["error"]["details"]["reason"] == "permission_denied"
    finally:
        upstream.selected = True
    assert upstream.snapshots == 1 and upstream.writes == 0
    native.scenarios["selected_source_exact_lost_reply_refresh_access_recheck"] = "passed"
    return binding
