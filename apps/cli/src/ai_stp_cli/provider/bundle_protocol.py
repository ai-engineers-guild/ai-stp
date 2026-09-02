"""Exact HarnessBundle and provider-plan binding for install lifecycle commands.

The provider process is a separate trust domain. A successful-looking JSON
object is therefore not evidence unless it echoes the exact immutable inputs
the consumer sent. These helpers own one fixed argv shape and verify the
corresponding response before any result may enter the operation journal.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue

_SHA256: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class Binding:
    """One literal bundle artifact and its independent logical identity."""

    path: Path
    bundle_format: str
    bundle_digest: str
    artifact_digest: str
    bundle_size: int

    def common_arguments(self) -> tuple[str, ...]:
        return (
            "--bundle",
            str(self.path),
            "--bundle-format",
            self.bundle_format,
            "--bundle-digest",
            self.bundle_digest,
            "--artifact-digest",
            self.artifact_digest,
            "--bundle-size",
            str(self.bundle_size),
        )

    def plan_arguments(self, expected_target_digest: str) -> tuple[str, ...]:
        return (*self.common_arguments(), "--expected-target-digest", expected_target_digest)

    def apply_arguments(
        self, expected_target_digest: str, provider_plan_digest: str
    ) -> tuple[str, ...]:
        return (
            *self.plan_arguments(expected_target_digest),
            "--plan-digest",
            provider_plan_digest,
        )


@dataclass(frozen=True)
class ProviderPlan:
    """The provider's immutable effect description bound to one target snapshot."""

    digest: str
    effects: tuple[str, ...]


def binding(
    path: Path,
    *,
    bundle_format: str,
    bundle_digest: str,
    artifact_digest: str,
    bundle_size: int,
) -> Binding:
    """Validate consumer-owned facts before constructing provider argv."""
    if path.is_symlink():
        raise _refused("the exact bundle artifact is not a regular absolute file")
    resolved = path.resolve()
    if not resolved.is_absolute() or not resolved.is_file():
        raise _refused("the exact bundle artifact is not a regular absolute file")
    if not bundle_format:
        raise _refused("the bundle format is missing")
    _digest(bundle_digest, "bundle_digest")
    _digest(artifact_digest, "artifact_digest")
    if bundle_size <= 0 or resolved.stat().st_size != bundle_size:
        raise _refused(
            "the cached bundle size differs from the immutable binding",
            expected=str(bundle_size),
            received=str(resolved.stat().st_size),
        )
    return Binding(
        path=resolved,
        bundle_format=bundle_format,
        bundle_digest=bundle_digest,
        artifact_digest=artifact_digest,
        bundle_size=bundle_size,
    )


def require_validated(answer: dict[str, JsonValue], expected: Binding) -> None:
    """Require an affirmative validation response for the exact sent bytes."""
    _echoes(answer, expected)
    if answer.get("valid") is not True:
        reason = answer.get("reason")
        raise _refused(
            "the provider did not validate the exact HarnessBundle",
            reason=(
                reason
                if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,64}", reason)
                else "unknown"
            ),
        )


def require_rejected(answer: dict[str, JsonValue], expected: Binding, expected_reason: str) -> None:
    """Require a typed refusal bound to the exact hostile artifact."""
    _echoes(answer, expected)
    if answer.get("rejected") is not True or answer.get("reason") != expected_reason:
        raise _refused(
            "the provider did not return the required HarnessBundle refusal",
            expected=expected_reason,
            received=str(answer.get("reason", "")),
        )


def require_plan(
    answer: dict[str, JsonValue], expected: Binding, expected_target_digest: str
) -> ProviderPlan:
    """Parse one side-effect-free provider plan and its exact input echoes."""
    _echoes(answer, expected)
    if answer.get("state") != "planned":
        raise _refused(
            "the provider did not return a planned bundle operation",
            received=str(answer.get("state", "")),
        )
    if answer.get("expected_target_digest") != expected_target_digest:
        raise _refused("the provider plan is bound to a different target snapshot")
    digest = str(answer.get("plan_digest", ""))
    _digest(digest, "plan_digest")
    raw_effects = answer.get("effects")
    if (
        not isinstance(raw_effects, list)
        or not raw_effects
        or not all(isinstance(item, str) and item for item in raw_effects)
    ):
        raise _refused("the provider plan does not enumerate its effects")
    return ProviderPlan(digest=digest, effects=cast(tuple[str, ...], tuple(raw_effects)))


def require_applied(
    answer: dict[str, JsonValue],
    expected: Binding,
    expected_target_digest: str,
    provider_plan_digest: str,
) -> None:
    """Verify apply answered about the same bytes, target and provider plan."""
    _echoes(answer, expected)
    if answer.get("expected_target_digest") != expected_target_digest:
        raise _refused("the provider applied response names a different target snapshot")
    if answer.get("plan_digest") != provider_plan_digest:
        raise _refused("the provider applied response names a different provider plan")


def _echoes(answer: dict[str, JsonValue], expected: Binding) -> None:
    wanted: tuple[tuple[str, JsonValue], ...] = (
        ("bundle_format", expected.bundle_format),
        ("bundle_digest", expected.bundle_digest),
        ("artifact_digest", expected.artifact_digest),
        ("bundle_size", expected.bundle_size),
    )
    mismatches = [name for name, value in wanted if answer.get(name) != value]
    if mismatches:
        raise _refused(
            "the provider response is not bound to the exact HarnessBundle",
            fields=", ".join(mismatches),
        )


def _digest(value: str, field: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise _refused("a provider binding digest is not canonical SHA-256", field=field)


def _refused(message: str, **details: str) -> CliFailure:
    return CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        message,
        details=details,
        next_actions=["provider conformance --harness <id> --executable <path> --json"],
    )
