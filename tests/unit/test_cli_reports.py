"""Report commands preserve exact previews, privacy and replay state."""

from contextlib import closing
from pathlib import Path

import httpx
import pytest

from ai_stp_cli.cloud import reports as transport
from ai_stp_cli.cloud import session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.reports import ReportCaseCreateRequest, ReportCaseResponse

BASE = "https://platform.example"
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
STABLE = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
CASE = "report_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DIGEST = "sha256:" + "b" * 64
KEY = "report-intent-012345"


def _parameters() -> dict[str, object]:
    return {
        "kind": "component",
        "id": STABLE,
        "version": "1.0",
        "content-digest": DIGEST,
        "harness-id": "codex",
        "idempotency-key": KEY,
    }


def _result() -> ReportCaseResponse:
    return ReportCaseResponse(
        case_id=CASE,
        object_kind="component",
        stable_id=STABLE,
        version="1.0",
        state="submitted",
        created_at="2026-08-13T00:00:00.000Z",
    )


def test_report_transport_uses_only_the_authenticated_contract_routes() -> None:
    seen: list[tuple[str, str, str | None]] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("Authorization")))
        if request.method == "GET":
            return httpx.Response(200, json={"schema_version": 1, "items": []})
        return httpx.Response(201, json=_result().model_dump(mode="json"))

    endpoint = Endpoint(BASE, transport=httpx.MockTransport(route))
    request = ReportCaseCreateRequest(
        object_kind="component",
        stable_id=STABLE,
        version="1.0",
        content_digest=DIGEST,
        validation_snapshot_ids=[],
        idempotency_key=KEY,
    )
    transport.create(endpoint, "bearer", request)
    transport.list_all(endpoint, "bearer")

    assert seen == [
        ("POST", "/v1/requests", "Bearer bearer"),
        ("GET", "/v1/requests", "Bearer bearer"),
    ]


def test_preview_is_durable_and_confirm_reuses_it_after_an_unknown_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import reports

    registry = tmp_path / "registry.sqlite3"
    monkeypatch.setattr(reports, "configured_path", lambda: registry)
    monkeypatch.setattr(
        reports,
        "_session",
        lambda: session.Session(
            account_id=ACCOUNT,
            device_id=DEVICE,
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        ),
    )
    attempts: list[str] = []

    def submit(request: ReportCaseCreateRequest) -> ReportCaseResponse:
        attempts.append(request.idempotency_key)
        if len(attempts) == 1:
            raise CliFailure("AI_STP_DEPENDENCY_UNAVAILABLE", "answer lost", retryable=True)
        return _result()

    monkeypatch.setattr(reports, "_submit", submit)

    preview = reports.preview(_parameters()).payload
    repeated = reports.preview(_parameters()).payload
    assert repeated.plan_id == preview.plan_id
    assert repeated.plan_digest == preview.plan_digest
    assert repeated.report.idempotency_key == KEY

    approved = {
        "plan-id": preview.plan_id,
        "plan-digest": preview.plan_digest,
        "confirm": True,
    }
    with pytest.raises(CliFailure) as lost:
        reports.confirm(approved)
    assert lost.value.retryable
    assert lost.value.next_actions == [
        f"report confirm --plan-id {preview.plan_id} "
        f"--plan-digest {preview.plan_digest} --confirm --json"
    ]

    completed = reports.confirm(approved).payload
    replayed = reports.confirm(approved).payload
    assert completed.case_id == CASE
    assert replayed == completed
    assert attempts == [KEY, KEY]

    with closing(open_registry(registry, create=False)) as connection:
        row = connection.execute(
            "SELECT submitted_case FROM report_plan WHERE plan_id = ?", (preview.plan_id,)
        ).fetchone()
    assert row["submitted_case"] is not None


def test_preview_accepts_a_service_without_countries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import reports

    monkeypatch.setattr(reports, "configured_path", lambda: tmp_path / "registry.sqlite3")
    preview = reports.preview(
        {
            "topic": "service_request",
            "service-name": "Worldwide",
            "primary-url": "https://worldwide.example",
            "description-ru": "Глобальный сервис",
            "description-en": "Global service",
            "source-url": "https://worldwide.example/about",
            "country-code": (),
            "validation-snapshot-id": (),
            "idempotency-key": "service-request-0001",
        }
    ).payload

    assert preview.report.topic == "service_request"
    assert preview.report.service is not None
    assert preview.report.service.country_codes == []


def test_report_confirmation_requires_the_exact_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.commands import reports

    monkeypatch.setattr(reports, "configured_path", lambda: tmp_path / "registry.sqlite3")
    preview = reports.preview(_parameters()).payload

    with pytest.raises(CliFailure) as undecided:
        reports.confirm({"plan-id": preview.plan_id, "plan-digest": preview.plan_digest})
    assert undecided.value.code == "AI_STP_USER_DECISION_REQUIRED"

    with pytest.raises(CliFailure) as changed:
        reports.confirm(
            {"plan-id": preview.plan_id, "plan-digest": "sha256:" + "a" * 64, "confirm": True}
        )
    assert changed.value.code == "AI_STP_PRECONDITION_FAILED"


@pytest.mark.parametrize(
    "diagnostics",
    ["TOKEN=secret-value", "failed at /home/person/private/file", "C:\\Users\\me\\secret"],
)
def test_report_diagnostics_fail_closed_before_the_plan_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostics: str
) -> None:
    from ai_stp_cli.commands import reports

    registry = tmp_path / "registry.sqlite3"
    source = tmp_path / "diagnostics.txt"
    source.write_text(diagnostics, encoding="utf-8")
    monkeypatch.setattr(reports, "configured_path", lambda: registry)
    parameters = {**_parameters(), "diagnostics-file": str(source)}

    with pytest.raises(CliFailure) as refused:
        reports.preview(parameters)
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"
    assert diagnostics not in refused.value.message
    assert not registry.exists()


def test_report_commands_are_one_preview_confirm_read_sequence() -> None:
    from ai_stp_cli.registry import COMMANDS

    reports = {item.name: item.descriptor for item in COMMANDS if item.name.startswith("report ")}
    assert set(reports) == {"report confirm", "report list", "report preview", "report status"}
    assert reports["report preview"].mutability == "plan"
    assert reports["report confirm"].confirmation == "explicit_flag"
    assert reports["report list"].mutability == "read"
    assert reports["report status"].mutability == "read"
