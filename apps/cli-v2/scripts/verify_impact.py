"""Real native report envelopes compared with the shared model and local oracle."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from verify_impact_sources import DEVICE, record_setup, release_instruction

from ai_stp_cli.local import cache, content, impact, installation, revisions, versions
from ai_stp_contracts.impact import BlastRadiusReport, SelectionImpactReport
from ai_stp_foundation.ids import new_id
from ai_stp_passports import ComponentVersionPassport, adaptation_for, seal_adaptation

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]


def prove(
    binary: Path, home: Path, state: Path, root: Path, setup: dict[str, Any], run: Runner
) -> None:
    database = state / "ai-stp-v2-state" / "registry.sqlite3"
    price_file = root / "impact-price.json"
    connection = sqlite3.connect(database)
    try:
        connection.row_factory = sqlite3.Row

        def native(args: list[str], expected: int) -> dict[str, Any]:
            nonlocal connection
            # The native owner takes exclusive SQLite access for its lifetime.
            # Retain serial format/oracle checks without keeping a WAL reader
            # alive across the process boundary or discarding fixture writes.
            assert not connection.in_transaction
            connection.close()
            result = run(binary, home, args, expected)
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
            return result

        def read(
            setup_id: str,
            estimator: str,
            profile: dict[str, Any] | None = None,
            expected: int = 0,
            *,
            project_id: str = "",
        ) -> dict[str, Any]:
            args = [
                "select",
                "impact",
                "--state-dir",
                str(state),
                "--setup-id",
                setup_id,
                "--setup-version",
                "1.0",
                "--tokenizer-profile",
                estimator,
            ]
            if project_id:
                args.extend(["--project-id", project_id])
            else:
                args.extend(["--against-setup-id", setup_id, "--against-setup-version", "1.0"])
            if profile is not None:
                price_file.write_text(json.dumps(profile), encoding="utf-8")
                args.extend(["--price-profile", str(price_file)])
            before = tuple(connection.iterdump())
            result = native(args, expected)
            assert tuple(connection.iterdump()) == before
            if expected:
                return result
            model = SelectionImpactReport.model_validate(result["data"])
            assert model.model_dump(mode="json") == result["data"]
            reference = impact.selection_report(
                connection,
                setup_id=setup_id,
                setup_version="1.0",
                baseline_id="" if project_id else setup_id,
                baseline_version="" if project_id else "1.0",
                project_id=project_id,
                estimator_profile=estimator,
                price_profile_path=price_file if profile else None,
                at=model.generated_at,
            )
            assert model == reference
            return result["data"]

        def radius(
            component_id: str, version: str, scenario: str = "update", expected: int = 0
        ) -> dict[str, Any]:
            before = tuple(connection.iterdump())
            result = native(
                [
                    "select",
                    "blast-radius",
                    "--state-dir",
                    str(state),
                    "--component-id",
                    component_id,
                    "--component-version",
                    version,
                    "--scenario",
                    scenario,
                ],
                expected,
            )
            assert tuple(connection.iterdump()) == before
            if expected:
                return result
            model = BlastRadiusReport.model_validate(result["data"])
            assert model.model_dump(mode="json") == result["data"]
            reference = impact.blast_radius(
                connection,
                component_id=component_id,
                component_version=version,
                scenario=scenario,
                at=model.generated_at,
            )
            assert model == reference
            return result["data"]

        exact = "ai-stp:utf8-bytes/1"
        estimated = "ai-stp:unicode-chars-div4/1"
        for estimator in [exact, estimated]:
            read(setup["stable_id"], estimator)
            profile = {
                "schema_version": 1,
                "profile_id": "fixture-price",
                "tokenizer_profile": estimator,
                "model": "fixture-model",
                "currency": "USD",
                "input_per_million": "2.50",
                "source": "https://example.test/price",
                "fetched_at": "2026-01-01T00:00:00.000Z",
                "expires_at": "2099-01-01T00:00:00.000Z",
            }
            for rate in [
                "0",
                "0.005",
                "0.0049999",
                "1",
                "1.00",
                "2.50",
                "000002.5000",
                "123456789.000000001",
            ]:
                read(setup["stable_id"], estimator, {**profile, "input_per_million": rate})
            stale = read(
                setup["stable_id"], estimator, {**profile, "expires_at": "2026-02-01T00:00:00.000Z"}
            )
            assert stale["token_cost"]["status"] == "stale"
            read(setup["stable_id"], estimator, {**profile, "input_per_million": "1e6"}, 2)
            read(setup["stable_id"], estimator, {**profile, "unexpected": True}, 2)

        # Real Python authoring creates an interoperability fixture with distinct
        # source and target instruction bytes. The native executable reads it.
        at = "2026-10-08T00:00:00.000Z"
        target_bytes = "# Codex instruction\nUnicode: café and 👋.\n".encode()
        target = content.put(connection, target_bytes, at=at)
        member = release_instruction(
            connection,
            harness_id="claude-code",
            payload=b"# Claude instruction\n",
            managed_path="CLAUDE.md",
            extra_adaptations=[
                {
                    "harness_id": "codex",
                    "content_digest": target.digest,
                    "content_format": "ai-stp-component-file/1",
                    "managed_paths": ["AGENTS.md"],
                    "scope": "global",
                    "projection_kind": "native_files",
                    "declared_key": "",
                    "source_locator": "",
                    "native_ids": [],
                }
            ],
        )
        target_setup, _ = record_setup(connection, harness_id="codex", member=member)
        connection.commit()
        for scenario in ["update", "deprecation", "blocked", "expired_evidence", "advisory"]:
            affected = radius(member[0], "1.0", scenario)
            assert [item["stable_id"] for item in affected["setup_versions"]] == [target_setup]
        radius(member[0], "9.0", expected=2)
        radius(member[0], "1.0", "invalid", 2)
        measured = read(target_setup, exact)
        assert measured["candidate_context"]["always_tokens"] == len(target_bytes)
        measured = read(target_setup, estimated)
        assert (
            measured["candidate_context"]["always_tokens"] == (len(target_bytes.decode()) + 3) // 4
        )

        held = versions.held(connection, member[0], member[1])
        assert held is not None
        stored = revisions.get(connection, held.revision_id)
        assert stored is not None
        passport = ComponentVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
        adaptation = adaptation_for(passport, "codex")
        adaptation.scope_adaptations.append(
            adaptation.scope_adaptations[0].model_copy(update={"scope": "project"})
        )
        passport.adaptations[passport.adaptations.index(adaptation)] = seal_adaptation(
            adaptation.model_dump(mode="json")
        )
        document = passport.model_dump(mode="json")
        document.pop("revision_id")
        document["version"] = "1.1"
        stored = revisions.commit(connection, document, device_id=DEVICE)
        recorded_digest = cache.digest_of(stored.envelope.model_dump(mode="json"))
        versions.record(
            connection,
            stable_id=member[0],
            version="1.1",
            passport_digest=recorded_digest,
            revision_id=stored.revision_id,
            at=at,
        )
        ambiguous, _ = record_setup(
            connection, harness_id="codex", member=(member[0], "1.1", recorded_digest)
        )
        connection.commit()
        uncertain = read(ambiguous, exact)
        assert uncertain["candidate_context"]["unavailable_components"] == 1
        assert uncertain["context_delta"] is None
        assert (
            uncertain["candidate_context"]["components"][0]["reason"]
            == "adaptation_selection_required"
        )
        unavailable = read(ambiguous, exact, {**profile, "tokenizer_profile": exact})
        assert unavailable["token_cost"]["reason"] == "context_budget_unavailable"
        assert unavailable["token_cost"]["amount"] is None

        opaque_member = release_instruction(
            connection,
            harness_id="codex",
            payload=b"# Instruction\n\xff",
            managed_path="AGENTS.md",
        )
        opaque_setup, _ = record_setup(connection, harness_id="codex", member=opaque_member)
        connection.commit()
        opaque = read(opaque_setup, exact)
        assert opaque["candidate_context"]["components"][0]["reason"] == "content_is_not_utf8"

        project_id = new_id("project")
        other_project = new_id("project")
        if connection.execute("SELECT 1 FROM entity WHERE kind='device'").fetchone() is None:
            revisions.commit(
                connection,
                {
                    "schema_version": 1,
                    "kind": "device",
                    "stable_id": new_id("device"),
                    "owner_id": setup["owner_id"],
                    "created_at": at,
                    "visibility": "private",
                    "parent_revision_ids": [],
                    "facts": {},
                },
                device_id=DEVICE,
            )
        connection.execute(
            "INSERT INTO entity (stable_id,kind,created_at) VALUES (?,'project',?)",
            (project_id, at),
        )
        connection.execute(
            "INSERT INTO selected_version "
            "(project_id,harness_id,stable_id,version,state,selected_at) "
            "VALUES (?,'codex',?,'1.0','pending_install',?)",
            (project_id, target_setup, at),
        )
        connection.commit()

        def settle(
            action: str,
            setup_id: str,
            *,
            project: str = project_id,
            location: str = str(root / "report-target"),
            complete: bool = True,
        ) -> None:
            # Only the real operation journal is exercised; no target is written.
            plan = installation.propose(
                connection,
                action=action,
                author="account_fixture",
                target_id=installation.target_identity(project, "codex"),
                expected_target_digest="sha256:" + "0" * 64,
                provider_version="1.0.0",
                provider_target=location,
                effects=("fixture journal transition",),
                recovery_action="restore",
                idempotency_key=new_id("operation"),
                at=at,
                expires_at="2099-01-01T00:00:00.000Z",
                setup_stable_id=setup_id,
                setup_version="1.0",
            )
            if complete:
                installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=at)
                installation.begin(
                    connection,
                    plan.operation_id,
                    observed_target_digest="sha256:" + "0" * 64,
                    at=at,
                )
                installation.applied(connection, plan.operation_id, at=at)
                installation.verify(
                    connection,
                    plan.operation_id,
                    postconditions_met=True,
                    observed_target_digest="sha256:" + "1" * 64,
                    at=at,
                )

        def current(source: str, setup_id: str) -> None:
            report = read(target_setup, exact, project_id=project_id)
            assert report["baseline_source"] == source
            assert report["baseline_setup"]["stable_id"] == setup_id
            for version in ["1.0", "1.1"]:
                affected = radius(member[0], version)
                assert bool(affected["devices"]) == bool(affected["installed_targets"])

        current("selected", target_setup)
        settle("install", ambiguous)
        current("installed", ambiguous)
        settle("update", target_setup)
        settle("backup", ambiguous)
        settle("install", ambiguous, complete=False)
        current("installed", target_setup)
        settle("remove", target_setup)
        current("selected", target_setup)
        settle("install", ambiguous)
        settle("rollback", ambiguous)
        current("selected", target_setup)
        second_root = str(root / "second-report-target")
        settle("install", ambiguous, location=second_root)
        current("installed", ambiguous)
        settle("install", target_setup)
        current("selected", target_setup)
        settle("remove", ambiguous, location=second_root)
        current("installed", target_setup)
        settle("install", ambiguous, project=other_project)
        current("selected", target_setup)
        settle("remove", ambiguous, project=other_project, location="")
        current("selected", target_setup)

        scope = adaptation_for(passport, "codex").scope_adaptations[0]
        connection.execute(
            "UPDATE content SET byte_length=byte_length+1 WHERE digest=?",
            (scope.projection_artifact.digest,),
        )
        connection.commit()
        read(ambiguous, exact, expected=4)
        radius(member[0], "1.1", expected=4)
        connection.execute(
            "UPDATE content SET byte_length=length(bytes) WHERE digest=?",
            (scope.projection_artifact.digest,),
        )
        connection.commit()
    finally:
        connection.close()
