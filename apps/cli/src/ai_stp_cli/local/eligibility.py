"""Mechanical constraints, run before an agent ever sees a candidate (`#163`).

`SPEC-006` REQ-601 puts this stage *before* selection, and that ordering is the
whole security property: an agent cannot return a reference it was never given,
so a candidate excluded here cannot come back through free text. Nothing in this
module consults a model, a network or a clock — the same facts decide the same
way on every machine, which is what makes REQ-607 reachable at all.

**Two axes, never merged.** `admissible` answers "may this be installed"; the
trust lane does not soften it, because `validation-policy.md` is explicit that a
lane changes what reaches the answer and not the set of checks an installation
must pass. `auto_selectable` answers "may this be chosen without being asked",
and `experimental` never may — consent opens a separate section of the answer,
not an automatic install (REQ-603). One boolean covering both would have let a
consented unverified object be picked silently, which is exactly the failure
`ADR-0016` exists to prevent.

**Two pairs of reasons are deliberately not one reason each.** An unknown
capability is a wrong passport the author fixes; a missing one is a mismatch
with this target the user fixes. An unreadable harness version is a silent
`--version`; an unsupported one is a version that was read and did not fit.
Collapsing either pair would send somebody to fix the wrong thing.

**What is not a refusal.** A missing mandatory environment variable is an
advisory: `SPEC-001` REQ-111 and `SPEC-008` REQ-816 both allow the install and
leave readiness at `needs_configuration`. Refusing here would be the easy
mistake and would contradict two requirements at once, so the notes are a
separate list rather than a weaker kind of refusal.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from ai_stp_cli.local.composition import native_surface
from ai_stp_cli.local.search import LANE_EXPERIMENTAL, lane_of

#: The six families of `REQ-601`, in the order that requirement names them.
#: Fixed, because the order of the families is the order refusals come back in
#: and REQ-607 wants one input to produce one answer.
FAMILY_COMPATIBILITY: Final[str] = "compatibility"
FAMILY_ACCESS: Final[str] = "access"
FAMILY_TRUST: Final[str] = "trust"
FAMILY_LICENSE: Final[str] = "license"
FAMILY_ENTITLEMENT: Final[str] = "entitlement"
FAMILY_PROVIDER: Final[str] = "provider"
FAMILIES: Final[tuple[str, ...]] = (
    FAMILY_COMPATIBILITY,
    FAMILY_ACCESS,
    FAMILY_TRUST,
    FAMILY_LICENSE,
    FAMILY_ENTITLEMENT,
    FAMILY_PROVIDER,
)

#: Every refusal this engine can produce, and the family it belongs to. Closed
#: by `eligibility-constraints.md`: a code invented in passing would be a reason
#: no test names and no caller can branch on.
REFUSALS: Final[dict[str, str]] = {
    "harness_mismatch": FAMILY_COMPATIBILITY,
    "adaptation_unavailable": FAMILY_COMPATIBILITY,
    "harness_version_unsupported": FAMILY_COMPATIBILITY,
    "harness_version_unknown": FAMILY_COMPATIBILITY,
    "os_unsupported": FAMILY_COMPATIBILITY,
    "arch_unsupported": FAMILY_COMPATIBILITY,
    "capability_malformed": FAMILY_COMPATIBILITY,
    "capability_unknown": FAMILY_COMPATIBILITY,
    "capability_missing": FAMILY_COMPATIBILITY,
    "object_not_registrable": FAMILY_ACCESS,
    "object_blocked": FAMILY_ACCESS,
    "grant_missing": FAMILY_ACCESS,
    "evidence_stale": FAMILY_TRUST,
    "unverified_without_consent": FAMILY_TRUST,
    "license_undeclared": FAMILY_LICENSE,
    "redistribution_forbidden": FAMILY_LICENSE,
    "entitlement_not_granted": FAMILY_ENTITLEMENT,
    "provider_unavailable": FAMILY_PROVIDER,
    "provider_platform_unsupported": FAMILY_PROVIDER,
    "provider_surface_unavailable": FAMILY_PROVIDER,
}

#: Advisories. Named in their own registry so that turning one into a refusal is
#: a visible edit here rather than a quiet change of behaviour somewhere else.
NOTE_REQUIRED_ENV_MISSING: Final[str] = "required_env_missing"
NOTE_AUTHORIZATION_REQUIRED: Final[str] = "authorization_required"
NOTE_CREDENTIALS_REQUIRED: Final[str] = "credentials_required"
NOTES: Final[frozenset[str]] = frozenset(
    {NOTE_REQUIRED_ENV_MISSING, NOTE_AUTHORIZATION_REQUIRED, NOTE_CREDENTIALS_REQUIRED}
)

#: The closed vocabulary of `capability-vocabulary.md`. Each entry is decided by
#: an observation this CLI already makes; an entry nobody can evaluate would be
#: a refusal nobody can clear, so the list grows with the observation and not
#: ahead of it.
CAPABILITIES: Final[frozenset[str]] = frozenset(
    {
        "project.language.python",
        "project.language.typescript",
        "project.language.javascript",
        "project.language.rust",
        "project.language.go",
        "project.language.dart",
        "project.vcs.git",
        "project.surface.agents_md",
        "project.surface.claude_md",
        "project.surface.skill_md",
        "project.surface.mcp_json",
        "toolchain.ruff",
    }
)

#: Versioned apart from the passport schema, exactly as the tag dictionary is:
#: adding an entry is compatible and must not force a schema bump.
CAPABILITY_VOCABULARY_VERSION: Final[str] = "1.0"

#: Which indexed file name proves which surface capability. A table rather than
#: a rule over names, so a file that merely looks like a surface cannot become
#: one by being named similarly.
SURFACE_CAPABILITIES: Final[dict[str, str]] = {
    "AGENTS.md": "project.surface.agents_md",
    "CLAUDE.md": "project.surface.claude_md",
    "SKILL.md": "project.surface.skill_md",
    ".mcp.json": "project.surface.mcp_json",
}

#: A version inside whatever a harness printed. At least one dot is required,
#: which is what separates a version from a year or a build number appearing in
#: the same line: `2024` is not a version and `0.146.0` is.
_NUMERIC: Final[re.Pattern[str]] = re.compile(r"v?(\d+(?:\.\d+)+)")

#: Bounds from the contract's normalisation rules.
CAPABILITY_MAX_LENGTH: Final[int] = 64
CAPABILITY_MIN_SEGMENTS: Final[int] = 2
CAPABILITY_MAX_SEGMENTS: Final[int] = 4


@dataclass(frozen=True)
class Target:
    """What a candidate has to fit: this harness, this machine, this project.

    Assembled by the caller from the device, project and harness facts as
    REQ-621 requires. Held as plain values so the engine stays decidable without
    touching a database, a passport file or the network.
    """

    harness_id: str
    os: str
    arch: str

    #: The version the harness reported, or empty when it reported none. Empty
    #: is a real state (`REQ-1415` has `unknown_version`) and is not the same as
    #: "any version".
    harness_version: str = ""

    #: What this project and machine can offer, already normalised.
    capabilities: frozenset[str] = frozenset()

    #: Permissions the user allows a candidate to require. Opaque strings
    #: compared exactly: there is no declared entitlement vocabulary yet, and
    #: inventing one here would create a second undeclared dictionary.
    entitlements: frozenset[str] = frozenset()

    #: Environment variable *names* present. Never their values — `REQ-1108`
    #: keeps values out of every path an agent can reach.
    env_present: frozenset[str] = frozenset()

    #: Who is composing. Their own objects need no grant and no licence.
    owner_id: str = ""

    #: Grants held, spelled `stable_id:major`, matching the target of a right in
    #: `access-grants-and-forks.md`: one object and one major line.
    grants: frozenset[str] = frozenset()

    #: Harness identifiers a provider covers. An identifier outside this set —
    #: `undefined` most of all — has nothing that could write the target's final
    #: state, and `ADR-0012` gives that write to the provider alone.
    provider_harnesses: frozenset[str] = frozenset()

    #: The `os/arch` pairs that provider supports, when a limit is known. Empty
    #: declares no known limit rather than no supported platform: a limit
    #: nobody has stated is not a limit, and treating it as one would refuse
    #: every candidate over a fact that was never established.
    provider_platforms: frozenset[str] = frozenset()

    #: Whether the composed result is meant to be redistributed. Off by default:
    #: a private setup for one machine is the ordinary case, and assuming
    #: redistribution would refuse candidates over a right nobody wanted.
    for_redistribution: bool = False


@dataclass(frozen=True)
class CandidateFacts:
    """The mechanical half of one candidate's passport.

    Only what a constraint reads. Nothing here carries a secret, an environment
    value or an artifact's bytes: this object is built to be handed to an agent
    together with the verdict.
    """

    stable_id: str
    revision_id: str

    #: `X.Y`. The major line is what a grant addresses, so it is read from here
    #: rather than passed alongside and risked disagreeing.
    version: str = ""

    harness_id: str = ""

    #: Harnesses named by immutable adaptations (`ADR-0143` / `REQ-631`). When
    #: this is non-empty it is the compatibility set; `harness_id` is ignored
    #: for that decision because the first supported passport form has no
    #: component-level harness field. Empty keeps the historical single-harness
    #: and portable readings of `harness_id`.
    adaptation_harnesses: frozenset[str] = frozenset()

    #: The component kind, read because one constraint needs it: a kind the
    #: provider has no route for can never be installed on this harness. Empty
    #: for a setup, which is a composition rather than a kind.
    component_type: str = ""

    owner_id: str = ""
    visibility: str = "private"

    #: Empty means unrestricted. A component that is plain text runs anywhere,
    #: and demanding an explicit list would refuse most of them for nothing.
    supported_os: frozenset[str] = frozenset()
    supported_arch: frozenset[str] = frozenset()

    #: Inclusive `(minimum, maximum)`; either side empty is unbounded. Both
    #: empty declares no requirement and skips the check entirely.
    harness_versions: tuple[str, str] = ("", "")

    requires_capabilities: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    requires_credentials: bool = False

    #: `none`, `user_account` or `external_service`.
    requires_authorization: str = "none"

    license_id: str = ""
    redistribution: bool = True
    entitlements: tuple[str, ...] = ()

    #: Whether the store considers this object part of the registry at all: a
    #: draft and a tombstoned object are both excluded, for different reasons
    #: that the caller has already resolved.
    registrable: bool = True

    #: A moderator's manual state, separate from and on top of `ADR-0032`.
    blocked: bool = False

    #: The four axes of `ADR-0016`. `checks_current` carries double duty by
    #: design: it decides the lane *and*, through `ADR-0032`, whether a new
    #: install is allowed at all.
    author_verified: bool = False
    component_verified: bool = False
    checks_current: bool = False
    owned_or_pinned: bool = False

    #: Whether a consent — request flag or durable record — covers this
    #: candidate. Decided by `consent.consulted` before it gets here; this
    #: engine does not re-derive it, it only refuses to auto-select on it.
    consented: bool = False

    #: Which consent decided, as `scope:target`, or the request flag. Carried
    #: so the recommendation trail and the install plan can record the basis
    #: rather than the bare fact, as the contract's last section requires.
    consent_source: str = ""


@dataclass(frozen=True)
class Refusal:
    """One failed constraint, in terms a caller can branch on."""

    family: str
    code: str
    summary: str

    #: The values that took part in the decision. Required rather than
    #: defaulted: a refusal nobody can act on is a refusal that has not been
    #: written yet.
    details: dict[str, str]


@dataclass(frozen=True)
class Note:
    """One state that is worth saying and does not block anything."""

    code: str
    summary: str
    details: dict[str, str]


@dataclass(frozen=True)
class Assessment:
    """What the mechanical stage decided about one candidate, and why."""

    stable_id: str
    revision_id: str
    lane: str
    lane_reason: str
    admissible: bool
    auto_selectable: bool
    refusals: tuple[Refusal, ...] = ()
    notes: tuple[Note, ...] = ()


def normalise_capability(value: str) -> str:
    """Fold a capability identifier the way the vocabulary defines it."""
    return unicodedata.normalize("NFC", value).strip().casefold()


def well_formed(value: str) -> bool:
    """Whether an identifier has the shape the vocabulary requires.

    Shape is checked before membership so that a typo and an unknown entry stay
    different answers: `capability-vocabulary.md` makes the wrong form the
    author's mistake and the unknown value a different one.
    """
    if not value or len(value) > CAPABILITY_MAX_LENGTH:
        return False
    segments = value.split(".")
    if not CAPABILITY_MIN_SEGMENTS <= len(segments) <= CAPABILITY_MAX_SEGMENTS:
        return False
    return all(
        segment
        and not segment.startswith(("-", "_"))
        and not segment.endswith(("-", "_"))
        and all(character.isalnum() or character in "-_" for character in segment)
        for segment in segments
    )


def observed_capabilities(
    *,
    languages: Iterable[str] = (),
    surfaces: Iterable[str] = (),
    git: bool = False,
    tools_current: Iterable[str] = (),
) -> frozenset[str]:
    """Turn observations into the capability set of `capability-vocabulary.md`.

    Takes names and returns names: the reading of a disk belongs to the caller,
    so this stays decidable twice over the same facts. Anything that would fall
    outside the vocabulary is dropped rather than emitted — a target claiming a
    capability no passport can require would be a value nobody could match.
    """
    held = {f"project.language.{name}" for name in languages}
    held |= {SURFACE_CAPABILITIES[name] for name in surfaces if name in SURFACE_CAPABILITIES}
    held |= {f"toolchain.{name}" for name in tools_current}
    if git:
        held.add("project.vcs.git")
    return frozenset(held & CAPABILITIES)


def assess(candidate: CandidateFacts, target: Target) -> Assessment:
    """Run every mechanical constraint against one candidate.

    All of them, not up to the first failure. REQ-604 asks for an explainable
    trace, and one reason out of six would hide the other five and turn fixing a
    passport into six rounds of guessing.
    """
    lane, lane_reason = lane_of(candidate)
    refusals: list[Refusal] = []
    refusals.extend(_compatibility(candidate, target))
    refusals.extend(_access(candidate, target))
    refusals.extend(_trust(candidate, lane))
    refusals.extend(_license(candidate, target))
    refusals.extend(_entitlement(candidate, target))
    refusals.extend(_provider(candidate, target))

    admissible = not refusals
    return Assessment(
        stable_id=candidate.stable_id,
        revision_id=candidate.revision_id,
        lane=lane,
        lane_reason=lane_reason,
        admissible=admissible,
        # Admissible and automatically selectable are different questions, and
        # `experimental` answers yes to the first and never to the second.
        auto_selectable=admissible and lane != LANE_EXPERIMENTAL,
        refusals=tuple(refusals),
        notes=tuple(_notes(candidate, target)),
    )


def assess_all(candidates: tuple[CandidateFacts, ...], target: Target) -> tuple[Assessment, ...]:
    """Assess many candidates in a stable order.

    Sorted by identifier rather than left in the caller's order: REQ-607 wants
    one canonical input to produce one answer, and the order a dictionary
    happened to be built in is not part of the input.
    """
    return tuple(
        sorted((assess(item, target) for item in candidates), key=lambda item: item.stable_id)
    )


def admissible(assessments: tuple[Assessment, ...]) -> tuple[Assessment, ...]:
    """Only what passed. The set an agent is allowed to be shown."""
    return tuple(item for item in assessments if item.admissible)


def selectable(assessments: tuple[Assessment, ...]) -> tuple[Assessment, ...]:
    """Only what may be chosen without asking. Never anything `experimental`."""
    return tuple(item for item in assessments if item.auto_selectable)


def _declared_harnesses(candidate: CandidateFacts) -> frozenset[str]:
    """The harnesses this object claims, never inferred from a provider route."""
    if candidate.adaptation_harnesses:
        return candidate.adaptation_harnesses
    if candidate.harness_id:
        return frozenset({candidate.harness_id})
    return frozenset()


def _fits_harness(candidate: CandidateFacts, target: Target) -> bool:
    """Whether the object names this harness, or names none and is portable."""
    declared = _declared_harnesses(candidate)
    return not declared or target.harness_id in declared


def _compatibility(candidate: CandidateFacts, target: Target) -> list[Refusal]:
    found: list[Refusal] = []
    # Adaptations are the first-supported compatibility set (`REQ-631`). A
    # provider route never creates one. Historical objects without adaptations
    # keep `harness_id`: a named mismatch stays `harness_mismatch`, and a
    # component that names no harness is portable — a repository-root
    # `AGENTS.md` is one convention four products agreed to read, not four
    # harness-bound surfaces sharing a path. `_provider` then decides from the
    # composition table whether that kind has a surface (`#64`). A setup always
    # names one harness, so an empty value never reaches here from a setup.
    declared = _declared_harnesses(candidate)
    if declared and target.harness_id not in declared:
        if candidate.adaptation_harnesses:
            found.append(
                _refuse(
                    "adaptation_unavailable",
                    "this object has no adaptation for the harness being composed",
                    {
                        "declared": ", ".join(sorted(declared)),
                        "target": target.harness_id,
                    },
                )
            )
        else:
            found.append(
                _refuse(
                    "harness_mismatch",
                    "this object is not for the harness being composed",
                    {"declared": candidate.harness_id, "target": target.harness_id},
                )
            )

    found.extend(_harness_version(candidate, target))

    if candidate.supported_os and target.os not in candidate.supported_os:
        found.append(
            _refuse(
                "os_unsupported",
                "this object does not support this operating system",
                {"declared": ", ".join(sorted(candidate.supported_os)), "target": target.os},
            )
        )
    if candidate.supported_arch and target.arch not in candidate.supported_arch:
        found.append(
            _refuse(
                "arch_unsupported",
                "this object does not support this architecture",
                {"declared": ", ".join(sorted(candidate.supported_arch)), "target": target.arch},
            )
        )

    # Sorted so the answer depends on which capabilities are required and not on
    # the order somebody wrote them into a passport.
    for wanted in sorted({normalise_capability(item) for item in candidate.requires_capabilities}):
        if not well_formed(wanted):
            found.append(
                _refuse(
                    "capability_malformed",
                    "a required capability is not a capability identifier",
                    {"capability": wanted},
                )
            )
        elif wanted not in CAPABILITIES:
            found.append(
                _refuse(
                    "capability_unknown",
                    "a required capability is outside the vocabulary",
                    {"capability": wanted, "vocabulary": CAPABILITY_VOCABULARY_VERSION},
                )
            )
        elif wanted not in target.capabilities:
            found.append(
                _refuse(
                    "capability_missing",
                    "this target does not have a required capability",
                    {"capability": wanted},
                )
            )
    return found


def _harness_version(candidate: CandidateFacts, target: Target) -> list[Refusal]:
    """Compare the detected harness version against a declared range.

    An unreadable version is refused rather than waved through. A declared range
    is a mandatory compatibility condition, and by `ADR-0032` the absence of
    evidence blocks a new install; it gets its own code because the thing to fix
    is a silent `--version`, not the version itself.
    """
    lowest, highest = candidate.harness_versions
    if not lowest and not highest:
        return []

    reading = _reading(target.harness_version)
    if reading is None:
        return [
            _refuse(
                "harness_version_unknown",
                "this object declares a harness version range and the harness reported no version",
                {"declared": _range(lowest, highest), "target": target.harness_version or "none"},
            )
        ]

    floor = _reading(lowest)
    ceiling = _reading(highest)
    if (floor is not None and _below(reading, floor)) or (
        ceiling is not None and _below(ceiling, reading)
    ):
        return [
            _refuse(
                "harness_version_unsupported",
                "the harness on this machine is outside the range this object declares",
                {"declared": _range(lowest, highest), "target": target.harness_version},
            )
        ]
    return []


def _access(candidate: CandidateFacts, target: Target) -> list[Refusal]:
    found: list[Refusal] = []
    if not candidate.registrable:
        found.append(
            _refuse(
                "object_not_registrable",
                "this object is a draft or has been deleted",
                {"stable_id": candidate.stable_id},
            )
        )
    if candidate.blocked:
        found.append(
            _refuse(
                "object_blocked",
                "a moderator has blocked this object",
                {"stable_id": candidate.stable_id},
            )
        )
    # Your own work needs no grant. Asking for one would be asking the owner for
    # permission to use what they wrote.
    if _own(candidate, target) or candidate.visibility == "public":
        return found

    wanted = f"{candidate.stable_id}:{_major(candidate.version)}"
    if wanted not in target.grants:
        found.append(
            _refuse(
                "grant_missing",
                "this private object of another owner is not granted on this major line",
                {"stable_id": candidate.stable_id, "major": _major(candidate.version)},
            )
        )
    return found


def _trust(candidate: CandidateFacts, lane: str) -> list[Refusal]:
    found: list[Refusal] = []
    # A user's own object carries no platform evidence and never did; refusing
    # it for stale evidence would block them from their own work.
    if not candidate.owned_or_pinned and not candidate.checks_current:
        found.append(
            _refuse(
                "evidence_stale",
                "a mandatory check has no current passing evidence",
                {"stable_id": candidate.stable_id},
            )
        )
    if lane == LANE_EXPERIMENTAL and not candidate.consented:
        found.append(
            _refuse(
                "unverified_without_consent",
                "no consent covers this unverified object",
                {"stable_id": candidate.stable_id},
            )
        )
    return found


def _license(candidate: CandidateFacts, target: Target) -> list[Refusal]:
    if _own(candidate, target):
        return []
    found: list[Refusal] = []
    if not candidate.license_id:
        found.append(
            _refuse(
                "license_undeclared",
                "this object of another owner declares no licence",
                {"stable_id": candidate.stable_id},
            )
        )
    if target.for_redistribution and not candidate.redistribution:
        found.append(
            _refuse(
                "redistribution_forbidden",
                "this object may not be redistributed and the composition is for distribution",
                {"stable_id": candidate.stable_id, "license": candidate.license_id or "none"},
            )
        )
    return found


def _entitlement(candidate: CandidateFacts, target: Target) -> list[Refusal]:
    return [
        _refuse(
            "entitlement_not_granted",
            "this object requires a permission this target does not allow",
            {"entitlement": wanted},
        )
        for wanted in sorted(set(candidate.entitlements))
        if wanted not in target.entitlements
    ]


def _provider(candidate: CandidateFacts, target: Target) -> list[Refusal]:
    found: list[Refusal] = []
    if target.harness_id not in target.provider_harnesses:
        found.append(
            _refuse(
                "provider_unavailable",
                "no released provider can install for this harness",
                {"harness_id": target.harness_id},
            )
        )
        # Without a provider there is no platform list to be outside of, and a
        # second refusal here would read as a second thing to fix.
        return found

    # A kind the provider cannot project is not installable, and saying so here
    # is the whole point of putting the mechanical stage before selection
    # (`REQ-601`). Without it the impossibility surfaced only at `select bundle`
    # — after the component was adopted, versioned, proposed and frozen into an
    # immutable SetupVersion, which is a late and expensive place to learn it.
    #
    # Not `harness_mismatch`: the object does name this harness, and a familiar
    # refusal that is accurate about the wrong thing costs more than a new one.
    #
    # Skipped entirely when the harness already mismatches, for the reason the
    # provider check above states: whether some other harness could project this
    # kind is not a second thing to fix, and reading as one is worse than saying
    # less.
    if (
        candidate.component_type
        and _fits_harness(candidate, target)
        and not native_surface(candidate.component_type, target.harness_id)
    ):
        found.append(
            _refuse(
                "provider_surface_unavailable",
                "this harness has no native surface for that component kind",
                {"harness_id": target.harness_id, "component_type": candidate.component_type},
            )
        )

    platform = f"{target.os}/{target.arch}"
    if target.provider_platforms and platform not in target.provider_platforms:
        found.append(
            _refuse(
                "provider_platform_unsupported",
                "the released provider does not support this platform",
                {"harness_id": target.harness_id, "platform": platform},
            )
        )
    return found


def _notes(candidate: CandidateFacts, target: Target) -> list[Note]:
    """States worth saying that never block. Names only, never values."""
    found: list[Note] = []
    missing = sorted(set(candidate.required_env) - target.env_present)
    if missing:
        found.append(
            Note(
                NOTE_REQUIRED_ENV_MISSING,
                "install is allowed; readiness stays needs_configuration until these are set",
                {"names": ", ".join(missing)},
            )
        )
    if candidate.requires_authorization != "none":
        found.append(
            Note(
                NOTE_AUTHORIZATION_REQUIRED,
                "this object needs an authorization completed after install",
                {"kind": candidate.requires_authorization},
            )
        )
    if candidate.requires_credentials:
        found.append(
            Note(
                NOTE_CREDENTIALS_REQUIRED,
                "this object needs credentials you will be asked to configure",
                {"stable_id": candidate.stable_id},
            )
        )
    return found


def _refuse(code: str, summary: str, details: dict[str, str]) -> Refusal:
    """Build a refusal, refusing to build one for an undeclared code.

    The lookup is the guard: a code that is not in `REFUSALS` is a reason this
    contract never declared, and letting it through would put a string nobody
    can branch on into a machine answer.
    """
    return Refusal(family=REFUSALS[code], code=code, summary=summary, details=details)


def _own(candidate: CandidateFacts, target: Target) -> bool:
    return bool(target.owner_id) and candidate.owner_id == target.owner_id


def _major(version: str) -> str:
    head = version.split(".")[0]
    return head if head.isdigit() else "0"


def _range(lowest: str, highest: str) -> str:
    return f"{lowest or 'any'}..{highest or 'any'}"


def _reading(text: str) -> tuple[tuple[int, ...], int] | None:
    """A version as comparable numbers, or `None` when there is no version here.

    A harness reports what it likes. `claude` answers `2.1.224 (Claude Code)`
    and `codex` answers `codex-cli 0.146.0`: the version leads one line and
    trails the other. A parser demanding a bare dotted number would call both
    unreadable and refuse every candidate that declares a range, so the first
    word that *is* a version is what is read.

    The second element carries release ordering: `1.2.3-beta` precedes `1.2.3`,
    as it does everywhere else. Dropping the suffix instead would let a
    prerelease satisfy a floor that was written to exclude it.
    """
    for word in text.split():
        match = _NUMERIC.match(word)
        if match is None:
            continue
        numbers = tuple(int(part) for part in match.group(1).split("."))
        return numbers, 0 if word[match.end() :].startswith("-") else 1
    return None


def _below(left: tuple[tuple[int, ...], int], right: tuple[tuple[int, ...], int]) -> bool:
    """Whether one reading precedes another, `1.2` and `1.2.0` being one version.

    Padded to equal depth before comparing, because a tuple comparison would
    otherwise make `1.2` precede `1.2.0` on length alone and quietly exclude a
    version that is the floor.
    """
    depth = max(len(left[0]), len(right[0]))
    return (_padded(left[0], depth), left[1]) < (_padded(right[0], depth), right[1])


def _padded(numbers: tuple[int, ...], depth: int) -> tuple[int, ...]:
    return numbers + (0,) * (depth - len(numbers))
