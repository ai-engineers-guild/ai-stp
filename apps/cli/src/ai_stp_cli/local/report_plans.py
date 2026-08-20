"""Durable exact report previews and replay-safe submission state."""

import sqlite3
from dataclasses import dataclass
from typing import cast

from ai_stp_contracts.reports import ReportCaseCreateRequest, ReportCaseResponse
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id


@dataclass(frozen=True)
class StoredPlan:
    plan_id: str
    plan_digest: str
    request: ReportCaseCreateRequest
    created_at: str
    submitted: ReportCaseResponse | None


def prepare(
    connection: sqlite3.Connection, request: ReportCaseCreateRequest, *, at: str
) -> StoredPlan:
    document = cast(dict[str, JsonValue], request.model_dump(mode="json"))
    plan_digest = digest_canonical("ai-stp:plan:v1", document)
    held = by_digest(connection, plan_digest)
    if held is not None:
        return held
    plan_id = new_id("plan")
    connection.execute(
        "INSERT INTO report_plan "
        "(plan_id, plan_digest, request_json, created_at) VALUES (?, ?, ?, ?)",
        (plan_id, plan_digest, request.model_dump_json(), at),
    )
    connection.commit()
    return StoredPlan(plan_id, plan_digest, request, at, None)


def get(connection: sqlite3.Connection, plan_id: str) -> StoredPlan | None:
    row = connection.execute("SELECT * FROM report_plan WHERE plan_id = ?", (plan_id,)).fetchone()
    return None if row is None else _stored(row)


def by_digest(connection: sqlite3.Connection, digest: str) -> StoredPlan | None:
    row = connection.execute(
        "SELECT * FROM report_plan WHERE plan_digest = ?", (digest,)
    ).fetchone()
    return None if row is None else _stored(row)


def submitted(
    connection: sqlite3.Connection, plan_id: str, result: ReportCaseResponse
) -> StoredPlan:
    connection.execute(
        "UPDATE report_plan SET submitted_case = ? WHERE plan_id = ?",
        (result.model_dump_json(), plan_id),
    )
    connection.commit()
    held = get(connection, plan_id)
    assert held is not None
    return held


def _stored(row: sqlite3.Row) -> StoredPlan:
    raw_result = row["submitted_case"]
    return StoredPlan(
        plan_id=str(row["plan_id"]),
        plan_digest=str(row["plan_digest"]),
        request=ReportCaseCreateRequest.model_validate_json(str(row["request_json"])),
        created_at=str(row["created_at"]),
        submitted=(
            None if raw_result is None else ReportCaseResponse.model_validate_json(str(raw_result))
        ),
    )
