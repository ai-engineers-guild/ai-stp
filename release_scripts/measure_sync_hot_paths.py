"""Measure the private-sync hot paths `#256` R05 keeps explicit.

`is_ancestor` was bounded in `#406` — an early stop at the requested
ancestor, not a rewritten walk. The remaining surfaces named by the issue —
private-sync ancestor walks, common-ancestor selection, large graphs, page
application, cold/warm task overhead — are measured here rather than
changed: denominators are graph sizes and page sizes, and every row records
the real sqlite statement count via ``set_trace_callback`` on the measured
connection, plus wall-clock milliseconds.

Nothing in this script replaces the measured path. Event pages are produced
by the real ``sync_state.prepare`` on a second "remote" registry and applied
by the real ``apply_page``; ancestor calls hit the shipped functions. A row
marked ``"fixture"`` records setup cost, never a verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from ai_stp_cli.application import sync as sync_app
from ai_stp_cli.local import passports, revisions, sync_state
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.sync import SyncEventReceipt, SyncPullResponse, SyncStreamEvent
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id

CHAIN: Final[int] = 10_000
BRANCH: Final[int] = 5_000
PAGE: Final[int] = 100
ACCOUNT: Final[str] = "account_01KZAA000000000000000000B1"
DEVICE: Final[str] = "device_01KZAA000000000000000000A0"


def _content(stable_id: str, owner: str, at: str, **extra: JsonValue) -> dict[str, JsonValue]:
    """The smallest passport document the local registry accepts."""
    document: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "developer",
        "stable_id": stable_id,
        "owner_id": owner,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {},
    }
    document.update(extra)
    return document


def _counted[T](
    connection: sqlite3.Connection,
    operation: str,
    graph: str,
    size: int,
    fn: Callable[[], T],
    *,
    catch: tuple[type[Exception], ...] = (),
) -> tuple[T | None, dict[str, object]]:
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    started = time.perf_counter()
    result: T | None = None
    error: str | None = None
    try:
        result = fn()
    except catch as failure:
        error = type(failure).__name__
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        connection.set_trace_callback(None)
    row: dict[str, object] = {
        "operation": operation,
        "graph": graph,
        "size": size,
        "sql_statements": len(statements),
        "elapsed_ms": elapsed_ms,
        "role": "measurement",
    }
    if error is not None:
        # A crashed operation still reports what it spent before dying: the
        # statement count up to the crash is part of the evidence.
        row["error"] = error
    return result, row


def _fixture(operation: str, graph: str, size: int, elapsed_ms: float) -> dict[str, object]:
    return {
        "operation": operation,
        "graph": graph,
        "size": size,
        "elapsed_ms": elapsed_ms,
        "role": "fixture",
    }


def _linear_chain(
    connection: sqlite3.Connection, stable_id: str, owner: str, at: str, count: int
) -> list[revisions.StoredRevision]:
    chain: list[revisions.StoredRevision] = []
    for _ in range(count):
        chain.append(
            revisions.commit(
                connection,
                _content(
                    stable_id,
                    owner,
                    at,
                    parent_revision_ids=[chain[-1].revision_id] if chain else [],
                ),
                device_id=DEVICE,
            )
        )
    return chain


def _fork_graph(
    connection: sqlite3.Connection, stable_id: str, owner: str, at: str, depth: int
) -> tuple[
    list[revisions.StoredRevision],
    list[revisions.StoredRevision],
    list[revisions.StoredRevision],
]:
    """A shared base extended independently on two sides, then left unmerged."""
    base = _linear_chain(connection, stable_id, owner, at, depth)
    left: list[revisions.StoredRevision] = list(base)
    right: list[revisions.StoredRevision] = list(base)
    for index in range(depth):
        left.append(
            revisions.commit(
                connection,
                _content(
                    stable_id,
                    owner,
                    at,
                    parent_revision_ids=[left[-1].revision_id],
                    facts={
                        "side": {
                            "value": f"left:{index}",
                            "origin": "declared",
                            "confirmation": "none",
                        },
                    },
                ),
                device_id=DEVICE,
            )
        )
        right.append(
            revisions.commit(
                connection,
                _content(
                    stable_id,
                    owner,
                    at,
                    parent_revision_ids=[right[-1].revision_id],
                    facts={
                        "side": {
                            "value": f"right:{index}",
                            "origin": "declared",
                            "confirmation": "none",
                        },
                    },
                ),
                device_id=DEVICE,
            )
        )
    return base, left, right


def _push_order_walk(connection: sqlite3.Connection, head: revisions.StoredRevision) -> int:
    """The shipped `sync push` order walk — imported, not copied."""
    return len(sync_app._push_order(connection, head))  # pyright: ignore[reportPrivateUsage]


def _stream_events(
    remote: sqlite3.Connection, chain: list[revisions.StoredRevision]
) -> list[SyncStreamEvent]:
    """Real `SyncEvent`s minted by `prepare`, each receipted `accepted` so the
    next child's `prepare` resolves its remote parents — the push flow's own
    shape, run on a second registry standing in for the account."""
    events: list[SyncStreamEvent] = []
    for index, stored in enumerate(chain, start=1):
        pending = sync_state.prepare(remote, account_id=ACCOUNT, device_id=DEVICE, stored=stored)
        request = pending.request
        sync_state.record_receipt(
            remote,
            account_id=ACCOUNT,
            receipt=SyncEventReceipt(
                event_id=request.event_id,
                state="accepted",
                revision_id=request.revision_id,
                server_head_revision_id=request.revision_id,
                cursor=f"cursor-{index}",
                conflict=None,
                conflicting_entity_id=None,
                error_code=None,
            ),
        )
        events.append(
            SyncStreamEvent(
                **request.model_dump(
                    exclude={"idempotency_key", "expected_head_revision_id"}, mode="python"
                ),
                sequence=index,
            )
        )
    return events


def _page(events: list[SyncStreamEvent]) -> SyncPullResponse:
    return SyncPullResponse(items=events, page=PageInfo(next_cursor=None, page_size=len(events)))


def _task_overhead() -> list[dict[str, object]]:
    """Cold and warm `task intents` wall time on an isolated HOME.

    Cold runs the schema migrations a first start pays for; warm repeats on
    the same home. A subprocess measure, not an envelope claim.
    """
    cli = Path(sys.executable).parent / "ai-stp"
    if not cli.is_file():
        return [
            {
                "operation": "task-intents",
                "graph": "cli",
                "size": 0,
                "role": "fixture",
                "skipped": "ai-stp console script not next to the interpreter",
            }
        ]
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-hotpath-") as tmp:
        env = {
            **os.environ,
            "HOME": tmp,
            "XDG_CONFIG_HOME": str(Path(tmp) / ".config"),
            "XDG_DATA_HOME": str(Path(tmp) / ".local" / "share"),
            "XDG_STATE_HOME": str(Path(tmp) / ".local" / "state"),
            "AI_STP_FORCE_FILE_CREDENTIAL_STORE": "1",
        }
        for name in ("cold", "warm"):
            started = time.perf_counter()
            run = subprocess.run(
                [str(cli), "task", "intents", "--json"],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            rows.append(
                {
                    "operation": f"task-intents:{name}",
                    "graph": "cli",
                    "size": 1,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                    "exit_code": run.returncode,
                    "role": "measurement",
                }
            )
    return rows


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Write the JSON evidence record here.")
    parser.add_argument("--chain", type=int, default=CHAIN)
    parser.add_argument("--branch", type=int, default=BRANCH)
    parser.add_argument("--page", type=int, default=PAGE)
    options = parser.parse_args(arguments)

    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-hotpaths-") as tmp:
        registry = open_registry(Path(tmp) / "registry.sqlite")
        try:
            owner, stable_id, at = (
                new_id("account"),
                new_id("developer"),
                passports.moment(),
            )

            started = time.perf_counter()
            chain = _linear_chain(registry, stable_id, owner, at, options.chain)
            rows.append(
                _fixture(
                    "build:linear-chain",
                    "linear",
                    options.chain,
                    round((time.perf_counter() - started) * 1000, 1),
                )
            )
            head = chain[-1]

            _, row = _counted(
                registry,
                "is_ancestor:immediate-parent",
                "linear",
                options.chain,
                lambda: revisions.is_ancestor(registry, chain[-2].revision_id, head.revision_id),
            )
            rows.append(row)
            _, row = _counted(
                registry,
                "is_ancestor:base-ancestor",
                "linear",
                options.chain,
                lambda: revisions.is_ancestor(registry, chain[0].revision_id, head.revision_id),
            )
            rows.append(row)
            _, row = _counted(
                registry,
                "is_ancestor:absent",
                "linear",
                options.chain,
                lambda: revisions.is_ancestor(
                    registry,
                    "revision_" + "0" * 64,
                    head.revision_id,
                ),
            )
            rows.append(row)

            base_ancestor, row = _counted(
                registry,
                "common_ancestor:head-vs-base",
                "linear",
                options.chain,
                lambda: revisions.common_ancestor(registry, head.revision_id, chain[0].revision_id),
            )
            rows.append(row)
            _, row = _counted(
                registry,
                "common_ancestor:repeat",
                "linear",
                options.chain,
                lambda: revisions.common_ancestor(registry, head.revision_id, chain[0].revision_id),
            )
            rows.append(row)

            started = time.perf_counter()
            _, left, right = _fork_graph(registry, stable_id, owner, at, options.branch)
            fork_size = options.branch * 3 - 1
            rows.append(
                _fixture(
                    "build:fork",
                    "fork",
                    fork_size,
                    round((time.perf_counter() - started) * 1000, 1),
                )
            )
            fork_ancestor, row = _counted(
                registry,
                "common_ancestor:diverged-heads",
                "fork",
                fork_size,
                lambda: revisions.common_ancestor(
                    registry, left[-1].revision_id, right[-1].revision_id
                ),
            )
            rows.append(row)

            visited: int | None = None
            for depth in (250, 500, options.chain):
                if depth > options.chain:
                    continue
                walked, row = _counted(
                    registry,
                    "push-order-dfs-walk",
                    "linear",
                    depth,
                    lambda depth=depth: _push_order_walk(registry, chain[depth - 1]),
                    catch=(RecursionError,),
                )
                row["recursion_limit"] = sys.getrecursionlimit()
                rows.append(row)
                if depth == options.chain:
                    visited = walked

            window = chain[-options.page :]
            _, row = _counted(
                registry,
                "payload_for:head-page",
                "linear",
                len(window),
                lambda: [
                    sync_state.payload_for(
                        registry, candidate, include_versions=index == len(window) - 1
                    )
                    for index, candidate in enumerate(window)
                ],
            )
            rows.append(row)
            _, row = _counted(
                registry,
                "mapping_for_local:head-page",
                "linear",
                len(window),
                lambda: [
                    sync_state.mapping_for_local(
                        registry,
                        account_id=ACCOUNT,
                        local_revision_id=candidate.revision_id,
                    )
                    for candidate in window
                ],
            )
            rows.append(row)

            _, row = _counted(
                registry,
                "heads:single-entity",
                "linear",
                1,
                lambda: revisions.heads(registry, stable_id),
            )
            rows.append(row)

            # A "remote" registry mints a real one-page event stream; the
            # measured `apply_page` consumes it on this registry.
            started = time.perf_counter()
            remote = open_registry(Path(tmp) / "remote.sqlite")
            try:
                remote_owner = new_id("account")
                remote_chain = _linear_chain(remote, stable_id, remote_owner, at, options.page)
                events = _stream_events(remote, remote_chain)
            finally:
                remote.close()
            rows.append(
                _fixture(
                    "build:event-page",
                    "linear",
                    options.page,
                    round((time.perf_counter() - started) * 1000, 1),
                )
            )

            counted, row = _counted(
                registry,
                "apply_page:apply",
                "linear",
                len(events),
                lambda: sync_state.apply_page(
                    registry, account_id=ACCOUNT, response=_page(events), at=passports.moment()
                ),
            )
            assert counted is not None
            applied, replayed, skipped = counted
            row["applied"], row["replayed"], row["skipped"] = applied, replayed, len(skipped)
            rows.append(row)
            counted, row = _counted(
                registry,
                "apply_page:replay",
                "linear",
                len(events),
                lambda: sync_state.apply_page(
                    registry, account_id=ACCOUNT, response=_page(events), at=passports.moment()
                ),
            )
            assert counted is not None
            applied, replayed, skipped = counted
            row["applied"], row["replayed"], row["skipped"] = applied, replayed, len(skipped)
            rows.append(row)
        finally:
            registry.close()

    rows.extend(_task_overhead())

    summary = {
        "subject": "sync-hot-paths",
        "issue": "ai-stp#256 R05",
        "chain": options.chain,
        "branch": options.branch,
        "page": options.page,
        "asserted": {
            "base_ancestor_found": getattr(base_ancestor, "revision_id", None)
            == chain[0].revision_id,
            "fork_ancestor_found": getattr(fork_ancestor, "revision_id", None)
            == _ancestor_expected(chain, left, right),
            "dfs_walk_visited": visited == options.chain,
        },
        "rows": rows,
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    if options.out is not None:
        options.out.parent.mkdir(parents=True, exist_ok=True)
        options.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _ancestor_expected(
    chain: list[revisions.StoredRevision],
    left: list[revisions.StoredRevision],
    right: list[revisions.StoredRevision],
) -> str | None:
    """The shared base tip both fork heads descend from."""
    shared = {item.revision_id for item in left} & {item.revision_id for item in right}
    ordered = [item.revision_id for item in chain if item.revision_id in shared]
    return ordered[-1] if ordered else None


if __name__ == "__main__":
    raise SystemExit(main())
