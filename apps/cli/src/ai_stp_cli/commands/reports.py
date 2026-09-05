"""Preview, submit and recover closed report cases without leaking local data."""

import os
import re
import stat
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import reports, session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import report_plans
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.reports import (
    CliReportCaseView,
    CliReportListView,
    CliReportPreview,
    CountryRequest,
    ReportCaseCreateRequest,
    ReportCaseResponse,
    ServiceRequest,
)

MAX_DIAGNOSTICS_BYTES = 4_000
_ABSOLUTE_PATH = re.compile(r"(?:^|\s)(?:/[^\s]+|[A-Za-z]:[\\/][^\s]+)")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:token|secret|password|passwd|api[_-]?key|authorization)\s*[:=]\s*\S+"
)


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value


def _optional(parameters: Mapping[str, object], name: str) -> str:
    return str(parameters.get(name) or "")


def _repeated(parameters: Mapping[str, object], name: str) -> list[str]:
    value = parameters.get(name, ())
    if not isinstance(value, tuple | list):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be repeatable text",
            details={"option": f"--{name}"},
        )
    return [str(item) for item in cast(tuple[object, ...] | list[object], value)]


def _session() -> session.Session:
    return cloud_auth.required("report submission")


def _submit(request: ReportCaseCreateRequest) -> ReportCaseResponse:
    held = _session()
    return reports.create(endpoint(), held.access_token, request)


def _diagnostics(parameters: Mapping[str, object]) -> tuple[str, bool]:
    named = _optional(parameters, "diagnostics-file")
    if not named:
        return "", False
    path = Path(named)
    try:
        before = path.lstat()
    except OSError as error:
        raise CliFailure("AI_STP_NOT_FOUND", "the diagnostics file cannot be opened") from error
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "diagnostics must be a bounded regular file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
        try:
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise CliFailure("AI_STP_CONFLICT", "the diagnostics file changed")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(MAX_DIAGNOSTICS_BYTES + 1)
        finally:
            os.close(descriptor)
    except CliFailure:
        raise
    except OSError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "the diagnostics file is not safely readable"
        ) from error
    if len(raw) > MAX_DIAGNOSTICS_BYTES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "diagnostics exceed the report byte limit",
            details={"limit_bytes": str(MAX_DIAGNOSTICS_BYTES)},
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "diagnostics must be UTF-8 text") from error
    if "\x00" in text or _ABSOLUTE_PATH.search(text) or _SECRET_ASSIGNMENT.search(text):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "diagnostics contain a forbidden absolute path or secret-bearing assignment",
        )
    return text, True


def preview(parameters: Mapping[str, object]) -> Answer[CliReportPreview]:
    diagnostics, previewed = _diagnostics(parameters)
    snapshots = _repeated(parameters, "validation-snapshot-id")
    topic = _optional(parameters, "topic") or "object_report"
    service = None
    country = None
    if topic == "service_request":
        service = ServiceRequest(
            name=_required(parameters, "service-name"),
            primary_url=_required(parameters, "primary-url"),
            description_ru=_required(parameters, "description-ru"),
            description_en=_required(parameters, "description-en"),
            source_url=_required(parameters, "source-url"),
            country_codes=[code.upper() for code in _repeated(parameters, "country-code")],
        )
    elif topic == "country_request":
        country_codes = _repeated(parameters, "country-code")
        if len(country_codes) != 1:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "country_request requires exactly one --country-code",
            )
        country = CountryRequest(
            code=country_codes[0].upper(),
            name_ru=_required(parameters, "name-ru"),
            name_en=_required(parameters, "name-en"),
        )
    object_kind = None
    stable_id = None
    version = None
    content_digest = None
    object_topics = {"object_report", "component_complaint", "ownership_transfer"}
    if topic == "object_report":
        object_kind = _required(parameters, "kind")
        stable_id = _required(parameters, "id")
        version = _required(parameters, "version")
        content_digest = _required(parameters, "content-digest")
    elif topic in object_topics:
        stable_id = _required(parameters, "id")
    request = ReportCaseCreateRequest(
        topic=topic,  # pyright: ignore[reportArgumentType]
        object_kind=object_kind,  # pyright: ignore[reportArgumentType]
        stable_id=stable_id,
        version=version,
        content_digest=content_digest,
        service=service,
        country=country,
        subject=_optional(parameters, "subject"),
        message=_optional(parameters, "message"),
        evidence=_optional(parameters, "evidence"),
        recipient_account_id=_optional(parameters, "recipient") or None,
        author_account_id=_optional(parameters, "author") or None,
        locale=(_optional(parameters, "locale") or "en"),  # pyright: ignore[reportArgumentType]
        harness_id=_optional(parameters, "harness-id"),
        harness_version=_optional(parameters, "harness-version"),
        provider_version=_optional(parameters, "provider-version"),
        operation_id=_optional(parameters, "operation-id"),
        error_code=_optional(parameters, "error-code"),
        validation_snapshot_ids=snapshots,
        diagnostics=diagnostics,
        diagnostics_previewed=previewed,
        vulnerability=parameters.get("vulnerability") is True,
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    with closing(open_registry(configured_path(), create=True)) as connection:
        held = report_plans.prepare(connection, request, at=moment())
    return Answer(
        CliReportPreview(
            plan_id=held.plan_id,
            plan_digest=held.plan_digest,
            report=held.request,
            submitted=held.submitted is not None,
        )
    )


def confirm(parameters: Mapping[str, object]) -> Answer[CliReportCaseView]:
    plan_id = _required(parameters, "plan-id")
    plan_digest = _required(parameters, "plan-digest")
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "report submission requires confirmation of the exact preview digest",
            next_actions=[
                f"report confirm --plan-id {plan_id} --plan-digest {plan_digest} --confirm --json"
            ],
        )
    with closing(open_registry(configured_path(), create=False)) as connection:
        held = report_plans.get(connection, plan_id)
        if held is None:
            raise CliFailure("AI_STP_NOT_FOUND", "the prepared report does not exist")
        if held.plan_digest != plan_digest:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED", "the report preview digest does not match"
            )
        if held.submitted is not None:
            return Answer(CliReportCaseView.model_validate(held.submitted.model_dump(mode="json")))
        try:
            result = _submit(held.request)
        except CliFailure as failure:
            if failure.retryable:
                raise CliFailure(
                    failure.code,
                    failure.message,
                    retryable=True,
                    details=failure.details,
                    next_actions=[
                        f"report confirm --plan-id {plan_id} "
                        f"--plan-digest {plan_digest} --confirm --json"
                    ],
                ) from failure
            raise
        report_plans.submitted(connection, plan_id, result)
    return Answer(CliReportCaseView.model_validate(result.model_dump(mode="json")))


def list_all(_parameters: Mapping[str, object]) -> Answer[CliReportListView]:
    held = cloud_auth.required("report listing")
    result = reports.list_all(endpoint(), held.access_token)
    return Answer(CliReportListView.model_validate(result.model_dump(mode="json")))


def status(parameters: Mapping[str, object]) -> Answer[CliReportCaseView]:
    case_id = _required(parameters, "case-id")
    held = cloud_auth.required("report status")
    result = reports.read(endpoint(), held.access_token, case_id)
    return Answer(CliReportCaseView.model_validate(result.model_dump(mode="json")))
