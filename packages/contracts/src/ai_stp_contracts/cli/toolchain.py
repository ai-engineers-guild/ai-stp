"""Harness programs, managed CLI programs, tool installations and the
toolchain survey.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_passports.versions import ComponentType


class HarnessProgramArtifact(ContractModel):
    """One archive a program plan named, as the plan named it.

    Repeated here rather than summarised because the consumer fetched exactly
    this and an agent reading the result may want to check the same bytes
    itself. `entry_point` is relative to the prefix and is the path the provider
    exposes there — not a path inside the archive.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    platform: Annotated[str, Field(min_length=1)]
    url: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    byte_length: Annotated[int, Field(gt=0)]
    entry_point: Annotated[str, Field(min_length=1)]


class HarnessProgram(ContractModel):
    """The outcome of one program lifecycle operation (`ADR-0122`).

    The subject is the harness program under `--prefix`, not the configuration
    in `--target`. `state` is what the provider reported after the effect, and
    `verified` is the only state that says the program is installed and its
    identity confirmed.

    `operation_id` names the journal entry, which is the same journal a setup
    installation uses: the state machine, the backup and the plan digest do not
    change with the subject.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]
    operation: Literal["software_install", "software_update", "software_remove"]
    state: Annotated[str, Field(min_length=1)]
    operation_id: Annotated[str, Field(min_length=1)]
    prefix: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]

    #: What the plan said it would do, verbatim. A plan with no effects changes
    #: nothing and is refused before it reaches here.
    effects: list[str]

    #: Empty for `software_remove`, which deletes what is already there and
    #: fetches nothing.
    artifacts: list[HarnessProgramArtifact] = []

    #: Present once the provider has exposed a command, as an absolute path.
    #: Read from the provider's own answer rather than joined here, so the two
    #: cannot disagree.
    executable: str = ""
    version: str = ""

    #: `software_remove` only. `false` means there was nothing of this program
    #: under the prefix — which is a success, because removing is idempotent,
    #: and a different answer from having removed something. Collapsing the two
    #: into `verified` alone leaves an agent unable to tell an absence from a
    #: deletion, and an absence that reads as a deletion invites a retry that
    #: will never change anything.
    removed: bool | None = None

    #: What an interrupted earlier operation left, resolved by the provider
    #: under the lock before it read the prefix. Empty on every ordinary run.
    #:
    #: Declared rather than left to `extra="allow"`, which would accept the key
    #: and then drop it: a prefix the provider had to recover would read
    #: identically to a clean one, and the one moment the operator could have
    #: learned an earlier run was interrupted would pass in silence.
    #:
    #: The provider resolves this itself because a consumer cannot ask for it.
    #: `recover-operation` names a `--target`, and program work happens under a
    #: `--prefix` — a different root with a different lifetime — so there is
    #: nowhere in the request to name one. Surfacing what the provider did is
    #: the whole of what this side can offer until that changes.
    recovered: list[str] = []


class HarnessProgramOperation(ContractModel):
    """One program operation this installation recorded against a prefix."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    operation_id: Annotated[str, Field(min_length=1)]
    operation: Literal["software_install", "software_update", "software_remove"]
    state: Annotated[str, Field(min_length=1)]
    at: Annotated[str, Field(min_length=1)]


class HarnessProgramStatus(ContractModel):
    """What stands under one prefix, read from the disk and from the journal.

    The standing report the program lifecycle owes, and the only one
    (`ADR-0122`). `toolchain harnesses` answers a different question — what is
    visible on this machine — and the two vocabularies are kept disjoint so no
    word carries two subjects.

    Two independent sources, deliberately: the journal says what this
    installation did, the filesystem says what is there now. Reporting only the
    first would have called a verified operation a success on an empty prefix,
    which is exactly what happened once — a provider unpacked into a sandbox's
    own tmpfs, verified it where every check was true, and the files died with
    the namespace. `lost` exists to make that one glance rather than an
    investigation.

    `version` comes from the journal and never from running the program.
    Asking a binary its version would execute a foreign executable from a
    command declared `read`, which is the same reason `doctor` only checks that
    `gh` is present.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]
    prefix: Annotated[str, Field(min_length=1)]

    #: - `present` — this installation put a program here and it is here.
    #: - `removed` — this installation's last word was a removal, and nothing
    #:   is here. Distinct from `never_installed` for the same reason
    #:   `removed: false` is distinct from `verified`: an absence that reads as
    #:   a deletion invites a retry that cannot change anything.
    #: - `never_installed` — no record, nothing here.
    #: - `foreign` — something is here that this installation did not put here.
    #:   The provider behaves the same way: it removes only what it installed,
    #:   and an unowned sibling copy survives and is reported.
    #: - `lost` — a verified operation is recorded and the program is not on
    #:   disk. Nothing else in the system reports this.
    #: - `interrupted` — an operation against this prefix stopped without
    #:   settling. It outranks the rest because it is the one that needs an
    #:   action rather than a reading.
    state: Literal["present", "removed", "never_installed", "foreign", "lost", "interrupted"]
    reason: Annotated[str, Field(min_length=1)]

    #: Read from the filesystem now. Absolute, and empty when nothing is there.
    executable: str = ""

    #: Relative to the prefix, as the provider exposed it — `bin/<command>`,
    #: never a path inside the archive.
    entry_point: str = ""

    #: From the journal. Empty when this installation has no verified record.
    version: str = ""
    operation_id: str = ""
    recorded_operation: str = ""
    recorded_state: str = ""
    recorded_at: str = ""

    #: Every operation against this prefix that stopped without settling, so a
    #: caller that reads `state` alone still learns there is something to
    #: recover.
    stopped: list[HarnessProgramOperation] = []


class ToolInstallation(ContractModel):
    """The outcome of one managed install (`SPEC-014` REQ-1405, REQ-1410, REQ-1411).

    `action` is what happened, not what was attempted. `needs_user_action` means
    something outside the managed directory would have to change, and the plan
    says exactly what — `REQ-1410` forbids the agent obtaining a password to do
    it instead.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    tool_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    action: Literal["installed", "already_installed", "needs_user_action", "removed"]
    reason: Annotated[str, Field(min_length=1)]

    #: The exact path the tool is invoked by (`REQ-1404`). Never a bare name:
    #: the surrounding `PATH` is not a source of truth for a managed toolchain.
    binary: str | None = None

    #: Whether this could be carried out with no network (`REQ-1413`).
    offline_capable: bool = False

    #: Every path created or removed (`REQ-1411`). An uninstall reads this list
    #: rather than deciding what looks like ours.
    paths: list[str] = []

    #: Paths deliberately left alone, with the reason. A user's own file inside
    #: a tool directory is theirs.
    kept: list[str] = []


class CliProgram(ContractModel):
    """Shared executable lifecycle for one catalog `cli` component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    operation: Literal["install", "invoke", "status", "remove"]
    state: Literal["present", "removed", "never_installed", "invoked"]
    prefix: Annotated[str, Field(min_length=1)]
    executable: str = ""
    exit_code: int | None = None
    output: str = ""


class PinnedTool(ContractModel):
    """One tool the managed profile pins (`SPEC-014` REQ-1403)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    tool_id: Annotated[str, Field(min_length=1)]
    purpose: Annotated[str, Field(min_length=1)]

    #: Exact, never a range: a range would let two installations differ while
    #: both looked pinned.
    version: Annotated[str, Field(min_length=1)]
    license: Annotated[str, Field(min_length=1)]

    #: Exact source and its integrity proof for *this* platform.
    source: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(min_length=1)]

    #: How the proof was obtained. A checksum the vendor published is an
    #: upstream statement about the artifact; one pinned during a single
    #: download only proves nothing changed since. Different strengths, kept
    #: apart so the difference survives into the answer.
    digest_source: Literal["vendor_published", "pinned_on_download"]


class EcosystemCoverage(ContractModel):
    """What the profile offers for one ecosystem, including nothing."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    ecosystem: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    state: Literal["available", "not_available"]

    #: Present exactly when `state` is `not_available`. `REQ-1407` asks for the
    #: reason: an agent reading a short list cannot otherwise tell "nothing
    #: needed" from "nothing yet".
    reason: str | None = None
    tools: list[PinnedTool]


class HarnessInstallation(ContractModel):
    """One place a harness was found (`SPEC-014` REQ-1417)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Absolute and verified, rendered with the home directory folded away.
    path: Annotated[str, Field(min_length=1)]

    #: The exact version, or `unknown`. Never a guess: `REQ-1415` allows the
    #: word and not an invented number.
    version: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]
    surface: Literal["cli", "desktop"] = "cli"
    version_source: Literal[
        "process", "package_metadata", "windows_package_metadata", "unavailable"
    ] = "process"
    diagnostic: Annotated[str, Field(min_length=1)] = "version_reported"


class HarnessPresence(ContractModel):
    """What is known about one harness on this machine (`REQ-1415`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harness_id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    support: Literal["primary", "beta"]
    state: Literal["configured", "installed", "unknown_version", "available"]

    #: Every installation rather than the first: two versions of one harness on
    #: one machine is ordinary, and reporting one hides the other.
    installations: list[HarnessInstallation]

    #: The user configuration root, when there is one.
    configuration: str | None = None
    reason: Annotated[str, Field(min_length=1)]


class HarnessSurvey(ContractModel):
    """Every declared harness, whether or not it is here.

    Total by construction. A harness absent from the answer would be
    indistinguishable from one this build does not support, and `REQ-1414`
    makes the supported set the point.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    harnesses: list[HarnessPresence]


#: What this build can do with one kind on one harness, and the four answers are
#: four different situations that `unsupported` was one word for (`#462`).
#:
#: `supported` — the product has the surface at a scope a provider owns, and
#: this compiler routes it.
#: `projection_missing` — the surface exists and nothing routes it yet. Waiting
#: helps: the work is on this side.
#: `project_only` — the surface exists where no provider writes, so there is
#: nothing to project and nothing missing.
#: `routed_only` — this compiler routes it and the catalogue records no row at
#: an owned scope, which is either a translation or a catalogue behind its
#: source; `tests/contract/test_capability_states.py` names each one.
#: `unsupported` — the product has no such surface anywhere.
type CapabilityState = Literal[
    "supported", "projection_missing", "project_only", "routed_only", "unsupported"
]


class HarnessComponentCapability(ContractModel):
    """One `(harness, kind)` cell, with native support and projection kept apart.

    Reading a single list of kinds as "what can be installed" is the mistake
    this exists to remove: the catalogue answers what the *product* reads, and
    the compiler answers what this build can hand a provider. They are different
    questions and they disagree on ten of the native-layout cells.

    **None of these fields claims a component is active.** Whether an installed
    thing is loaded, parsed and running is a third question, and for at least
    one surface it is not answerable from outside the product at all: driven at
    a temporary `CODEX_HOME` in four states — valid, malformed, an invented
    event name, an invented top-level key — codex produced byte-identical
    output, and identical again with the file absent. A model that reported
    "active" would have to invent that answer for codex hooks. Runtime evidence
    is a separate record tied to versions, OS and scope (`#462`, item 8).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    component_type: ComponentType
    #: The product reads this kind somewhere, at any scope.
    native_support: bool
    #: ...and at a scope a provider owns, which is what makes it projectable.
    native_at_owned_scope: bool
    #: This build has a compiler route for it.
    projection_support: bool
    #: Where the product reads it, in catalogue order: `global` is the harness
    #: configuration home, `user_root` the shared convention root, `project` a
    #: directory in somebody's repository. `#462` item 2: a cell is not one
    #: answer, and "native" at `project` means something a provider cannot act
    #: on.
    native_scopes: list[str]
    #: Which scopes this build routes it to; empty when nothing routes it.
    projection_scopes: list[str]
    state: CapabilityState
    #: Why the state is not `supported`, or `None` when it is. `#462` item 4
    #: asks for a machine reason, and these were written twice in places a
    #: caller could not read — beside each rule in a comment, and in a contract
    #: test's table.
    reason: str | None = None


class HarnessCapabilityRow(ContractModel):
    """One executable row from the closed harness capability catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    harness_id: HarnessId | Literal["undefined"]
    title: Annotated[str, Field(min_length=1)]
    support: Literal["primary", "beta", "portable"]
    #: Every kind the *product* reads, at any scope. Kept because it is a true
    #: fact about the harness, and no longer the only one reported: read alone
    #: it was taken for effective support, which is `#462`.
    component_types: list[ComponentType]
    #: Every closed kind, each with its own state — present for every kind rather
    #: than only the interesting ones, because a caller building a matrix should
    #: not have to infer absence from a missing row.
    #:
    #: `null`, and only, for a row no provider owns: the shared-convention row
    #: carries `no_single_harness_owner` in `gaps`, and a projection state needs
    #: somebody to project. Reporting `projection_missing` there would say the
    #: work is ours when there is no provider to route to, and reporting
    #: `unsupported` would say the convention does not exist. An absent answer
    #: is the true one.
    components: list[HarnessComponentCapability] | None = None
    native_authoring: list[str]
    global_layouts: list[str]
    project_layouts: list[str]
    layout_sources: list[str]
    gaps: list[str]


class HarnessCapabilityTable(ContractModel):
    """The complete supported harness table, including shared conventions."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    harnesses: list[HarnessCapabilityRow]


class ToolchainProfile(ContractModel):
    """The managed toolchain as it resolves on this machine (`SPEC-014`).

    Policy, not project: `REQ-1402` makes an empty project and a documentation
    project resolve to the same profile, because what a developer needs
    installed is not deducible from what they have written so far.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    profile: Annotated[str, Field(min_length=1)]
    platform: Annotated[str, Field(min_length=1)]
    ecosystems: list[EcosystemCoverage]
