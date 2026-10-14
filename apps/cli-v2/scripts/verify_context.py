"""Real process proof for private developer declarations in the preview registry."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from ai_stp_cli.local import revisions, sync_merge
from ai_stp_contracts.cli.components import PassportView
from ai_stp_contracts.cli.sync import SyncPreview
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports.envelope import seal_envelope


def prove(
    root: Path,
    state: Path,
    invoke: Callable[..., Any],
    apply: Callable[..., Any],
) -> None:
    database = state / "ai-stp-v2-state" / "registry.sqlite3"

    def counts() -> tuple[int, int, int]:
        with closing(sqlite3.connect(database)) as connection:
            return connection.execute(
                "SELECT (SELECT count(*) FROM entity),"
                "(SELECT count(*) FROM revision),(SELECT count(*) FROM operation)"
            ).fetchone()

    before = counts()
    initialization = ["passport", "developer", "initialize", "plan", "--state-dir", str(state)]
    plan = invoke(initialization)
    assert counts() == before
    developer = apply(plan, "developer-init")
    assert developer["facts"] == {} and developer["visibility"] == "private"
    assert counts() == tuple(value + 1 for value in before)
    show = [
        "local",
        "passport",
        "show",
        "--kind",
        "developer",
        "--id",
        developer["stable_id"],
        "--state-dir",
        str(state),
    ]
    view = PassportView.model_validate(invoke(show))
    assert view.revision_id == developer["revision_id"]
    patch = root / "developer-patch.json"
    patch.write_text(
        json.dumps({"role": "Engineer", "preferred_languages": ["Rust"]}), encoding="utf-8"
    )
    command = [
        "passport",
        "developer",
        "update",
        "plan",
        "--state-dir",
        str(state),
        "--expected-revision",
        developer["revision_id"],
        "--patch",
        str(patch),
    ]
    before = counts()
    planned = invoke(command)
    assert counts() == before
    updated = apply(planned, "developer-update")
    assert updated["facts"]["role"]["confirmation"] == "user_confirmed"
    assert updated["facts"]["preferred_languages"]["value"] == ["Rust"]
    assert updated["parent_revision_ids"] == [developer["revision_id"]]
    invoke(command, 4)
    initialized_again = apply(invoke(initialization), "developer-init-again")
    assert initialized_again["revision_id"] == updated["revision_id"]
    assert apply(plan, "developer-initial-replay") == developer
    assert invoke(show)["revision_id"] == updated["revision_id"]
    command[command.index("--expected-revision") + 1] = updated["revision_id"]
    noop = apply(invoke(command), "developer-unchanged")
    assert noop["revision_id"] == updated["revision_id"]
    patch.write_text('{"operating_system":"linux"}', encoding="utf-8")
    before = counts()
    invoke(command, 2)
    assert counts() == before
    prove_merge(state, invoke, apply, updated)


def prove_merge(
    state: Path,
    invoke: Callable[..., Any],
    apply: Callable[..., Any],
    base: dict[str, Any],
) -> None:
    """The existing Python graph and merger are an independent native oracle."""
    preview = [
        "sync",
        "preview",
        "--state-dir",
        str(state),
        "--id",
        base["stable_id"],
        "--account-id",
        base["owner_id"],
    ]
    assert SyncPreview.model_validate(invoke(preview)).state == "up_to_date"
    left, right = deepcopy(base), deepcopy(base)
    for document in (left, right):
        document["parent_revision_ids"] = [base["revision_id"]]
        document.pop("revision_id")
    left["facts"]["role"]["value"] = "Reviewer"
    right["facts"]["preferred_languages"]["value"] = ["Rust", "Python"]
    database = state / "ai-stp-v2-state" / "registry.sqlite3"
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.row_factory = sqlite3.Row
        device = connection.execute(
            "SELECT device_id FROM revision WHERE revision_id=?", (base["revision_id"],)
        ).fetchone()[0]
        a = revisions.commit(connection, left, device_id=device)
        b = revisions.commit(connection, right, device_id=device)

    def body(document: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in document.items()
            if key not in {"revision_id", "parent_revision_ids"}
        }

    outcome = sync_merge.merge_documents(body(base), body(left), body(right))
    assert outcome.document is not None and not outcome.conflicts
    candidate = seal_envelope(
        {
            **outcome.document,
            "parent_revision_ids": cast(JsonValue, sorted([a.revision_id, b.revision_id])),
        }
    )
    report = SyncPreview.model_validate(invoke(preview))
    assert report.state == "merge_ready" and report.candidate_revision_id == candidate.revision_id
    assert report.common_ancestor_revision_id == base["revision_id"]
    plan = invoke(["sync", "merge", "plan", "--state-dir", str(state), "--id", base["stable_id"]])
    assert plan["plan"]["operation"]["passport"] == candidate.model_dump(mode="json")
    merged = apply(plan, "developer-merge")
    assert merged == candidate.model_dump(mode="json")
    assert SyncPreview.model_validate(invoke(preview)).state == "up_to_date"
