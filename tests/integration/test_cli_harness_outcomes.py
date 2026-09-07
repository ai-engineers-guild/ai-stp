"""Program outcomes settle the real operation journal without inventing effects."""

from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_stp_cli.commands.harness import _apply  # pyright: ignore[reportPrivateUsage]
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, journal
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_cli.provider import operation_v3, program_state, protocol_v3
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ({"state": "refused", "reason": "stale"}, "stale"),
        ({"state": "rolled_back"}, "rolled_back"),
        ({"state": "partial"}, "partial"),
        ({"state": "failed"}, "failed"),
        ({"state": "unknown"}, "partial"),
        ({"state": "verified", "plan_digest": "wrong"}, "partial"),
        (None, "partial"),
    ],
)
def test_program_apply_settles_the_provider_outcome(
    tmp_path: Path, reply: dict[str, JsonValue] | None, expected: str
) -> None:
    prefix = tmp_path / "prefix"
    target = tmp_path / "target"
    prefix.mkdir()
    target.mkdir()
    snapshot = digest_canonical("ai-stp:artifact:v1", {})
    artifact: dict[str, JsonValue] = {
        "operation": "software_remove",
        "expected_target_digest": snapshot,
    }
    effects = ("remove the exposed program",)
    plan = operation_v3.ProviderPlan(
        artifact=artifact,
        digest=digest_canonical(protocol_v3.PLAN_DOMAIN, artifact),
        effects=effects,
    )
    calls: list[str] = []

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        assert arguments[arguments.index("--prefix") + 1] == str(prefix)
        calls.append(command)
        if reply is None:
            raise CliFailure("AI_STP_PARTIAL_OPERATION", "provider response was lost")
        return reply

    with closing(open_registry(configured_path(), create=True)) as connection:
        held = installation.propose(
            connection,
            action="software_remove",
            author="test",
            target_id=str(prefix),
            expected_target_digest=snapshot,
            provider_version="test",
            effects=effects,
            recovery_action="install",
            idempotency_key="program-outcome",
            at=moment(),
            expires_at=(datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        )
        with pytest.raises(CliFailure) as error:
            _apply(
                connection,
                held,
                invoke=invoke,
                operation=protocol_v3.Operation.SOFTWARE_REMOVE,
                harness_id="claude-code",
                prefix=prefix,
                target=target,
                release_digest=snapshot,
                plan=artifact,
                plan_digest=plan.digest,
                bound=plan,
                effects=effects,
                artifacts=(),
                before=program_state.observe(prefix, entry_point="bin/claude"),
                entry_point="bin/claude",
            )
        assert error.value.code != "AI_STP_CONFLICT"
        recorded = journal.get(connection, held.operation_id)
        assert recorded is not None and recorded.state == expected
        assert calls == ["apply-operation"]
        assert not list(prefix.iterdir())
