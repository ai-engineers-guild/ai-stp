"""Official GitHub archived observations remain non-mutating evidence (SPEC-044)."""

import sqlite3
from contextlib import closing

import httpx
import pytest

from ai_stp_cli.commands import component as component_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, github_evidence, revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.registry import COMMANDS
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import versions as corpus_versions

AT = "2026-08-13T12:00:00.000Z"
LATER = "2026-08-13T13:00:00.000Z"
STALE = "2026-08-15T13:00:00.000Z"


def _materialize(*, source: bool = True) -> FirstPartyVersion:
    item = next(version for version in corpus_versions() if version.passport.kind == "component")
    document = item.passport.model_dump(mode="json")
    document.pop("revision_id")
    if not source:
        document["source"] = None
    with closing(open_registry(configured_path(), create=True)) as connection:
        stored = revisions.commit(connection, document, device_id="device_test")
        versions.record(
            connection,
            stable_id=item.passport.stable_id,
            version=item.passport.version,
            passport_digest=cache.digest_of(
                stored.envelope.model_dump(mode="json")  # pyright: ignore[reportArgumentType]
            ),
            revision_id=stored.revision_id,
            at=AT,
        )
    return item


def _response(
    *, archived: bool, repository_id: int = 42, name: str = "owner/repo"
) -> dict[str, object]:
    return {"id": repository_id, "full_name": name, "archived": archived, "private": False}


def _registry_snapshot(connection: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    names = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT IN ('github_repository_observation', 'sqlite_sequence') ORDER BY name"
        ).fetchall()
    ]
    return {
        name: [tuple(item) for item in connection.execute(f'SELECT * FROM "{name}"')]
        for name in names
    }


def test_machine_registry_exposes_one_refresh_and_two_offline_reads() -> None:
    commands = {
        command.name: command.descriptor
        for command in COMMANDS
        if command.name.startswith("component source evidence ")
    }
    assert set(commands) == {
        "component source evidence refresh",
        "component source evidence show",
        "component source evidence history",
    }
    assert commands["component source evidence refresh"].mutability == "apply"
    assert commands["component source evidence show"].mutability == "read"
    assert commands["component source evidence history"].mutability == "read"


def test_archived_unarchive_and_not_modified_are_append_only_with_one_request_each() -> None:
    item = _materialize()
    calls: list[httpx.Request] = []
    answers = iter(
        [
            httpx.Response(200, json=_response(archived=True), headers={"etag": '"one"'}),
            httpx.Response(
                200,
                json=_response(archived=False, name="new-owner/new-repo"),
                headers={"etag": '"two"'},
            ),
            httpx.Response(304),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return next(answers)

    transport = httpx.MockTransport(handler)
    with closing(open_registry(configured_path(), create=False)) as connection:
        before = _registry_snapshot(connection)
        archived = github_evidence.refresh(
            connection, item.passport.stable_id, item.passport.version, at=AT, transport=transport
        )
        active = github_evidence.refresh(
            connection,
            item.passport.stable_id,
            item.passport.version,
            at=LATER,
            transport=transport,
        )
        unchanged = github_evidence.refresh(
            connection,
            item.passport.stable_id,
            item.passport.version,
            at=STALE,
            transport=transport,
        )
        history = github_evidence.history(
            connection, item.passport.stable_id, item.passport.version, at=STALE
        )
        after = _registry_snapshot(connection)

    assert archived.repository_state == "archived"
    assert archived.proposal == "deprecated"
    assert active.repository_state == "active"
    assert active.repository_full_name == "new-owner/new-repo"
    assert unchanged.repository_state == "active"
    assert [entry.observation_id for entry in history.observations] == [1, 2, 3]
    assert [entry.archived for entry in history.observations] == [True, False, False]
    assert before == after
    assert len(calls) == 3
    assert calls[0].url.path.startswith("/repos/")
    assert calls[1].url.path == "/repositories/42"
    assert calls[2].headers["if-none-match"] == '"two"'
    assert all("authorization" not in request.headers for request in calls)


def test_archived_command_answer_warns_without_applying_the_proposal() -> None:
    item = _materialize()
    with closing(open_registry(configured_path(), create=False)) as connection:
        archived = github_evidence.refresh(
            connection,
            item.passport.stable_id,
            item.passport.version,
            at=AT,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=_response(archived=True))
            ),
        )
        archived_answer = component_commands.source_evidence_show(
            {"id": item.passport.stable_id, "version": item.passport.version}
        )
        active = github_evidence.refresh(
            connection,
            item.passport.stable_id,
            item.passport.version,
            at=LATER,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=_response(archived=False))
            ),
        )
        active_answer = component_commands.source_evidence_show(
            {"id": item.passport.stable_id, "version": item.passport.version}
        )
    assert archived.proposal == "deprecated"
    assert active.proposal == "none"
    assert archived_answer.payload.proposal == "deprecated"
    assert archived_answer.warnings == (
        "the source repository is archived; review a deprecated lifecycle transition",
    )
    assert active_answer.payload.proposal == "none"
    assert active_answer.warnings == ()


def test_offline_show_distinguishes_unavailable_fresh_and_stale() -> None:
    item = _materialize()
    with closing(open_registry(configured_path(), create=False)) as connection:
        missing = github_evidence.show(
            connection, item.passport.stable_id, item.passport.version, at=AT
        )
        github_evidence.refresh(
            connection,
            item.passport.stable_id,
            item.passport.version,
            at=AT,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=_response(archived=False))
            ),
        )
        fresh = github_evidence.show(
            connection, item.passport.stable_id, item.passport.version, at=LATER
        )
        stale = github_evidence.show(
            connection, item.passport.stable_id, item.passport.version, at=STALE
        )
    assert missing.freshness == "unavailable"
    assert fresh.freshness == "fresh"
    assert stale.freshness == "stale"


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_http_failures_do_not_replace_the_last_good_observation(status: int) -> None:
    item = _materialize()
    with closing(open_registry(configured_path(), create=False)) as connection:
        first = github_evidence.refresh(
            connection,
            item.passport.stable_id,
            item.passport.version,
            at=AT,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=_response(archived=True))
            ),
        )
        with pytest.raises(CliFailure) as raised:
            github_evidence.refresh(
                connection,
                item.passport.stable_id,
                item.passport.version,
                at=LATER,
                transport=httpx.MockTransport(lambda _request: httpx.Response(status)),
            )
        latest = github_evidence.show(
            connection, item.passport.stable_id, item.passport.version, at=LATER
        )
        count = connection.execute("SELECT COUNT(*) FROM github_repository_observation").fetchone()[
            0
        ]
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert latest.observation_id == first.observation_id
    assert latest.archived is True
    assert count == 1


def test_repository_identity_collision_is_refused_without_history_mutation() -> None:
    item = _materialize()
    answers = iter(
        [
            httpx.Response(200, json=_response(archived=False, repository_id=42)),
            httpx.Response(200, json=_response(archived=False, repository_id=99)),
        ]
    )
    transport = httpx.MockTransport(lambda _request: next(answers))
    with closing(open_registry(configured_path(), create=False)) as connection:
        github_evidence.refresh(
            connection, item.passport.stable_id, item.passport.version, at=AT, transport=transport
        )
        with pytest.raises(CliFailure) as raised:
            github_evidence.refresh(
                connection,
                item.passport.stable_id,
                item.passport.version,
                at=LATER,
                transport=transport,
            )
        count = connection.execute("SELECT COUNT(*) FROM github_repository_observation").fetchone()[
            0
        ]
    assert raised.value.code == "AI_STP_CONFLICT"
    assert count == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"id": "wrong"}),
        httpx.Response(
            200,
            json={"id": 42, "full_name": "owner/private", "archived": True, "private": True},
        ),
        httpx.Response(200, content=b"x", headers={"content-length": "1048577"}),
    ],
)
def test_malformed_private_and_oversized_answers_create_no_evidence(
    response: httpx.Response,
) -> None:
    item = _materialize()
    with closing(open_registry(configured_path(), create=False)) as connection:
        with pytest.raises(CliFailure) as raised:
            github_evidence.refresh(
                connection,
                item.passport.stable_id,
                item.passport.version,
                at=AT,
                transport=httpx.MockTransport(lambda _request: response),
            )
        count = connection.execute("SELECT COUNT(*) FROM github_repository_observation").fetchone()[
            0
        ]
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert count == 0


def test_transport_failure_creates_no_evidence() -> None:
    item = _materialize()

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with closing(open_registry(configured_path(), create=False)) as connection:
        with pytest.raises(CliFailure) as raised:
            github_evidence.refresh(
                connection,
                item.passport.stable_id,
                item.passport.version,
                at=AT,
                transport=httpx.MockTransport(fail),
            )
        count = connection.execute("SELECT COUNT(*) FROM github_repository_observation").fetchone()[
            0
        ]
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert count == 0


def test_missing_public_github_source_is_refused_before_http() -> None:
    item = _materialize(source=False)
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=_response(archived=False))

    with (
        closing(open_registry(configured_path(), create=False)) as connection,
        pytest.raises(CliFailure) as raised,
    ):
        github_evidence.refresh(
            connection,
            item.passport.stable_id,
            item.passport.version,
            at=AT,
            transport=httpx.MockTransport(handler),
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert called is False


def test_a_version_without_a_declared_source_is_refused_with_the_way_to_declare_one() -> None:
    """A draft that declares no source has no GitHub evidence.

    The refusal names the version and the command that declares a source.
    """
    from contextlib import closing

    from ai_stp_cli.local import cache, content, passports, revisions, versions
    from ai_stp_cli.local.database import configured_path, open_registry

    at = "2026-09-02T00:00:00.000Z"
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = "component_01J0000000000000000000000S"
        artifact = content.put(connection, b"# sourceless\n", at=at)
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
            (stable_id, at),
        )
        fact = {"origin": "observed", "confirmation": "none", "observed_at": at}
        stored = revisions.commit(
            connection,
            {
                "schema_version": 1,
                "kind": "component",
                "stable_id": stable_id,
                "owner_id": passports.owner().account_id,
                "created_at": at,
                "visibility": "private",
                "parent_revision_ids": [],
                "facts": {
                    "harness_id": {"value": "claude-code", **fact},
                    "component_type": {"value": "skill", **fact},
                    "content_digest": {"value": artifact.digest, **fact},
                },
            },
            device_id="device_test",
        )
        versions.record(
            connection,
            stable_id=stable_id,
            version="1.0",
            passport_digest=cache.digest_of(stored.envelope.model_dump(mode="json")),
            revision_id=stored.revision_id,
            at=at,
        )
        with pytest.raises(CliFailure) as raised:
            github_evidence.show(connection, stable_id, "1.0", at=at)

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.details == {"id": stable_id, "version": "1.0"}
    assert raised.value.next_actions == [f"component passport suggest --id {stable_id} --json"]
