"""A program apply result carries no plan echo, and requiring one broke the lifecycle.

Measured against the released `0.0.48` providers rather than read off the
contract. A configuration apply answers `plan_digest`, `expected_target_digest`,
`target_identity_digest`, `backup_ref` and `setup_id`. A software apply answers
`state`, `operation`, `command`, `version`, `entry_point`, `executable`, `files`
and `recovered` — and neither echo.

`require_applied` required both unconditionally, so every `harness install`,
`harness update` and `harness remove` through `ai-stp` refused **after** the
provider had installed the program: the prefix held a working build and the
operation sat in `applied_unverified`.

No producer test could see this. The provider does exactly what its own suite
asserts, and the consumer's tests used answers written by hand to match the
consumer. It took driving the released binary through the real consumer path,
which is the whole argument for having that path in the evidence set.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import operation_v3

pytestmark = pytest.mark.cli


def _plan(operation: str) -> operation_v3.ProviderPlan:
    artifact: dict[str, Any] = {
        "operation": operation,
        "expected_target_digest": "sha256:" + "a" * 64,
    }
    return operation_v3.ProviderPlan(
        artifact=artifact,
        digest="sha256:" + "b" * 64,
        effects=("do the thing",),
    )


#: What the released providers actually answer for a software install. Copied
#: from a real run rather than composed to suit the assertion.
_RELEASED_SOFTWARE_ANSWER: dict[str, Any] = {
    "state": "verified",
    "operation": "software_install",
    "command": "codex",
    "version": "0.151.0",
    "entry_point": "bin/codex",
    "executable": "/prefix/bin/codex",
    "files": 8,
    "recovered": [],
}


def test_a_released_program_apply_result_is_accepted() -> None:
    """The falsification: this exact answer used to refuse a landed install."""
    state = operation_v3.require_applied(
        dict(_RELEASED_SOFTWARE_ANSWER), plan=_plan("software_install"), bundle=None
    )

    assert state == "verified"


@pytest.mark.parametrize("operation", ["software_install", "software_update", "software_remove"])
def test_every_program_operation_is_accepted_without_the_echo(operation: str) -> None:
    answer = {**_RELEASED_SOFTWARE_ANSWER, "operation": operation}

    assert operation_v3.require_applied(answer, plan=_plan(operation), bundle=None) == "verified"


def test_a_program_result_naming_another_plan_is_still_refused() -> None:
    """Tolerating absence is not tolerating disagreement."""
    answer = {**_RELEASED_SOFTWARE_ANSWER, "plan_digest": "sha256:" + "c" * 64}

    with pytest.raises(CliFailure, match="different v3 plan"):
        operation_v3.require_applied(answer, plan=_plan("software_install"), bundle=None)


def test_a_program_result_naming_another_snapshot_is_still_refused() -> None:
    answer = {**_RELEASED_SOFTWARE_ANSWER, "expected_target_digest": "sha256:" + "d" * 64}

    with pytest.raises(CliFailure, match="different target snapshot"):
        operation_v3.require_applied(answer, plan=_plan("software_install"), bundle=None)


def test_a_configuration_result_must_still_name_its_plan() -> None:
    """Nothing here relaxes the subject the consumer records provenance for."""
    with pytest.raises(CliFailure, match="does not name the plan it applied"):
        operation_v3.require_applied(
            {"state": "verified", "operation": "install"},
            plan=_plan("install"),
            bundle=None,
        )


def test_a_configuration_result_with_both_echoes_is_accepted() -> None:
    answer: dict[str, Any] = {
        "state": "verified",
        "operation": "install",
        "plan_digest": "sha256:" + "b" * 64,
        "expected_target_digest": "sha256:" + "a" * 64,
    }

    assert operation_v3.require_applied(answer, plan=_plan("install"), bundle=None) == "verified"
