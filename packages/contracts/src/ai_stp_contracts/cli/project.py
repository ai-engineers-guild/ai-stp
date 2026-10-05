"""Project discovery, the project index, imports and symbol outlines."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_passports.versions import ComponentType


class ProjectCandidate(ContractModel):
    """One directory that could be registered as a project (`SPEC-004`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Rendered with the home directory folded away, like every reported path.
    root: Annotated[str, Field(min_length=1)]

    #: `project`, or `nested_repository` for a repository inside another one.
    #: A nested repository is reported so the user can see it and registered only
    #: on an explicit choice (REQ-410).
    kind: Literal["project", "nested_repository"]

    #: `new` covers an empty folder, an empty repository and a folder holding
    #: only documentation — none of them has anything to index yet (REQ-402).
    state: Literal["new", "established"]

    #: What identified it: manifest file names, `git`, or nothing.
    markers: list[str]

    #: Why it is classified this way, in words a caller can show a person.
    reason: Annotated[str, Field(min_length=1)]


class DiscoveryDiagnostic(ContractModel):
    """One path skipped while examining an explicit project discovery root."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]
    code: Literal["excluded", "entry_limit", "symlink", "unreadable"]
    reason: Annotated[str, Field(min_length=1)]


class ProjectCandidates(ContractModel):
    """Everything found inside one directory the user named."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    discovery_root: Annotated[str, Field(min_length=1)]
    complete: bool
    candidates: list[ProjectCandidate]
    diagnostics: list[DiscoveryDiagnostic]


class IndexedFile(ContractModel):
    """One file the index knows about, described without keeping its content."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: Relative to the project root, POSIX form. No absolute path reaches a
    #: passport, and two machines indexing the same tree agree.
    path: Annotated[str, Field(min_length=1)]
    kind: Literal["manifest", "lock", "agent_surface", "source", "document", "config", "text"]
    language: str | None = None
    size_bytes: Annotated[int, Field(ge=0)]

    #: `None` when the file was too large to read; its size is still known.
    digest: str | None = None
    lines: int | None = None


class ExcludedPath(ContractModel):
    """One path left out of the index, and why."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]


class ProjectIndex(ContractModel):
    """The bounded second-level index of one project root (`SPEC-004`).

    `state` is `partial` when a size, depth, entry or time bound was reached.
    Saying so is the point: a short answer that looks complete is worse than a
    complete answer that says where it stopped.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    state: Literal["complete", "partial"]
    stopped_by: str | None = None
    files: list[IndexedFile]
    excluded: list[ExcludedPath]


class ImportedFile(ContractModel):
    """One configuration file an inspection read."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1)]
    byte_length: Annotated[int, Field(ge=0)]
    digest: str = ""

    #: Key names whose value was removed. Names only: `SPEC-008` REQ-815 allows
    #: the name of a mandatory variable into a passport and nothing else, and a
    #: list of what was redacted would be a list of secrets.
    redacted_keys: list[str] = []

    #: Why the file was not read, when it was not. Kept apart from "no secrets
    #: found": one is a clean file and the other is a file nobody looked at.
    unreadable: str = ""

    #: Set when the file was read and hashed but is larger than an imported
    #: configuration file may be. It is excluded from every proposed component
    #: and it is not a blocker: the import bound is a declared policy, not a
    #: failure to see the file.
    oversized: bool = False


class ImportInspection(ContractModel):
    """What one native configuration holds, read and nothing more (`REQ-813`).

    `detection_rule` says how secrets were looked for. A report that will not
    say how it looked cannot be told apart from one that looked properly, and
    this one is deliberately partial — it matches key names, so a credential
    stored under a name that says nothing is not found.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    detection_rule: Annotated[str, Field(min_length=1)]
    files: list[ImportedFile] = []
    redacted_keys: list[str] = []
    unreadable: list[str] = []

    #: Files excluded by the import size bound. Separate from `unreadable`
    #: because the remedies differ: an oversized file is excluded by policy,
    #: while an unreadable one means the configuration was not fully seen.
    oversized: list[str] = []


class SetupImportComponent(ContractModel):
    """One native component proposed by a read-only setup import plan."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    candidate_id: Annotated[str, Field(min_length=1)]
    component_type: ComponentType
    native_role: Annotated[str, Field(min_length=1)]
    paths: Annotated[list[str], Field(min_length=1)]
    file_set_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    byte_length: Annotated[int, Field(ge=0)]


class SetupImportPlan(ContractModel):
    """Deterministic read-only decomposition of one native setup candidate."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    harness_id: HarnessId
    inspection_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    components: list[SetupImportComponent] = []
    excluded: list[str] = []
    blocked_by: list[str] = []
    effects: list[str] = []


class ImportedSetup(ContractModel):
    """A registered import and the backup it was taken alongside.

    Two identifiers because they are two objects (`REQ-814`). A backup says
    where the old bytes are; a setup says what was made from them. Deleting the
    first must not delete the identity of the second.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    revision_id: Annotated[str, Field(min_length=1)]
    backup_id: Annotated[str, Field(min_length=1)]
    redacted_keys: list[str] = []
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    component_ids: Annotated[list[str], Field(min_length=1)]


class LanguageOutline(ContractModel):
    """What one language contributes to a project (`SPEC-004` REQ-404).

    `method` carries the strength of the answer, and it is not decoration.
    `syntax_tree` means a real parser read the file; `line_scan` means the words
    were recognised line by line and a string containing them would be
    indistinguishable from a declaration. Reporting both as plain symbol counts
    would hide that difference exactly where a caller decides how far to trust
    them.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    language: Annotated[str, Field(min_length=1)]

    #: `REQ-412`: a language with no adapter is `not_available` with a reason,
    #: never a partial index presented as a whole one.
    state: Literal["available", "not_available"]
    method: Literal["syntax_tree", "line_scan"] | None = None
    reason: str | None = None
    files: Annotated[int, Field(ge=0)]
    symbols: Annotated[int, Field(ge=0)]
    tests: Annotated[int, Field(ge=0)]
    entry_points: list[str] = []


class ProjectSymbols(ContractModel):
    """The table of contents of one project, and nothing deeper (`REQ-411`).

    No call graph, no vector representations, no symbol bodies. `state` is
    `partial` when the file budget was reached, for the same reason the index
    says so: a short answer that looks complete is the worse failure.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    root: Annotated[str, Field(min_length=1)]
    state: Literal["complete", "partial"]
    stopped_by: str | None = None
    languages: list[LanguageOutline]
