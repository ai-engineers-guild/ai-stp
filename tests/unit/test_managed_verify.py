"""`corporate assignment verify`: managed content vs authorized records.

The verdict must hold under every evidence gap the issue names: drift,
missing or extra managed content, a later authorized installation, revoked
or outdated assignments, an unreachable corporate layer, and a target that
was never managed at all. Every path stays read-only.
"""

import hashlib
import io
import json
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.application import managed_verify
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.corporate import (
    CorporateAssignmentPlan,
    CorporateAssignmentPlanRequest,
)
from ai_stp_contracts.machine_help import ManagedVerification

PROJECT = "project_test"
HARNESS = "claude-code"
PAIR = f"{PROJECT}:{HARNESS}"
SETUP_ID = "setup_01J0000000000000000000000A"
ORGANIZATION = "organization_01J0000000000000000000000B"
ACCOUNT = "account_01J0000000000000000000000C"
MOMENT = "2026-09-20T10:00:00.000Z"
TARGET_DIGEST = "sha256:" + "0" * 64
ENDPOINT = Endpoint(base_url="http://corporate.test")


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _bundle_bytes(
    files: dict[str, bytes],
    *,
    components: list[dict[str, object]] | None = None,
    setup_version: str = "1.0",
) -> bytes:
    records = [
        {"path": name, "digest": _digest(payload), "byte_length": len(payload), "mode": 420}
        for name, payload in sorted(files.items())
    ]
    document: dict[str, object] = {
        "managed_paths": sorted(files),
        "files": records,
        "conversion_report": {"entries": [{"native_surface": "skills"}]},
        "setup": {
            "stable_id": SETUP_ID,
            "version": setup_version,
            "passport_digest": "sha256:" + "a" * 64,
        },
    }
    if components is not None:
        document["component_adaptations"] = components
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bundle.json", json.dumps(document))
        for name, payload in files.items():
            archive.writestr(f"files/{name}", payload)
    return buffer.getvalue()


def _verified_installation(
    connection: sqlite3.Connection,
    *,
    target: Path,
    bundle: bytes,
    version: str = "1.0",
    at: str = MOMENT,
    key: str = "verify-fixture",
    digest: str = TARGET_DIGEST,
    pair: str = PAIR,
) -> installation.Plan:
    artifact_digest = _digest(bundle)
    cache.store_raw_artifact_bytes(bundle, artifact_digest)
    plan = installation.propose(
        connection,
        action="install",
        author=ACCOUNT,
        target_id=pair,
        expected_target_digest=TARGET_DIGEST,
        provider_version="1.0.0",
        effects=("materialize managed paths",),
        recovery_action="restore",
        idempotency_key=key,
        at=at,
        expires_at="2099-01-01T00:00:00.000Z",
        provider_target=str(target),
        bundle_artifact_digest=artifact_digest,
        setup_stable_id=SETUP_ID,
        setup_version=version,
    )
    installation.approve(connection, plan.operation_id, plan_digest=plan.digest, at=at)
    installation.begin(connection, plan.operation_id, observed_target_digest=TARGET_DIGEST, at=at)
    installation.applied(connection, plan.operation_id, at=at)
    installation.verify(
        connection,
        plan.operation_id,
        postconditions_met=True,
        observed_target_digest=digest,
        at=at,
    )
    return plan


def _plan_result(
    *items: tuple[str, str, str, str],
) -> CorporateAssignmentPlan:
    """(object_kind, stable_id, state, outcome) entries, action derived."""
    return CorporateAssignmentPlan.model_validate(
        {
            "schema_version": 1,
            "organization_id": ORGANIZATION,
            "account_id": ACCOUNT,
            "harness": HARNESS,
            "items": [
                {
                    "object_kind": kind,
                    "stable_id": stable_id,
                    "state": state,
                    "outcome": outcome,
                    "action": "remove" if outcome in {"revoked", "unassigned"} else "none",
                }
                for kind, stable_id, state, outcome in items
            ],
            "total": len(items),
        }
    )


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as opened:
        yield opened


@pytest.fixture
def corporate_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    """The assignment layer, answered locally; `response` can be replaced or
    set to a CliFailure to simulate an unreachable layer."""
    requests: list[tuple[str, CorporateAssignmentPlanRequest]] = []
    box: dict[str, object] = {
        "response": _plan_result(("setup", SETUP_ID, "assigned", "installed")),
        "requests": requests,
    }

    def answer(
        _endpoint: Endpoint,
        _token: str,
        organization: str,
        request: CorporateAssignmentPlanRequest,
    ) -> CorporateAssignmentPlan:
        requests.append((organization, request))
        response = box["response"]
        if isinstance(response, CliFailure):
            raise response
        assert isinstance(response, CorporateAssignmentPlan)
        return response

    monkeypatch.setattr("ai_stp_cli.application.managed_verify.corporate.assignment_plan", answer)
    return box


def _parameters(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "organization": ORGANIZATION,
        "harness": HARNESS,
        "local-project": PROJECT,
    }
    base.update(overrides)
    return base


def _verify(parameters: dict[str, object]) -> ManagedVerification:
    return managed_verify.verify_managed(
        parameters,
        endpoint_url=ENDPOINT,
        access_token="bearer",
        account_id=ACCOUNT,
    ).payload


def test_a_clean_verified_target_passes(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )

    result = _verify(_parameters())

    assert result.status == "pass"
    assert result.corporate == "evaluated"
    assert result.project_id == PROJECT
    assert result.organization_id == ORGANIZATION
    assert result.account_id == ACCOUNT
    assert result.verified_target_digest == TARGET_DIGEST
    setup = next(item for item in result.items if item.subject == "setup")
    assert (setup.stable_id, setup.version, setup.classification) == (
        SETUP_ID,
        "1.0",
        "unchanged",
    )
    assert setup.outcome == "installed"


def test_a_modified_managed_file_fails_as_locally_modified(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes(
            {"skills/review/SKILL.md": b"expected\n"},
            components=[
                {
                    "stable_id": "component_01J0000000000000000000000D",
                    "version": "1.0",
                    "passport_digest": "sha256:" + "b" * 64,
                    "provider_component_kind": "skill",
                    "member_paths": ["skills/review/SKILL.md"],
                }
            ],
        ),
    )
    managed.write_bytes(b"edited by hand\n")

    result = _verify(_parameters())

    assert result.status == "fail"
    component = next(item for item in result.items if item.subject == "component")
    assert component.classification == "locally_modified"
    path = next(item for item in result.items if item.subject == "path")
    assert (path.path, path.change, path.classification) == (
        "skills/review/SKILL.md",
        "modified",
        "locally_modified",
    )
    assert path.observed_digest.startswith("sha256:")


def test_a_missing_managed_file_fails_as_missing(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    managed.unlink()

    result = _verify(_parameters())

    assert result.status == "fail"
    path = next(item for item in result.items if item.subject == "path")
    assert (path.change, path.classification) == ("deleted", "missing")


def test_extra_managed_content_fails_as_extra(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    (target / "skills" / "smuggled.md").write_bytes(b"not authorized\n")

    result = _verify(_parameters())

    assert result.status == "fail"
    extra = next(
        item for item in result.items if item.subject == "path" and item.classification == "extra"
    )
    assert (extra.path, extra.change) == ("skills/smuggled.md", "added")


def test_a_later_authorized_installation_is_expected_change_not_tampering(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"older\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"older\n"}),
        version="1.0",
        at="2026-09-19T10:00:00.000Z",
        key="first",
    )
    # A second authorized operation on the same provider target — another
    # pair's this time — replaces the first: the caller's own record is older
    # than what is actually installed, and that must read as authorized change
    # rather than as drift.
    managed.write_bytes(b"newer\n")
    second = _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"newer\n"}, setup_version="1.1"),
        version="1.1",
        at=MOMENT,
        key="second",
        pair="other_project:claude-code",
    )

    result = _verify(_parameters())

    assert result.status == "pass"
    assert result.operation_id == second.operation_id
    setup = next(item for item in result.items if item.subject == "setup")
    assert setup.version == "1.1"
    assert setup.classification == "expected_change"
    assert second.operation_id in (setup.diagnostic or "")


def test_revoked_assignments_report_revoked(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    corporate_plan["response"] = _plan_result(("setup", SETUP_ID, "revoked", "revoked"))

    result = _verify(_parameters())

    assert result.status == "revoked"
    setup = next(item for item in result.items if item.subject == "setup")
    assert setup.outcome == "revoked"


def test_an_unassigned_setup_reports_not_enrolled(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    corporate_plan["response"] = _plan_result(("setup", SETUP_ID, "unassigned", "unassigned"))

    result = _verify(_parameters())

    assert result.status == "not_enrolled"


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("outdated", "outdated"),
        ("conflicting", "outdated"),
        ("unsupported", "unsupported"),
        ("missing", "outdated"),
    ],
)
def test_policy_states_map_to_verdicts(
    outcome: str,
    expected: str,
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    corporate_plan["response"] = _plan_result(("setup", SETUP_ID, "assigned", outcome))

    result = _verify(_parameters())

    assert result.status == expected


def test_a_missing_assigned_component_names_the_install_plan(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    """The verdict names the one command that closes the gap (#358).

    `install plan --setup <assigned> --component <assigned>` installs the
    exact assigned set onto the named baseline — the continuation carries
    executable arguments, not a command the caller must reassemble.
    """
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    corporate_plan["response"] = CorporateAssignmentPlan.model_validate(
        {
            "schema_version": 1,
            "organization_id": ORGANIZATION,
            "account_id": ACCOUNT,
            "harness": HARNESS,
            "items": [
                {
                    "object_kind": "setup",
                    "stable_id": SETUP_ID,
                    "state": "assigned",
                    "outcome": "installed",
                    "action": "none",
                    "version": "1.0",
                },
                {
                    "object_kind": "component",
                    "stable_id": "component_extra",
                    "state": "assigned",
                    "outcome": "missing",
                    "action": "install",
                    "version": "2.0",
                },
            ],
            "total": 2,
        }
    )

    answer = managed_verify.verify_managed(
        _parameters(),
        endpoint_url=ENDPOINT,
        access_token="bearer",
        account_id=ACCOUNT,
    )

    assert answer.payload.status == "outdated"
    assert len(answer.continuations) == 1
    remediation = answer.continuations[0]
    assert remediation.path == ["install", "plan"]
    assert remediation.arguments["setup"] == f"{SETUP_ID}@1.0"
    assert remediation.arguments["component"] == ["component_extra@2.0"]
    assert remediation.arguments["project"] == PROJECT


def test_a_components_only_gap_names_no_install_plan(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    """Standalone components bind to an exact setup graph — without an
    assigned setup line there is no honest command to print."""
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    corporate_plan["response"] = CorporateAssignmentPlan.model_validate(
        {
            "schema_version": 1,
            "organization_id": ORGANIZATION,
            "account_id": ACCOUNT,
            "harness": HARNESS,
            "items": [
                {
                    "object_kind": "component",
                    "stable_id": "component_extra",
                    "state": "assigned",
                    "outcome": "missing",
                    "action": "install",
                    "version": "2.0",
                },
            ],
            "total": 1,
        }
    )

    answer = managed_verify.verify_managed(
        _parameters(),
        endpoint_url=ENDPOINT,
        access_token="bearer",
        account_id=ACCOUNT,
    )

    # A plan silent on the materialized setup is not a verdict to pass on.
    assert answer.payload.status == "unverifiable"
    assert answer.continuations == ()


def test_a_pair_with_no_verified_installation_is_not_enrolled(
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    result = _verify(_parameters())

    assert result.status == "not_enrolled"
    assert result.items == []
    assert box_requests(corporate_plan) == []


def test_no_registry_at_all_is_not_enrolled(
    corporate_plan: dict[str, object],
) -> None:
    assert not configured_path().exists()
    result = _verify(_parameters())
    assert result.status == "not_enrolled"
    assert box_requests(corporate_plan) == []


def test_offline_verification_reports_the_local_verdict_as_unverifiable(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )

    result = _verify(_parameters(offline=True))

    assert result.status == "unverifiable"
    assert result.corporate == "offline"
    assert box_requests(corporate_plan) == []


def test_offline_still_fails_on_proven_drift(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    managed.write_bytes(b"tampered offline\n")

    result = _verify(_parameters(offline=True))

    assert result.status == "fail"
    assert result.corporate == "offline"
    assert box_requests(corporate_plan) == []


def test_an_unreachable_corporate_layer_is_unverifiable_not_clean(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    corporate_plan["response"] = CliFailure("AI_STP_UNAVAILABLE", "offline")

    result = _verify(_parameters())

    assert result.status == "unverifiable"
    assert result.corporate == "unavailable"
    assert any("could not be reached" in line for line in result.diagnostics)


def test_a_missing_bundle_archive_is_unverifiable(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )

    def missing_artifact(_digest: str) -> Path | None:
        return None

    monkeypatch.setattr(
        "ai_stp_cli.application.managed_verify.cache.stored_raw_artifact",
        missing_artifact,
    )

    result = _verify(_parameters())

    assert result.status == "unverifiable"
    setup = next(item for item in result.items if item.subject == "setup")
    assert setup.classification == "unverifiable"


def test_a_changed_provider_target_digest_fails(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    (target / "skills" / "review").mkdir(parents=True)
    (target / "skills" / "review" / "SKILL.md").write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )

    def moved_target(*_args: object, **_kwargs: object) -> tuple[str, None, tuple[()]]:
        return "sha256:" + "f" * 64, None, ()

    monkeypatch.setattr(
        "ai_stp_cli.application.install._observe_target",
        moved_target,
    )

    result = _verify(_parameters())

    assert result.status == "fail"
    assert result.observed_target_digest == "sha256:" + "f" * 64
    assert any("provider target digest" in line for line in result.diagnostics)


def test_verification_never_writes_to_the_target_or_the_log(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    operations = connection.execute("SELECT COUNT(*) FROM operation").fetchone()[0]
    events = connection.execute("SELECT COUNT(*) FROM operation_event").fetchone()[0]

    result = _verify(_parameters())

    assert result.status == "pass"
    assert managed.read_bytes() == b"expected\n"
    assert connection.execute("SELECT COUNT(*) FROM operation").fetchone()[0] == operations
    assert connection.execute("SELECT COUNT(*) FROM operation_event").fetchone()[0] == events


def test_the_report_carries_no_local_paths_or_file_content(
    tmp_path: Path,
    connection: sqlite3.Connection,
    corporate_plan: dict[str, object],
) -> None:
    target = tmp_path / "target"
    managed = target / "skills" / "review" / "SKILL.md"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"expected\n")
    _verified_installation(
        connection,
        target=target,
        bundle=_bundle_bytes({"skills/review/SKILL.md": b"expected\n"}),
    )
    managed.write_bytes(b"secret token value\n")

    result = _verify(_parameters())

    assert result.status == "fail"
    rendered = json.dumps(result.model_dump(mode="json"))
    assert str(tmp_path) not in rendered
    assert "secret token value" not in rendered
    assert "expected\\n" not in rendered


def box_requests(box: dict[str, object]) -> list[object]:
    return cast(list[object], box["requests"])
