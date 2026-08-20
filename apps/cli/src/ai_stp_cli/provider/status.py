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


def _malformed(field: str) -> CliFailure:
    return CliFailure(
        "AI_STP_SCHEMA_UNSUPPORTED",
        "the provider status carries malformed authorization evidence",
        details={"field": field},
        next_actions=["provider conformance --harness <id> --executable <path> --json"],
    )
