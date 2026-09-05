"""Full-task authority is a third consent scope, not a covering grant that wins.

`ADR-0150` authorises the agent to use an unverified object without a fresh
grant per object or capability expansion. `ADR-0029` still forbids a config
wildcard. The machine model is scope `task` / target `full-auto`: revocable,
named, and beaten by a narrower exclusion. It never moves a candidate off
`experimental`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from typing import Any

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import consent, revisions, search
from ai_stp_cli.local.database import configured_path, open_registry

MOMENT = "2026-08-07T10:00:00.000Z"
LATER = "2026-08-07T11:00:00.000Z"
OWNER = "account_01J0000000000000000000000A"
STABLE = "component_01J00000000000000000000A06"
TASK = "task"
PROFILE = "full-auto"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _capabilities(**named: list[str]) -> dict[str, Any]:
    return {name: list(value) for name, value in named.items()}


def _grant(
    connection: sqlite3.Connection,
    *,
    suffix: str,
    scope: str,
    target: str,
    observed: tuple[str, ...] = (STABLE,),
    capabilities: dict[str, Any] | None = None,
    at: str = MOMENT,
) -> None:
    consent.grant(
        connection,
        consent_id=f"request_01J0000000000000000000{suffix}",
        scope=scope,
        target=target,
        fingerprint=consent.fingerprint_of(capabilities or {}),
        observed=observed,
        decided_by=OWNER,
        origin="test",
        at=at,
    )


def _ask(
    connection: sqlite3.Connection,
    *,
    version: str = "1.0",
    capabilities: dict[str, Any] | None = None,
) -> consent.Consultation:
    return consent.consulted(
        connection,
        stable_id=STABLE,
        owner_id=OWNER,
        version=version,
        capabilities=capabilities or {},
    )


@dataclass(frozen=True)
class Case:
    """One consulted outcome. The grants run first, then the revokes."""

    grants: tuple[tuple[str, str, tuple[str, ...]], ...]
    revokes: tuple[tuple[str, str], ...]
    version: str
    capabilities: dict[str, Any]
    covered: bool
    source: str
    reason: str


CASES = {
    "task_alone_covers": Case(
        grants=((TASK, PROFILE, ()),),
        revokes=(),
        version="1.0",
        capabilities=_capabilities(network_permissions=["api.example.test"]),
        covered=True,
        source=f"{TASK}:{PROFILE}",
        reason="full-task",
    ),
    "capability_growth_still_covered_under_task": Case(
        grants=(
            (consent.SCOPE_PUBLISHER, OWNER, (STABLE,)),
            (TASK, PROFILE, ()),
        ),
        revokes=(),
        version="1.0",
        capabilities=_capabilities(network_permissions=["collect.elsewhere.test"]),
        covered=True,
        source=f"{TASK}:{PROFILE}",
        reason="full-task",
    ),
    "capability_growth_refused_without_task": Case(
        grants=((consent.SCOPE_PUBLISHER, OWNER, (STABLE,)),),
        revokes=(),
        version="1.0",
        capabilities=_capabilities(network_permissions=["collect.elsewhere.test"]),
        covered=False,
        source=f"{consent.SCOPE_PUBLISHER}:{OWNER}",
        reason="more than when consent was given",
    ),
    "new_major_covered_under_task": Case(
        grants=(
            (consent.SCOPE_OBJECT_MAJOR, f"{STABLE}@1", (STABLE,)),
            (TASK, PROFILE, ()),
        ),
        revokes=(),
        version="2.0",
        capabilities={},
        covered=True,
        source=f"{TASK}:{PROFILE}",
        reason="full-task",
    ),
    "new_major_refused_without_task": Case(
        grants=((consent.SCOPE_OBJECT_MAJOR, f"{STABLE}@1", (STABLE,)),),
        revokes=(),
        version="2.0",
        capabilities={},
        covered=False,
        source="",
        reason="no durable consent",
    ),
    "revoked_object_major_beats_task": Case(
        grants=(
            (consent.SCOPE_OBJECT_MAJOR, f"{STABLE}@1", (STABLE,)),
            (TASK, PROFILE, ()),
        ),
        revokes=((consent.SCOPE_OBJECT_MAJOR, f"{STABLE}@1"),),
        version="1.0",
        capabilities={},
        covered=False,
        source=f"{consent.SCOPE_OBJECT_MAJOR}:{STABLE}@1",
        reason="withdrawn",
    ),
    "revoked_publisher_beats_task": Case(
        grants=(
            (consent.SCOPE_PUBLISHER, OWNER, (STABLE,)),
            (TASK, PROFILE, ()),
        ),
        revokes=((consent.SCOPE_PUBLISHER, OWNER),),
        version="1.0",
        capabilities={},
        covered=False,
        source=f"{consent.SCOPE_PUBLISHER}:{OWNER}",
        reason="withdrawn",
    ),
    "revoked_task_covers_nothing": Case(
        grants=((TASK, PROFILE, ()),),
        revokes=((TASK, PROFILE),),
        version="1.0",
        capabilities={},
        covered=False,
        source=f"{TASK}:{PROFILE}",
        reason="withdrawn",
    ),
    "object_major_grant_is_the_source_when_it_covers": Case(
        grants=(
            (consent.SCOPE_OBJECT_MAJOR, f"{STABLE}@1", (STABLE,)),
            (TASK, PROFILE, ()),
        ),
        revokes=(),
        version="1.0",
        capabilities={},
        covered=True,
        source=f"{consent.SCOPE_OBJECT_MAJOR}:{STABLE}@1",
        reason="object_major",
    ),
    "narrower_revoked_object_major_beats_publisher": Case(
        grants=(
            (consent.SCOPE_OBJECT_MAJOR, f"{STABLE}@1", (STABLE,)),
            (consent.SCOPE_PUBLISHER, OWNER, (STABLE,)),
        ),
        revokes=((consent.SCOPE_OBJECT_MAJOR, f"{STABLE}@1"),),
        version="1.0",
        capabilities={},
        covered=False,
        source=f"{consent.SCOPE_OBJECT_MAJOR}:{STABLE}@1",
        reason="withdrawn",
    ),
}


@pytest.mark.parametrize("name", tuple(CASES))
def test_consulted_authority_table(registry: sqlite3.Connection, name: str) -> None:
    case = CASES[name]
    for index, (scope, target, observed) in enumerate(case.grants):
        _grant(
            registry,
            suffix=f"{name[:6].upper()}{index}",
            scope=scope,
            target=target,
            observed=observed,
        )
    for scope, target in case.revokes:
        assert consent.revoke(registry, scope=scope, target=target, at=LATER)
    verdict = _ask(registry, version=case.version, capabilities=case.capabilities)
    assert verdict.covered is case.covered, verdict
    if case.source:
        assert verdict.source == case.source, verdict
    assert case.reason in verdict.reason, verdict


def test_task_is_a_closed_scope_and_not_a_wildcard() -> None:
    assert TASK in consent.SCOPES
    assert consent.SCOPE_PUBLISHER in consent.SCOPES
    assert consent.SCOPE_OBJECT_MAJOR in consent.SCOPES
    assert "" not in consent.SCOPES


def test_a_task_grant_refuses_any_target_other_than_the_authorized_profile(
    registry: sqlite3.Connection,
) -> None:
    with pytest.raises(CliFailure, match="task profile is not one this contract defines"):
        _grant(registry, suffix="WILD", scope=TASK, target="everything", observed=())


def test_consent_allow_task_does_not_need_a_registered_object(
    registry: sqlite3.Connection,
) -> None:
    from ai_stp_cli.commands import component as command

    granted = command.consent_allow({"scope": TASK, "target": PROFILE}).payload
    assert granted.scope == TASK
    assert granted.target == PROFILE
    assert granted.observed == []
    verdict = _ask(registry, capabilities=_capabilities(network_permissions=["api.example.test"]))
    assert verdict.covered is True
    assert verdict.source == f"{TASK}:{PROFILE}"


def test_a_task_covered_candidate_stays_experimental(
    registry: sqlite3.Connection,
) -> None:
    unproven = _register(registry, "A6")
    _grant(registry, suffix="LANE", scope=TASK, target=PROFILE, observed=())
    found = search.search(registry, (unproven,))
    assert [hit.lane for hit in found.experimental] == [search.LANE_EXPERIMENTAL]
    assert found.authoritative == ()
    assert TASK in found.experimental[0].reason
    assert "authoritative" not in found.experimental[0].reason


def _register(connection: sqlite3.Connection, suffix: str) -> search.Candidate:
    stable_id = f"component_01J000000000000000000000{suffix}"
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, MOMENT),
    )
    document: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": OWNER,
        "version": "1.0",
        "created_at": MOMENT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            "name": {
                "value": "unproven",
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            }
        },
    }
    stored = revisions.commit(connection, document, device_id="device_test")  # pyright: ignore[reportArgumentType]
    return search.Candidate(
        stable_id=stable_id,
        revision_id=stored.revision_id,
        fields={"name": "unproven"},
        owner_id=OWNER,
        version="1.0",
    )
