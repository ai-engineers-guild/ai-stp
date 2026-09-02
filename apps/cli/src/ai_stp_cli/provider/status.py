"""Strict additive fields from provider ``status`` (`ADR-0052`)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from jsonschema import Draft202012Validator

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue

AUTHORIZATION_KINDS: Final[frozenset[str]] = frozenset({"user_account", "external_service"})
AUTHORIZATION_STATES: Final[frozenset[str]] = frozenset({"pending", "ready"})


def require_wire(answer: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Reject a protocol-v3 status that does not match the released closed schema."""
    from ai_stp_cli.provider import protocol_v3

    validator = Draft202012Validator(protocol_v3.STATUS_WIRE_SCHEMA)
    errors = sorted(
        validator.iter_errors(answer),  # pyright: ignore[reportUnknownMemberType]
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        path = ".".join(str(item) for item in first.absolute_path) or "$"
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the provider status does not match the released protocol-v3 schema",
            details={
                "field": path,
                "validator": str(first.validator),
            },
            # `toolchain install` used to be named here with a `--harness` flag
            # it does not take; a schema mismatch means the provider itself is
            # behind or foreign, and the way out is a released one.
            next_actions=[
                "provider fetch --harness <id> --json",
                "provider conformance --harness <id> --executable <path> --json",
            ],
        )
    return dict(answer)


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


@dataclass(frozen=True)
class ShadowedSurface:
    """A name the product reads that the provider does not own.

    `state: "managed"` and a clean `target_digest` are statements about the
    bytes the provider wrote. Neither is a statement about what the product
    obeys, and the two differ: an `opencode.jsonc` beside an owned
    `opencode.json` is the file the product keeps, and a product that globs
    `{skill,skills}` resolves one name from two spellings in an order that
    followed creation time rather than the spelling.

    So a target reported clean can be running a file the provider never wrote.
    Reported and never refused: which file should win belongs to whoever put it
    there, and refusing would decide it for them.
    """

    #: The name the product reads.
    name: str
    #: The owned surface it takes precedence over.
    over: str
    #: What the product does as a result, in the provider's words. Opaque:
    #: displayed, never branched on.
    effect: str


def shadowed(answer: Mapping[str, JsonValue]) -> tuple[ShadowedSurface, ...] | None:
    """Parse the optional shadow list; `None` when the provider does not carry one.

    `None` and `()` differ for the same reason they do for copies. An empty
    tuple is the provider saying nothing shadows what it owns. `None` is a build
    that was never asked, and an absent answer must not be rendered as a clean
    one — that is the whole failure this field exists to end.

    Malformed is a refusal rather than a silent drop, unlike the recovery list:
    that one describes what happened before an operation that has already
    landed, while this one describes the target a caller is about to act on.
    """
    if "shadowed_by" not in answer:
        return None
    raw = answer["shadowed_by"]
    if not isinstance(raw, list):
        raise _malformed_shadow("shadowed_by")
    observed: list[ShadowedSurface] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise _malformed_shadow(f"shadowed_by[{index}]")
        fields: dict[str, str] = {}
        for key in ("name", "over", "effect"):
            value = item.get(key)
            if not isinstance(value, str) or not value:
                raise _malformed_shadow(f"shadowed_by[{index}].{key}")
            fields[key] = value
        observed.append(ShadowedSurface(**fields))
    return tuple(observed)


def _malformed_shadow(field: str) -> CliFailure:
    return CliFailure(
        "AI_STP_SCHEMA_UNSUPPORTED",
        "the provider status carries a malformed shadow list",
        details={"field": field},
        next_actions=["provider conformance --harness <id> --executable <path> --json"],
    )


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
