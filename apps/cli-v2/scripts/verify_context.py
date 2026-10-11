"""Real process proof for private developer declarations in the preview registry."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from ai_stp_contracts.cli.components import PassportView


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
