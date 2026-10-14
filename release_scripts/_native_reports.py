"""Exact native reporter delivery against the existing API and PostgreSQL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from release_scripts._evidence import without_credentials
from release_scripts._native_client import NativeClient

from ai_stp_contracts.reports import ReportCaseCreateRequest

if TYPE_CHECKING:
    from release_scripts.verify_native_publication import _Server


def confirm(
    native: NativeClient, root: Path, preview: dict[str, Any], *, ok: bool = True
) -> dict[str, Any]:
    result = native.invoke(
        root,
        "report",
        "confirm",
        "--state-dir",
        root,
        "--plan-id",
        preview["plan_id"],
        "--plan-digest",
        preview["plan_digest"],
        "--confirm",
        ok=ok,
    )
    without_credentials(result)
    return result


def prove(
    native: NativeClient, root: Path, server: _Server
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = root / "report-request.json"
    body = {
        "topic": "other",
        "subject": "Native reporter qualification",
        "message": "Cafe\u0301 retains its original spelling.",
        "diagnostics": "The isolated operation failed.",
        "idempotency_key": "native-report-api-original-01",
    }
    request.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    before = len(server.requests)
    preview = native.invoke(root, "report", "preview", "--state-dir", root, "--request", request)
    assert len(server.requests) == before
    outgoing = ReportCaseCreateRequest.model_validate(preview["report"])
    assert outgoing.message == body["message"]
    assert outgoing.diagnostics == body["diagnostics"] and outgoing.diagnostics_previewed
    assert outgoing.idempotency_key != body["idempotency_key"]
    assert (
        native.invoke(root, "report", "preview", "--state-dir", root, "--request", request)
        == preview
    )
    body["message"] = "Changed content must refuse."
    request.write_text(json.dumps(body), encoding="utf-8")
    native.invoke(root, "report", "preview", "--state-dir", root, "--request", request, ok=False)
    native.invoke(
        root,
        "report",
        "confirm",
        "--state-dir",
        root,
        "--plan-id",
        preview["plan_id"],
        "--plan-digest",
        preview["plan_digest"],
        ok=False,
    )
    assert len(server.requests) == before
    server.drop_report = True
    confirm(native, root, preview, ok=False)
    assert not server.drop_report
    request.unlink()
    result = confirm(native, root, preview)
    case = result["case"]
    assert result["historical"] is False
    assert case["topic"] == "other" and case["state"] == "submitted"
    assert all(key not in case for key in ("message", "evidence", "diagnostics", "content_digest"))
    status = native.invoke(
        root, "report", "status", "--state-dir", root, "--case-id", case["case_id"]
    )
    assert status["case"] == case
    page = native.invoke(root, "report", "list", "--state-dir", root)
    assert page["response"]["items"] == [case]
    assert page["response"]["page"]["next_cursor"] is None
    assert sum(r["method"] == "POST" and r["path"] == "/v1/requests" for r in server.requests) == 2
    before = len(server.requests)
    replay = confirm(native, root, preview)
    assert replay["historical"] is True and replay["case"] == case
    assert len(server.requests) == before
    native.scenarios["report_exact_preview_lost_response_and_single_case"] = "passed"
    return preview, result
