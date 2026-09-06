"""Materialize a missing target adaptation from a pinned component version."""

from __future__ import annotations

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
from ai_stp_cli.local import component_materialize, component_passports, eligibility, lifecycle
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_foundation.ids import new_id
from ai_stp_passports import adaptation_for


def test_materialize_derives_a_codex_instruction_and_is_idempotent() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        overlay_id = member[0]
        first = component_materialize.plan(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness="codex",
            overlay_id=overlay_id,
            created_at=CREATED,
            local_only=False,
        )
        second = component_materialize.plan(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness="codex",
            overlay_id=overlay_id,
            created_at=CREATED,
            local_only=False,
        )
        assert first.plan_digest == second.plan_digest
        assert first.complete
        assert first.disposition == "derive"
        applied = component_materialize.apply(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness="codex",
            overlay_id=overlay_id,
            created_at=CREATED,
            local_only=False,
            expected_plan_digest=first.plan_digest,
            device_id=DEVICE,
            owner_id=OWNER,
        )
        assert applied.created
        assert applied.version == "1.1"
        again = component_materialize.apply(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness="codex",
            overlay_id=overlay_id,
            created_at=CREATED,
            local_only=False,
            expected_plan_digest=first.plan_digest,
            device_id=DEVICE,
            owner_id=OWNER,
        )
        assert not again.created
        assert again.passport_digest == applied.passport_digest
        derived = adaptation_for(
            component_passports.version_passport(connection, member[0], "1.1"),
            "codex",
        )
        assert derived.scope_adaptations[0].members[0].path == "AGENTS.md"


def test_a_stale_materialize_plan_is_refused() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        with pytest.raises(CliFailure) as raised:
            component_materialize.apply(
                connection,
                stable_id=member[0],
                version="1.0",
                source_harness="claude-code",
                target_harness="codex",
                overlay_id=member[0],
                created_at=CREATED,
                local_only=False,
                expected_plan_digest="sha256:" + "0" * 64,
                device_id=DEVICE,
                owner_id=OWNER,
            )
        assert raised.value.code == "AI_STP_PLAN_STALE"


def test_portability_forks_a_private_overlay_without_mutating_the_source() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        overlay_id = new_id("component")
        preview = component_materialize.plan(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness="codex",
            overlay_id=overlay_id,
            created_at=CREATED,
            local_only=True,
        )
        assert preview.complete
        applied = component_materialize.apply(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness="codex",
            overlay_id=overlay_id,
            created_at=CREATED,
            local_only=True,
            expected_plan_digest=preview.plan_digest,
            device_id=DEVICE,
            owner_id=OWNER,
        )
        assert applied.local_only
        assert applied.stable_id == overlay_id
        source = component_passports.version_passport(connection, member[0], "1.0")
        with pytest.raises(ValueError):
            adaptation_for(source, "codex")
        overlay = component_passports.version_passport(connection, overlay_id, "1.0")
        assert overlay.visibility == "private"
        assert lifecycle.version_is_overlay(connection, overlay_id, "1.0")
        adaptation_for(overlay, "codex")
        missing = eligibility.CandidateFacts(
            stable_id=member[0],
            revision_id="rev",
            version="1.0",
            adaptation_harnesses=frozenset({"claude-code"}),
            visibility="public",
            license_id="MIT",
            author_verified=True,
            component_verified=True,
            checks_current=True,
        )
        verdict = eligibility.assess(
            missing,
            eligibility.Target(
                harness_id="codex",
                os="linux",
                arch="x86_64",
                provider_harnesses=frozenset({"codex"}),
            ),
        )
        assert any(item.code == "adaptation_unavailable" for item in verdict.refusals)


def test_an_unsupported_surface_stays_blocked() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="setting",
            harness_id="claude-code",
            payload=b"{}\n",
            managed_path="settings.json",
        )
        preview = component_materialize.plan(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness="codex",
            overlay_id=member[0],
            created_at=CREATED,
            local_only=False,
        )
        assert not preview.complete
        assert preview.disposition == "blocked"


def test_materialize_all_missing_is_blocked_when_any_harness_cannot_derive() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        preview = component_materialize.plan(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness=(),
            overlay_id=member[0],
            created_at=CREATED,
            local_only=False,
            all_missing=True,
        )
        assert not preview.complete
        blocked = {
            item.target_harness_id for item in preview.targets if item.disposition == "blocked"
        }
        derived = {
            item.target_harness_id for item in preview.targets if item.disposition == "derive"
        }
        assert blocked == {"cursor", "antigravity"}
        assert derived == {"codex", "pi", "opencode", "grok-build"}


def test_materialize_named_subset_derives_every_requested_instruction() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=CLAUDE_BYTES,
            managed_path="CLAUDE.md",
        )
        requested = ("codex", "pi", "opencode", "grok-build")
        preview = component_materialize.plan(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness=requested,
            overlay_id=member[0],
            created_at=CREATED,
            local_only=False,
        )
        assert preview.complete
        assert preview.disposition == "derive"
        applied = component_materialize.apply(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness=requested,
            overlay_id=member[0],
            created_at=CREATED,
            local_only=False,
            expected_plan_digest=preview.plan_digest,
            device_id=DEVICE,
            owner_id=OWNER,
        )
        assert applied.created
        assert applied.version == "1.1"
        held = component_passports.version_passport(connection, member[0], "1.1")
        assert {item.harness_id for item in held.adaptations} == {
            "claude-code",
            *requested,
        }


def test_materialize_all_missing_stays_blocked_for_settings() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="setting",
            harness_id="claude-code",
            payload=b"{}\n",
            managed_path="settings.json",
        )
        preview = component_materialize.plan(
            connection,
            stable_id=member[0],
            version="1.0",
            source_harness="claude-code",
            target_harness=(),
            overlay_id=member[0],
            created_at=CREATED,
            local_only=False,
            all_missing=True,
        )
        assert not preview.complete
        assert preview.disposition == "blocked"
