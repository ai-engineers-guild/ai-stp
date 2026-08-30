"""Strict additive fields from provider ``status`` (`ADR-0052`)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue

AUTHORIZATION_KINDS: Final[frozenset[str]] = frozenset({"user_account", "external_service"})
AUTHORIZATION_STATES: Final[frozenset[str]] = frozenset({"pending", "ready"})


@dataclass(frozen=True)
class AuthorizationEvidence:
    """What the provider observes in the native target, without identity data."""

    kind: str
    state: str

    @property
    def ready(self) -> bool:
        return self.state == "ready"


def authorization(answer: Mapping[str, JsonValue]) -> AuthorizationEvidence | None:
    """Parse optional evidence; omission is compatible but never proves ready."""
    if "authorization" not in answer:
        return None
    raw = answer["authorization"]
    if not isinstance(raw, dict):
        raise _malformed("authorization")
    kind = raw.get("kind")
    state = raw.get("state")
    if not isinstance(kind, str) or kind not in AUTHORIZATION_KINDS:
        raise _malformed("authorization.kind")
    if not isinstance(state, str) or state not in AUTHORIZATION_STATES:
        raise _malformed("authorization.state")
    return AuthorizationEvidence(kind=kind, state=state)


#: What the provider stores when `hold --reason` is omitted. A placeholder, not
#: an answer: a hold placed without a reason and a hold placed before reasons
#: were carried at all publish these same words. Displayable as text, never
#: countable as a reason somebody gave.
BACKUP_HOLD_PLACEHOLDER: Final[str] = "no reason recorded"


@dataclass(frozen=True)
class BackupObservation:
    """One provider-owned copy as the provider reports it *now*.

    Distinct from `local.targets.Backup`, which is what our journal recorded
    when the copy was taken. The two answer different questions and are allowed
    to disagree — a ref we still list and the provider no longer reports is the
    interesting answer, not an inconsistency to smooth over.
    """

    backup_ref: str
    #: `None` means the provider never said, which is an older build rather than
    #: an unheld copy. Reading absence as `False` would report an unprotected
    #: baseline as checked against every release before the field existed.
    held: bool | None
    #: Free text typed by a person. Opaque: displayed, never branched on.
    hold_reason: str | None

    @property
    def reason_recorded(self) -> bool:
        """Whether a person actually gave a reason, as opposed to the placeholder."""
        return (
            self.held is True
            and self.hold_reason is not None
            and self.hold_reason != BACKUP_HOLD_PLACEHOLDER
        )


def backups(answer: Mapping[str, JsonValue]) -> tuple[BackupObservation, ...] | None:
    """Parse the optional copy list; `None` when the provider does not carry one.

    `None` and `()` are deliberately different answers. An empty tuple is the
    provider saying it owns no copies, which is authoritative. `None` is the
    provider not having been asked the question — a build older than the field —
    and nothing may be concluded from it.
    """
    if "backups" not in answer:
        return None
    raw = answer["backups"]
    if not isinstance(raw, list):
        raise _malformed_backup("backups")
    observed: list[BackupObservation] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise _malformed_backup(f"backups[{index}]")
        ref = item.get("backup_ref")
        if not isinstance(ref, str) or not ref:
            raise _malformed_backup(f"backups[{index}].backup_ref")
        held = item.get("held")
        if held is not None and not isinstance(held, bool):
            raise _malformed_backup(f"backups[{index}].held")
        reason = item.get("hold_reason")
        if reason is not None and not isinstance(reason, str):
            raise _malformed_backup(f"backups[{index}].hold_reason")
        observed.append(BackupObservation(backup_ref=ref, held=held, hold_reason=reason))
    return tuple(observed)


def _malformed_backup(field: str) -> CliFailure:
    return CliFailure(
        "AI_STP_SCHEMA_UNSUPPORTED",
        "the provider status carries a malformed copy list",
        details={"field": field},
        next_actions=["provider conformance --harness <id> --executable <path> --json"],
    )


def _malformed(field: str) -> CliFailure:
    return CliFailure(
        "AI_STP_SCHEMA_UNSUPPORTED",
        "the provider status carries malformed authorization evidence",
        details={"field": field},
        next_actions=["provider conformance --harness <id> --executable <path> --json"],
    )
