"""An occupied immutable coordinate is not an idempotency receipt (SPEC-063)."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest
from tests.unit.test_cli_setup_recast import (
    CLAUDE_BYTES,
    CREATED,
    DEVICE,
    OWNER,
    _release_component,  # pyright: ignore[reportPrivateUsage]
)

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import component_materialize, component_passports
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import ComponentMaterializePlan, ComponentMaterializeResult
from ai_stp_foundation.ids import new_id
from ai_stp_passports import adaptation_for


def _source(connection: sqlite3.Connection, payload: bytes = CLAUDE_BYTES) -> str:
    return _release_component(
        connection,
        component_type="instruction",
        harness_id="claude-code",
        payload=payload,
        managed_path="CLAUDE.md",
    )[0]


def _plan(
    connection: sqlite3.Connection,
    stable_id: str,
    target: str,
    *,
    overlay_id: str | None = None,
) -> ComponentMaterializePlan:
    return component_materialize.plan(
        connection,
        stable_id=stable_id,
        version="1.0",
        source_harness="claude-code",
        target_harness=target,
        overlay_id=overlay_id or stable_id,
        created_at=CREATED,
        local_only=overlay_id is not None,
    )


def _apply(
    connection: sqlite3.Connection, preview: ComponentMaterializePlan
) -> ComponentMaterializeResult:
    return component_materialize.apply(
        connection,
        stable_id=preview.stable_id,
        version=preview.source_version,
        source_harness=preview.source_harness_id,
        target_harness=preview.target_harness_id,
        overlay_id=preview.overlay_id,
        created_at=preview.created_at,
        local_only=preview.local_only,
        expected_plan_digest=preview.plan_digest,
        device_id=DEVICE,
        owner_id=OWNER,
    )


def test_another_target_cannot_reuse_the_occupied_next_minor() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _source(connection)
        codex = _plan(connection, stable_id, "codex")
        pi = _plan(connection, stable_id, "pi")
        assert codex.complete and pi.complete
        assert codex.target_version == pi.target_version == "1.1"
        assert codex.plan_digest != pi.plan_digest
        applied = _apply(connection, codex)
        before = tuple(connection.iterdump())
        with pytest.raises(CliFailure) as raised:
            _apply(connection, pi)
        assert raised.value.code == "AI_STP_CONFLICT"
        assert tuple(connection.iterdump()) == before
        held = component_passports.version_passport(connection, stable_id, applied.version)
        adaptation_for(held, "codex")
        with pytest.raises(ValueError):
            adaptation_for(held, "pi")


@pytest.mark.parametrize("local_only", [False, True])
def test_only_the_identical_materialized_passport_is_an_idempotent_retry(local_only: bool) -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _source(connection)
        preview = _plan(
            connection,
            stable_id,
            "codex",
            overlay_id=new_id("component") if local_only else None,
        )
        first = _apply(connection, preview)
        before = tuple(connection.iterdump())
        again = _apply(connection, preview)
        assert first.created
        assert not again.created
        assert again.passport_digest == first.passport_digest
        assert tuple(connection.iterdump()) == before


def test_an_overlay_id_cannot_be_reused_for_another_source() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        first_id = _source(connection)
        second_id = _source(connection, b"# Different source\n")
        overlay_id = new_id("component")
        first = _plan(connection, first_id, "codex", overlay_id=overlay_id)
        second = _plan(connection, second_id, "codex", overlay_id=overlay_id)
        _apply(connection, first)
        before = tuple(connection.iterdump())
        with pytest.raises(CliFailure) as raised:
            _apply(connection, second)
        assert raised.value.code == "AI_STP_CONFLICT"
        assert tuple(connection.iterdump()) == before


def test_an_overlay_id_cannot_silently_reuse_another_target() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _source(connection)
        overlay_id = new_id("component")
        codex = _plan(connection, stable_id, "codex", overlay_id=overlay_id)
        pi = _plan(connection, stable_id, "pi", overlay_id=overlay_id)
        _apply(connection, codex)
        before = tuple(connection.iterdump())
        with pytest.raises(CliFailure) as raised:
            _apply(connection, pi)
        assert raised.value.code == "AI_STP_CONFLICT"
        assert tuple(connection.iterdump()) == before


def test_an_existing_source_id_is_not_a_new_private_overlay() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _source(connection)
        preview = _plan(connection, stable_id, "codex", overlay_id=stable_id)
        before = tuple(connection.iterdump())
        with pytest.raises(CliFailure) as raised:
            _apply(connection, preview)
        assert raised.value.code == "AI_STP_CONFLICT"
        assert tuple(connection.iterdump()) == before
