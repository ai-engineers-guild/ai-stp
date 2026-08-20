"""Provider protocol v1, frozen (`#169`, `docs/contracts/provider-protocol.md`).

This module is the machine form of a contract that is otherwise prose. It
declares the twelve commands, the execution boundary, the state mapping and the
error semantics as data, so a conformance run compares an implementation against
one source rather than against somebody's reading of a document.

**Frozen means the version, not the file.** Adding a command, renaming a state
or widening the boundary is protocol v2 and needs its own decision. `VERSION`
below is what a provider reports and what `provider-info` is checked against; a
provider announcing a version this build does not know is refused rather than
read optimistically, because misreading a protocol is worse than not speaking it.

**Applied is not success.** `REQ-809` gives `applied_unverified` its own name on
both sides, and the mapping here keeps it: a provider that changed a target and
has not verified it has not succeeded, and calling that success is how a broken
install becomes invisible.

**The boundary is part of the protocol.** An argument array, no shell, an
absolute target, a filtered environment, a time limit and an output bound —
`SPEC-008` REQ-803 puts the lifecycle inside the provider, and these are the
terms on which `ai_stp` is willing to start one.
"""

from dataclasses import dataclass
from typing import Final

#: The protocol version this build speaks. A provider announcing anything else
#: is refused: reading a protocol you do not know is worse than declining it.
VERSION: Final[int] = 1

#: The twelve commands of `provider-protocol.md`, in the contract's own order.
#: Closed — a thirteenth is protocol v2.
COMMANDS: Final[tuple[str, ...]] = (
    "provider-info",
    "software-status",
    "software-plan",
    "software-install",
    "software-update",
    "software-remove",
    "validate-bundle",
    "plan-bundle",
    "apply-bundle",
    "status",
    "restore",
    "launch",
)

#: Commands that observe and must create no state. A read that wrote would make
#: "look before you decide" unsafe, which is the whole shape of the flow.
READ_COMMANDS: Final[frozenset[str]] = frozenset(
    {"provider-info", "software-status", "status", "validate-bundle", "plan-bundle"}
)

#: Commands that change the target. Each needs an exact plan hash, a lock and a
#: re-check of the target after the lock (`REQ-806`).
APPLY_COMMANDS: Final[frozenset[str]] = frozenset(
    {"software-install", "software-update", "software-remove", "apply-bundle", "restore"}
)

#: States a provider may report, and the durable operation state each maps to.
#: One-to-one and total: a provider result with no mapping would have to be
#: guessed at, and a guess about whether a target changed is the guess that
#: matters most.
STATE_MAP: Final[dict[str, str]] = {
    "planned": "planned",
    "applying": "applying",
    "applied_unverified": "applied_unverified",
    "verified": "verified",
    "partial": "partial",
    "failed": "failed",
    "stale": "stale",
    "rolled_back": "rolled_back",
}

#: Operation states with no provider source. `approved` is the user's decision
#: and `cancelled` is `ai_stp` stopping before an effect; a provider reporting
#: either would be claiming something it cannot know.
OPERATION_ONLY_STATES: Final[frozenset[str]] = frozenset({"approved", "cancelled"})

#: The only name for success (`REQ-809`).
SUCCESS_STATE: Final[str] = "verified"

#: Fields `provider-info` must answer with. Closed, because a conformance check
#: over an open set could only check what it happened to know about.
INFO_FIELDS: Final[tuple[str, ...]] = (
    "protocol_version",
    "harness_id",
    "provider_version",
    "supported_actions",
    "bundle_formats",
    "supported_os",
    "supported_arch",
    "limits",
)

#: Every reason a provider must reject a bundle (`REQ-804`). The compiler
#: refuses the same shapes before one is ever built; a provider that trusted the
#: compiler would trust a bundle it did not build.
BUNDLE_REJECTIONS: Final[frozenset[str]] = frozenset(
    {
        "unsupported_protocol_version",
        "path_escapes_target",
        "path_not_relative",
        "path_duplicate",
        "link_not_allowed",
        "special_file_not_allowed",
        "limit_exceeded",
        "unknown_native_surface",
        "digest_mismatch",
    }
)


@dataclass(frozen=True)
class Boundary:
    """How a provider process is started, and the terms it runs under.

    Values rather than advice. `SPEC-008` REQ-803 puts the whole lifecycle
    inside the provider, so these are the only things `ai_stp` controls about
    it — and each one exists because its absence has a name: a shell turns an
    argument into a command, an unfiltered environment hands over every secret
    in it, and no time limit means a hung provider hangs the caller.
    """

    #: Never a string. A string command has to be split by something, and that
    #: something would not be us.
    argument_array: bool = True
    shell: bool = False

    #: The target is named absolutely, so nothing depends on a working directory
    #: the provider might change.
    absolute_target: bool = True

    #: Exactly which executable, verified before starting it.
    exact_executable: bool = True

    #: Names allowed through, and nothing else. A provider needs a path and a
    #: home; it does not need whatever the caller's shell was carrying.
    environment_allowlist: tuple[str, ...] = ("PATH", "HOME")

    timeout_seconds: float = 120.0
    output_limit_bytes: int = 1024 * 1024


#: The boundary as frozen for v1.
BOUNDARY: Final[Boundary] = Boundary()


def operation_state(reported: str) -> str:
    """Map a provider state onto a durable operation state.

    Refuses anything unmapped instead of passing it through. An unknown state
    reaching the operation log would be recorded as though it meant something,
    and the one thing an operation log must not do is claim to know what
    happened when it does not.
    """
    if reported in OPERATION_ONLY_STATES:
        raise KeyError(f"{reported!r} belongs to the operation alone and has no provider source")
    return STATE_MAP[reported]


def speaks(version: int) -> bool:
    """Whether this build can talk to a provider announcing that version."""
    return version == VERSION
