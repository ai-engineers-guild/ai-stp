"""Exact native graph proof over genuine immutable passports and SQLite snapshots."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from ai_stp_cli.local import graph, revisions, selection, versions
from ai_stp_cli.local.database import open_registry
from ai_stp_contracts.cli.selection import SetupGraph
from ai_stp_contracts.fixtures import case
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]


def prove(binary: Path, home: Path, temporary: Path, run: Runner) -> None:
    source, snapshot = temporary / "graph.sqlite", temporary / "graph-backup.sqlite"
    base: dict[str, Any] = json.loads(
        json.dumps(dict(case("readComponentVersion.published").body or {}))
    )["passport"]
    with closing(open_registry(source)) as connection:

        def record(document: dict[str, Any]) -> dict[str, str]:
            stored = revisions.commit(connection, document, device_id=new_id("device"))
            digest = digest_canonical("ai-stp:passport:v1", stored.envelope.model_dump(mode="json"))
            versions.record(
                connection,
                stable_id=stored.stable_id,
                version=document["version"],
                passport_digest=digest,
                revision_id=stored.revision_id,
                at=document["created_at"],
            )
            return {
                "stable_id": stored.stable_id,
                "version": document["version"],
                "passport_digest": digest,
            }

        def component(dependencies: list[dict[str, str]], **changes: Any) -> dict[str, str]:
            document = copy.deepcopy(base)
            document.update(stable_id=new_id("component"), requires_components=dependencies)
            document.update(changes)
            return record(document)

        def read(
            roots: list[dict[str, str]], expected: int = 0, proposal: str | None = None
        ) -> dict[str, Any]:
            with closing(sqlite3.connect(snapshot)) as destination:
                connection.backup(destination)
                destination.execute("PRAGMA journal_mode=DELETE")
            before = snapshot.read_bytes()
            args = [
                "select",
                "graph",
                "--snapshot",
                str(snapshot),
                "--sha256",
                "sha256:" + hashlib.sha256(before).hexdigest(),
            ]
            for root in roots:
                args.extend(["--member", root["stable_id"] + "@" + root["version"]])
            if proposal is not None:
                args.extend(["--proposal", proposal])
            result = run(binary, home, args, expected)
            assert snapshot.read_bytes() == before
            if expected:
                return result
            model = SetupGraph.model_validate(result["data"])
            assert model.max_depth == graph.MAX_DEPTH and model.max_nodes == graph.MAX_NODES
            assert result["data"]["max_edges"] == 8192
            assert model.resolved or (not model.nodes and not model.order)
            return result["data"]

        leaf = component([])
        left, right = component([leaf]), component([leaf])
        roots = [left, right]
        result = read(roots)
        expected = graph.resolve(connection, tuple(graph.Reference(**root) for root in roots))
        assert result["resolved"] and result["order"] == list(expected.order)
        assert result == read(list(reversed(roots))), "root order changed the resolved graph"
        assert [node["depth"] for node in result["nodes"]] == [
            node.depth for node in expected.nodes
        ]
        assert len(result["nodes"]) == 3, "shared exact dependency was expanded twice"
        setup: dict[str, Any] = json.loads(
            json.dumps(dict(case("readSetupVersion.published").body or {}))
        )["passport"]
        setup.update(stable_id=new_id("setup"), components=[left, right])
        setup_reference = record(setup)
        assert read([setup_reference])["order"] == [
            *result["order"],
            setup_reference["stable_id"] + "@" + setup_reference["version"],
        ]
        passports: dict[str, revisions.StoredRevision] = {}
        for kind in ["developer", "device", "project"]:
            document: dict[str, Any] = {
                "schema_version": 1,
                "kind": kind,
                "stable_id": new_id(kind),
                "owner_id": base["owner_id"],
                "created_at": base["created_at"],
                "visibility": "private",
                "parent_revision_ids": [],
                "facts": {},
            }
            passports[kind] = revisions.commit(connection, document, device_id=new_id("device"))
        context = selection.Context(
            project_id=passports["project"].stable_id,
            harness_id="claude-code",
            developer_revision=passports["developer"].revision_id,
            device_revision=passports["device"].revision_id,
            project_revision=passports["project"].revision_id,
            policy_version="graph-proof/1",
        )
        proposal = selection.propose(
            connection,
            context=context,
            members=tuple(
                selection.Member(**root, lane="local_owner_or_pinned", lane_reason="proof")
                for root in roots
            ),
            at=base["created_at"],
            expires_at="2099-01-01T00:00:00.000Z",
        )
        assert read([], proposal=proposal.proposal_id) == result
        read([], 2)
        read(roots, 2, proposal=proposal.proposal_id)
        connection.execute(
            "UPDATE proposal SET graph = ? WHERE proposal_id = ?",
            (json.dumps([{**leaf, "version": "latest"}]), proposal.proposal_id),
        )
        assert [item["code"] for item in read([], proposal=proposal.proposal_id)["refusals"]] == [
            "reference_floating"
        ]
        for root, code in [
            (component([{**leaf, "passport_digest": "sha256:" + "0" * 64}]), "digest_mismatch"),
            (component([{**leaf, "stable_id": new_id("component")}]), "dependency_missing"),
            (component([leaf, {**leaf, "version": "99.0"}]), "version_conflict"),
            (component([], lifecycle_state="draft"), "dependency_not_registrable"),
        ]:
            refused = read([root])
            assert [item["code"] for item in refused["refusals"]] == [code]
        connection.execute(
            "INSERT INTO tombstone(stable_id, reason, created_at) VALUES (?, 'proof', ?)",
            (leaf["stable_id"], base["created_at"]),
        )
        assert {item["code"] for item in read(roots)["refusals"]} == {"dependency_not_registrable"}
        connection.execute("DELETE FROM tombstone WHERE stable_id = ?", (leaf["stable_id"],))
        deep = component([])
        for _ in range(graph.MAX_DEPTH + 1):
            deep = component([deep])
        assert {item["code"] for item in read([deep])["refusals"]} == {"closure_too_deep"}
        wide = component([leaf] * 8193)
        assert {item["code"] for item in read([wide])["refusals"]} == {"closure_too_large"}
        connection.execute(
            "UPDATE object_version SET major = 99 WHERE stable_id = ?", (leaf["stable_id"],)
        )
        assert {item["code"] for item in read(roots)["refusals"]} == {"digest_mismatch"}
        read([{**leaf, "version": "latest"}], 2)
    assert not list(home.iterdir())
