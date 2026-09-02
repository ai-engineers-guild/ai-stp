"""Importing existing native configuration, safely (`#174`, `SPEC-008` REQ-813).

Somebody already has a working harness. Importing it must not break it, must not
carry their secrets into a registry, and must not pretend the result is more
trustworthy than what it was made from.

**Inspection changes nothing.** `REQ-813` puts inspection first and in
inspection order, and this module reads: it opens files, hashes them and reports.
Nothing here writes to a harness target, and there is no argument shape that
lets it. The backup belongs to the provider; `ai_stp` holds a reference to it and
never the bytes.

**Secret values never enter the registry, and the inventory says only names.**
`REQ-815` allows an imported setup to carry the *names* of mandatory environment
variables and nothing else. So scrubbing replaces a value in place and records
the key it sat under — a redacted document plus a list of names, never a list of
what was redacted.

**The inventory reports what was scanned, not that nothing was missed.**
Detection is by key name, because the alternative — guessing from the shape of a
string — calls a project identifier a secret and misses a password stored under
`value`. An honest partial answer beats a confident wrong one, so the report
names the rule it used and the caller decides.

**A `BackupRef` is not an identity.** `REQ-814` keeps them separate objects: a
backup says where the old bytes are, an imported setup says what was made from
them. Conflating the two would make deleting a backup delete a setup's identity.
"""

import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

import tomlkit
import tomlkit.exceptions
import yaml

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    components,
    composition,
    content,
    harness_catalog,
    journal,
    mcp_clients,
    reading,
    revisions,
)
from ai_stp_cli.local.database import transaction
from ai_stp_cli.paths import redact_any_home
from ai_stp_cli.provider import protocol_v3
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

#: Key names whose value is a credential. Matched case-insensitively against the
#: whole key and against its last dotted segment, so `auth.token` is caught as
#: readily as `token`.
SECRET_KEYS: Final[frozenset[str]] = frozenset(
    {
        "api_key",
        "apikey",
        "access_key",
        "access_token",
        "auth_token",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "key",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "session_token",
        "token",
    }
)

#: What replaces a value that was removed. A fixed marker rather than a blank:
#: an empty string reads as "this setting is off", and the whole point is that
#: the setting exists and its value was not carried.
REDACTED: Final[str] = "<redacted-on-import>"

#: What the inventory says it did. Named so a caller can tell a complete answer
#: from this one, which is not complete and does not claim to be.
DETECTION_RULE: Final[str] = "key-name"

#: Files that are configuration worth importing. A binary or an artifact is not
#: configuration, and importing one would carry bytes nobody reviewed.
#: `.jsonc` because opencode reads it wherever it reads `.json` — the catalog
#: declares both spellings — and `.mdc` because cursor rules are written in it;
#: both were invisible to import while discovery already knew them.
IMPORTABLE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".json", ".jsonc", ".toml", ".yaml", ".yml", ".md", ".mdc", ".txt"}
)

#: Bound on one imported file. A harness configuration is text somebody wrote;
#: anything larger is not the thing this is for.
MAX_FILE_BYTES: Final[int] = 1024 * 1024

#: Bound on one inspected tree. A configuration root is a few hundred files at
#: the wild extreme; a tree past this is not a configuration and walking the
#: rest of it would spend the reader's time describing something else.
MAX_INSPECTED_FILES: Final[int] = 10_000


@dataclass(frozen=True)
class Placed:
    """One catalogue layout this file answers to: what it is, and where it ends.

    A physical path can answer to more than one — codex's `config.toml` is the
    `setting` and, when it declares servers, the host of an `mcp` contribution
    — so a file carries a tuple of these rather than one classification.
    """

    component_type: str
    native_role: str

    #: The component family boundary: the layout-relative directory child for a
    #: directory layout, the path itself for a file layout, and
    #: `path#declared_key` for a contribution living inside a host file.
    boundary: str

    #: The structured key a contribution owns inside its host file, empty for a
    #: whole-file or directory component.
    declared_key: str = ""

    #: The entry names the host file declares under `declared_key`, read as
    #: names only. These are the component's native identities — `config.toml`
    #: is the container, never the identity.
    entry_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    """One file the inspection read, and what it holds."""

    path: str
    byte_length: int
    digest: str

    #: Key names whose value was removed. Names only — `REQ-815` allows the name
    #: of a mandatory variable into a passport and nothing else, and a list of
    #: what was redacted would be the list of secrets.
    redacted_keys: tuple[str, ...] = ()

    #: Set when the file could not be read at all. Kept apart from "no secrets
    #: found": one is a clean file and the other is a file nobody looked at.
    unreadable: str = ""

    #: Set when the file was read and hashed but exceeds `MAX_FILE_BYTES`. That
    #: is a declared exclusion policy, not a failure to see the file, so it must
    #: not reach `unreadable`: the two need different remedies and only one of
    #: them means the configuration was not fully described.
    oversized: bool = False

    #: Set when the path was refused rather than read: a symlink, a hardlink or
    #: a special file. Naming which is the difference between a report and a
    #: shrug, and none of the three may contribute bytes to a capture — a link
    #: reads bytes from outside the tree, a second name can swap them later.
    refused: str = ""

    #: What the catalogue says this file is, possibly several things at once.
    candidates: tuple[Placed, ...] = ()

    #: The structured format the scrubber actually rewrote, or `none` when the
    #: bytes went through untouched. The inventory used to imply every file was
    #: scanned; this is the honest per-file answer.
    scrub_format: str = "none"


@dataclass(frozen=True)
class Inspection:
    """What one native configuration looks like, read and nothing more."""

    root: str
    harness_id: str
    findings: tuple[Finding, ...]

    #: The rule detection used. A report that does not say how it looked cannot
    #: be told apart from one that looked properly.
    detection_rule: str = DETECTION_RULE

    @property
    def redacted_keys(self) -> tuple[str, ...]:
        return tuple(sorted({name for item in self.findings for name in item.redacted_keys}))

    @property
    def unreadable(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.findings if item.unreadable)

    @property
    def oversized(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.findings if item.oversized)

    @property
    def refused(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.findings if item.refused)

    @property
    def skipped(self) -> tuple[str, ...]:
        """Every path that contributes to no component, for any reason."""
        return tuple(sorted({*self.unreadable, *self.oversized, *self.refused}))


@dataclass(frozen=True)
class BackupRef:
    """Where the provider put the old bytes. Not a setup, and not an identity."""

    backup_id: str
    harness_id: str
    target_id: str

    #: The provider's own reference. `ai_stp` never holds backup bytes: they are
    #: the provider's, and copying them would make two owners of one recovery.
    provider_ref: str
    created_at: str


@dataclass(frozen=True)
class Imported:
    """One imported setup and the backup it was taken alongside.

    Two fields rather than one object, because they are two objects. Deleting a
    backup must not delete a setup's identity, and it cannot when the identity
    was never the backup's.
    """

    stable_id: str
    revision_id: str
    backup_id: str
    plan_digest: str = ""
    component_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProposedComponent:
    """One natural native component boundary found inside an inspection."""

    candidate_id: str
    component_type: str
    native_role: str
    paths: tuple[str, ...]
    file_set_digest: str
    byte_length: int

    #: Carried from the layout when this component is a contribution to a host
    #: file: the key it owns, and the entry names it declares there. The entry
    #: names are the native identities; the host filename never is.
    declared_key: str = ""
    entry_names: tuple[str, ...] = ()

    #: The boundary `Placed` computed: the path every member is relative to.
    #: A file layout's own path, a directory layout's first child, or
    #: `path#key` for a contribution. Carried rather than re-derived so the
    #: registration packages members the way the compiler will read them —
    #: relative to the component, never to the harness root (`#63`).
    boundary: str = ""


@dataclass(frozen=True)
class Plan:
    """A content-addressed, read-only proposal for registering one setup graph."""

    root: str
    harness_id: str
    inspection_digest: str
    plan_digest: str
    components: tuple[ProposedComponent, ...]
    excluded: tuple[str, ...]
    blocked_by: tuple[str, ...]
    effects: tuple[str, ...]


def plan(inspection: Inspection) -> Plan:
    """Decompose an inspection without creating identities or storing bytes."""
    inspection_document: dict[str, JsonValue] = {
        "root": inspection.root,
        "harness_id": inspection.harness_id,
        "detection_rule": inspection.detection_rule,
        "files": [
            {
                "path": item.path,
                "byte_length": item.byte_length,
                "digest": item.digest,
                "redacted_keys": list(item.redacted_keys),
                "unreadable": item.unreadable,
                "oversized": item.oversized,
                "refused": item.refused,
                "scrub_format": item.scrub_format,
                "candidates": [
                    {
                        "component_type": placed.component_type,
                        "native_role": placed.native_role,
                        "boundary": placed.boundary,
                        "declared_key": placed.declared_key,
                        "entry_names": list(placed.entry_names),
                    }
                    for placed in item.candidates
                ],
            }
            for item in inspection.findings
        ],
    }
    inspection_digest = digest_canonical("ai-stp:native-discovery:v1", inspection_document)
    grouped: dict[tuple[str, str], list[tuple[Finding, Placed]]] = {}
    excluded: list[str] = []
    for item in inspection.findings:
        if item.unreadable or item.oversized or item.refused:
            excluded.append(item.path)
            continue
        for placed in item.candidates:
            grouped.setdefault((placed.component_type, placed.boundary), []).append((item, placed))

    proposed: list[ProposedComponent] = []
    for (component_type, boundary), members in sorted(grouped.items()):
        native_role = members[0][1].native_role
        declared_key = members[0][1].declared_key
        entry_names = members[0][1].entry_names
        findings = sorted({item for item, _placed in members}, key=lambda found: found.path)
        paths = tuple(item.path for item in findings)
        material: dict[str, JsonValue] = {
            "harness_id": inspection.harness_id,
            "component_type": component_type,
            "native_role": native_role,
            "boundary": boundary,
            "declared_key": declared_key,
            "entry_names": list(entry_names),
            "files": [
                {"path": item.path, "digest": item.digest, "byte_length": item.byte_length}
                for item in findings
            ],
        }
        file_set_digest = digest_canonical("ai-stp:plan:v1", material)
        candidate_id = digest_canonical("ai-stp:native-discovery:v1", material)
        proposed.append(
            ProposedComponent(
                candidate_id=candidate_id,
                component_type=component_type,
                native_role=native_role,
                paths=paths,
                file_set_digest=file_set_digest,
                byte_length=sum(item.byte_length for item in findings),
                declared_key=declared_key,
                entry_names=entry_names,
                boundary=boundary,
            )
        )

    # Only a file nobody could read blocks. An oversized one is already in
    # `excluded`, and listing the same path as both "left out" and "in your way"
    # is a contradiction the caller cannot act on.
    blocked = tuple(f"unreadable:{path}" for path in sorted(inspection.unreadable))
    effects = (
        f"register {len(proposed)} component draft(s)",
        "register one private setup draft with exact component references",
    )
    plan_document: dict[str, JsonValue] = {
        "inspection_digest": inspection_digest,
        "harness_id": inspection.harness_id,
        "components": [
            {
                "candidate_id": item.candidate_id,
                "component_type": item.component_type,
                "native_role": item.native_role,
                "paths": list(item.paths),
                "file_set_digest": item.file_set_digest,
                "byte_length": item.byte_length,
                "declared_key": item.declared_key,
                "entry_names": list(item.entry_names),
                "boundary": item.boundary,
            }
            for item in proposed
        ],
        "excluded": cast(list[JsonValue], sorted(excluded)),
        "blocked_by": cast(list[JsonValue], list(blocked)),
        "effects": cast(list[JsonValue], list(effects)),
    }
    return Plan(
        root=inspection.root,
        harness_id=inspection.harness_id,
        inspection_digest=inspection_digest,
        plan_digest=digest_canonical("ai-stp:plan:v1", plan_document),
        components=tuple(proposed),
        excluded=tuple(sorted(excluded)),
        blocked_by=blocked,
        effects=effects,
    )


#: The native role each component kind reports, matching what `component
#: discover` reports for the same kind so the two capture paths speak one
#: vocabulary.
_ROLE_OF: Final[dict[str, str]] = {
    "skill": "skill",
    "command": "command",
    "agent": "agent",
    "hook": "hook",
    "plugin": "plugin",
    "mcp": "mcp_server",
    "instruction": "instruction",
    "setting": "configuration",
}


def _global_layouts(harness_id: str) -> tuple[harness_catalog.Layout, ...]:
    """This harness's global layouts, longest path first.

    The catalogue is the one owner of what a native path means — discovery
    already consumes it, and import used to carry its own five-name guess
    beside it, which is how codex `prompts/` became a `setting` while the
    catalogue two files away said `command`. Longest first so `plugins/local`
    wins over any shorter prefix that may one day sit above it.

    Only layouts rooted at the configuration directory: an import inspects one
    root, and a `home`-rooted shared convention lives outside it.
    """
    definition = harness_catalog.BY_ID.get(harness_id)
    if definition is None:
        return ()
    layouts = tuple(
        layout
        for layout in definition.layouts
        if layout.scope == "global" and layout.root == "config"
    )
    return tuple(sorted(layouts, key=lambda layout: len(layout.relative), reverse=True))


def classify(harness_id: str, relative: str, place: Path) -> tuple[Placed, ...]:
    """Everything the catalogue says this file is, in one deterministic answer.

    A file may be several things at once — a `config.toml` is the `setting`
    and, when it declares servers, the host of an `mcp` contribution — so the
    answer is a tuple. A file no layout claims stays a `setting` with its own
    path as its boundary: capturing an authored file the catalogue has not met
    beats inventing a kind for it, and beats dropping it.

    Directory layouts claim the first child under them as the component
    boundary, which is what makes `plugins/local/<name>` one plugin per name
    rather than one aggregate called `local`. A child the layout excludes by
    name falls through to the unclaimed bucket rather than joining a component
    the product does not read it into.
    """
    posix = PurePosixPath(relative.replace("\\", "/"))
    candidates: list[Placed] = []
    claimed_by_directory = False
    for layout in _global_layouts(harness_id):
        role = _ROLE_OF.get(layout.component_type, layout.component_type)
        if layout.shape == "file":
            if str(posix) != layout.relative:
                continue
            if layout.declared_key:
                names = mcp_clients.declared_servers(place, layout.declared_key)
                if names:
                    candidates.append(
                        Placed(
                            layout.component_type,
                            role,
                            f"{layout.relative}#{layout.declared_key}",
                            declared_key=layout.declared_key,
                            entry_names=names,
                        )
                    )
                continue
            candidates.append(Placed(layout.component_type, role, layout.relative))
            continue
        if claimed_by_directory:
            continue
        prefix = PurePosixPath(layout.relative).parts
        if posix.parts[: len(prefix)] != prefix or len(posix.parts) <= len(prefix):
            continue
        child = posix.parts[len(prefix)]
        if child in layout.excluded_names:
            continue
        candidates.append(Placed(layout.component_type, role, f"{layout.relative}/{child}"))
        claimed_by_directory = True
    if candidates:
        return tuple(candidates)
    return (Placed("setting", "configuration", str(posix)),)


def _state_paths(harness_id: str) -> tuple[str, ...]:
    """Subtrees this harness writes state into, from the catalog that owns them."""
    definition = harness_catalog.BY_ID.get(harness_id)
    return () if definition is None else definition.state_paths


def _is_state(relative: str, state_paths: tuple[str, ...]) -> bool:
    """Whether a path inside the configuration root is runtime state.

    Matched on whole path segments so a declared `cache` never swallows a
    sibling named `cache-policy.toml`, and so an undeclared harness keeps
    every file it has today.
    """
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    for declared in state_paths:
        prefix = PurePosixPath(declared).parts
        if parts[: len(prefix)] == prefix:
            return True
    return False


def inspect(root: Path, *, harness_id: str) -> Inspection:
    """Read one native configuration. Writes nothing, anywhere.

    Files are visited in sorted order so two inspections of one tree produce one
    report. A file that cannot be read is reported as unreadable rather than
    skipped: "there were no secrets" and "nobody looked" must not be the same
    answer.

    Subtrees the harness writes state into are not read at all. A configuration
    root is also where a harness keeps session transcripts, job records and
    caches, and a real `~/.claude` offers 3800 job records against roughly 58
    files a person authored. A setup built from those would pin one machine's
    history as if it were shareable, and would read as drifted the moment the
    harness ran again. Which subtrees those are belongs to `harness_catalog`,
    the same owner the layouts come from.
    """
    resolved = root.resolve()
    if not resolved.is_dir():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "there is no configuration directory at that path",
            details={"root": str(root)},
        )

    state_paths = _state_paths(harness_id)
    findings: list[Finding] = []
    visited = 0
    # `os.walk` with `followlinks=False`, not `rglob`: `rglob` descends into a
    # symlinked directory as if it were the tree's own, which is exactly how
    # bytes from outside a capture root end up described as inside it. A
    # symlinked *file* is likewise refused below rather than read through.
    places: list[Path] = []
    for parent, directories, names in os.walk(resolved, followlinks=False):
        directories.sort()
        # A directory that is itself a link is pruned before descent; `walk`
        # with `followlinks=False` does not descend either, but pruning also
        # keeps it out of the walk's own bookkeeping.
        directories[:] = [
            name
            for name in directories
            if reading.classify_place(Path(parent) / name)[0] == reading.PLACE_DIRECTORY
        ]
        for name in sorted(names):
            places.append(Path(parent) / name)
    for place in places:
        if place.suffix.casefold() not in IMPORTABLE_SUFFIXES:
            continue
        relative = place.relative_to(resolved).as_posix()
        if _is_state(relative, state_paths):
            continue
        visited += 1
        if visited > MAX_INSPECTED_FILES:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "this tree holds more files than a configuration does",
                details={"root": str(root), "limit": str(MAX_INSPECTED_FILES)},
            )
        kind, _held = reading.classify_place(place)
        if kind in {reading.PLACE_LINK, reading.PLACE_HARDLINK, reading.PLACE_SPECIAL}:
            # Not read, and said so. A link reads bytes from outside the tree,
            # a second name can swap them after the fact, and a device node is
            # not configuration; each is reported rather than silently skipped
            # so a complete-capture registration can refuse over it.
            findings.append(Finding(path=relative, byte_length=0, digest="", refused=kind))
            continue
        if kind != reading.PLACE_REGULAR:
            continue
        # Ask how big it is before reading it. `REQ-841` requires an oversized
        # file to be read and hashed, and it still is — but "read" used to mean
        # "read into one `bytes` object", so a multi-gigabyte cache blob in a
        # harness root was allocated whole in order to discover that it would be
        # excluded. A real `~/.codex` holds exactly that shape of file.
        #
        # The evidence is unchanged: same digest, same length, same exclusion.
        # Only the memory is bounded.
        try:
            oversized_by_stat = place.stat().st_size > MAX_FILE_BYTES
            if oversized_by_stat:
                digest, length = content.address_of_file(place)
                findings.append(
                    Finding(path=relative, byte_length=length, digest=digest, oversized=True)
                )
                continue
            raw = place.read_bytes()
        except OSError as error:
            findings.append(
                Finding(path=relative, byte_length=0, digest="", unreadable=type(error).__name__)
            )
            continue
        # A file that grew past the bound between the stat and the read is
        # still oversized, and this is the branch that says so.
        if len(raw) > MAX_FILE_BYTES:
            # Read and hashed, so it is not unreadable. Harness roots carry
            # caches — a real `~/.codex` holds multi-megabyte catalogue blobs —
            # and calling those unreadable made every such root unimportable
            # while pointing the reader at a permission problem that does not
            # exist.
            findings.append(
                Finding(
                    path=relative,
                    byte_length=len(raw),
                    digest=content.address_of(raw),
                    oversized=True,
                )
            )
            continue

        suffix = place.suffix.casefold()
        _, names, scrub_format = _scrub_with_format(raw, suffix)
        findings.append(
            Finding(
                path=relative,
                byte_length=len(raw),
                digest=content.address_of(raw),
                redacted_keys=names,
                candidates=classify(harness_id, relative, place),
                scrub_format=scrub_format,
            )
        )
    return Inspection(root=str(resolved), harness_id=harness_id, findings=tuple(findings))


def scrub(raw: bytes, *, suffix: str = "") -> tuple[bytes, tuple[str, ...]]:
    """Remove credential values, returning the clean bytes and the key names.

    Structured documents are walked and rewritten in the format their name
    declares; anything else is returned untouched with nothing claimed about
    it. Guessing at the shape of an unstructured file would either miss a
    secret or mangle a document, and both are worse than saying the file was
    not rewritten — and the report says which files were which, per file.

    TOML goes through `tomlkit` so the rewrite keeps the comments a person
    wrote: losing them would damage a file this program did not author. JSONC
    and YAML come back as canonical JSON and YAML respectively — their comment
    grammar has no round-tripping writer here, and a redacted document that
    lost its comments still beats a faithful one that kept a token. The
    measured case this closes: a `config.toml` with
    `env = { TOKEN = "live" }` under `[mcp_servers.x]` used to pass through
    whole.
    """
    cleaned, names, _format = _scrub_with_format(raw, suffix)
    return cleaned, names


def _scrub_with_format(raw: bytes, suffix: str) -> tuple[bytes, tuple[str, ...], str]:
    """The scrub plus the honest answer of which rewrite actually happened.

    `none` means the bytes went through untouched — an unhandled format or a
    document that did not parse — and the per-file report carries it, so "this
    file was scanned" is a recorded fact rather than an implication.
    """
    folded = suffix.casefold()
    if folded == ".toml":
        return _scrub_toml(raw)
    if folded in {".yaml", ".yml"}:
        return _scrub_yaml(raw)
    if folded == ".jsonc":
        return _scrub_json(raw, jsonc=True)
    if folded in {"", ".json"}:
        return _scrub_json(raw)
    return raw, (), "none"


def _scrub_json(raw: bytes, *, jsonc: bool = False) -> tuple[bytes, tuple[str, ...], str]:
    try:
        text = raw.decode("utf-8")
        decoded: object = json.loads(mcp_clients.jsonc_source(text) if jsonc else text)
    except (ValueError, UnicodeDecodeError):
        return raw, (), "none"

    names: set[str] = set()
    cleaned = _walk(decoded, names)
    return (
        json.dumps(cleaned, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        tuple(sorted(names)),
        "jsonc" if jsonc else "json",
    )


def _scrub_toml(raw: bytes) -> tuple[bytes, tuple[str, ...], str]:
    """Rewrite a TOML document in place, keeping its comments and layout."""
    try:
        document = tomlkit.parse(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, tomlkit.exceptions.TOMLKitError):
        return raw, (), "none"
    names: set[str] = set()
    _walk_toml(document, names)
    return tomlkit.dumps(document).encode("utf-8"), tuple(sorted(names)), "toml"


def _walk_toml(container: object, names: set[str], prefix: str = "") -> None:
    """Rewrite one tomlkit container in place, the same rule as `_walk`."""
    if isinstance(container, dict):
        held = cast("dict[str, object]", container)
        for key in list(held.keys()):
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            value = held[name]
            if is_secret_key(name):
                names.add(path)
                held[name] = REDACTED
                continue
            if _fold_key(name) in ENVIRONMENT_MAPS and isinstance(value, dict):
                block = cast("dict[str, object]", value)
                for variable in list(block.keys()):
                    names.add(f"{path}.{variable}")
                    block[str(variable)] = REDACTED
                continue
            _walk_toml(value, names, path)
        return
    if isinstance(container, list):
        for item in cast("list[object]", container):
            _walk_toml(item, names, f"{prefix}[]")


def _scrub_yaml(raw: bytes) -> tuple[bytes, tuple[str, ...], str]:
    """Rewrite a YAML document as canonical safe YAML, values removed.

    `safe_load` only: a YAML file in a harness root is data, and a loader that
    can construct objects would be running the file rather than reading it.
    """
    try:
        decoded: object = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError):
        return raw, (), "none"
    if not isinstance(decoded, dict | list):
        return raw, (), "none"
    names: set[str] = set()
    cleaned = _walk(cast(object, decoded), names)
    return (
        yaml.safe_dump(cleaned, allow_unicode=True, sort_keys=True).encode("utf-8"),
        tuple(sorted(names)),
        "yaml",
    )


_CAMEL_BOUNDARY: Final = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _fold_key(name: str) -> str:
    """One spelling for a key name, so an exact comparison can be exact.

    `accessToken`, `access-token` and `Access_Token` are the same name written
    three ways, and a set membership test sees three different strings unless
    they are folded first.
    """
    return _CAMEL_BOUNDARY.sub("_", name).casefold().replace("-", "_")


def is_secret_key(name: str) -> bool:
    """Whether a key's *name* says its value is a credential.

    By name, and the report says so. The alternative is guessing from the shape
    of the value, which calls a project identifier a secret and misses a
    password stored under `value` — a confident wrong answer where an honest
    partial one was available.

    The comparison is exact against `SECRET_KEYS`, so the name has to be folded
    into the same shape first. `-` and camel case are both word boundaries in
    the wild: Claude Code stores its OAuth tokens as `accessToken` and
    `refreshToken`, which matched nothing while the set held `access_token`.
    """
    folded = _fold_key(name)
    return folded in SECRET_KEYS or folded.rsplit(".", 1)[-1] in SECRET_KEYS


def record_backup(
    connection: sqlite3.Connection,
    *,
    harness_id: str,
    target_id: str,
    provider_ref: str,
    at: str,
) -> BackupRef:
    """Record where the provider put the old bytes (`REQ-807`, `REQ-814`).

    A reference, never the bytes. Copying them would give one recovery two
    owners, and the provider's is the one that can actually restore.
    """
    if not provider_ref:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "an import needs the provider's backup reference before anything is registered",
            details={"harness_id": harness_id},
            # A command, not a sentence. `next_actions` is read by an agent that
            # runs what it finds there, and "run the provider's backup command"
            # is advice it has no way to follow.
            next_actions=["setup import register ... --backup-ref <ref from the provider> --json"],
        )
    if not protocol_v3.BACKUP_REF_PATTERN.fullmatch(provider_ref):
        # The vendored kit's own shape. A reference is checked for form here
        # and for existence nowhere yet — recording a typo would write a
        # recovery path no provider will ever answer for, and the passport
        # below says `recorded_unverified` precisely because form is all this
        # proves.
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that is not the shape of a provider backup reference",
            details={"expected": protocol_v3.BACKUP_REF_PATTERN.pattern},
            next_actions=["setup import register --backup-ref slot-<twelve digits> ... --json"],
        )
    backup_id = new_id("backup")
    connection.execute(
        """
        INSERT INTO backup_ref (backup_id, harness_id, target_id, provider_ref, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (backup_id, harness_id, target_id, provider_ref, at),
    )
    return BackupRef(backup_id, harness_id, target_id, provider_ref, at)


def backup(connection: sqlite3.Connection, backup_id: str) -> BackupRef | None:
    row = connection.execute(
        "SELECT * FROM backup_ref WHERE backup_id = ?", (backup_id,)
    ).fetchone()
    if row is None:
        return None
    return BackupRef(
        backup_id=str(row["backup_id"]),
        harness_id=str(row["harness_id"]),
        target_id=str(row["target_id"]),
        provider_ref=str(row["provider_ref"]),
        created_at=str(row["created_at"]),
    )


def register(
    connection: sqlite3.Connection,
    inspection: Inspection,
    *,
    backup_id: str,
    owner_id: str,
    device_id: str,
    at: str,
    plan_digest: str = "",
    components: list[dict[str, JsonValue]] | None = None,
    operation_id: str | None = None,
    partial: bool = False,
    harness_version: str = "",
) -> Imported:
    """Register the inspected configuration as the user's own setup.

    Everything or nothing: the passport, its exact file hashes and its
    provenance are one transaction, because a setup recorded without the hashes
    it was made from is a setup nobody can verify against its source.

    Complete by default. A registration that quietly left files out — an
    oversized cache, a refused link — would present itself as the working
    configuration while describing part of one. `partial=True` is the caller
    saying so out loud, and the passport then records the mode and what was
    left out, so the incompleteness travels with the object rather than with
    the operator's memory.

    The backup must already exist. `REQ-813` puts the provider's backup before
    registration, and taking a reference to something that was never made would
    record a recovery path that does not exist.
    """
    held = backup(connection, backup_id)
    if held is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no backup with that identifier was recorded",
            details={"backup_id": backup_id},
        )
    if held.harness_id != inspection.harness_id:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that backup is for another harness",
            details={"backup": held.harness_id, "inspection": inspection.harness_id},
        )
    if not inspection.findings:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "there is nothing to import from an empty configuration",
            details={"root": inspection.root},
        )
    unreadable = inspection.unreadable
    if unreadable:
        # A setup registered from files nobody could read would claim to
        # describe a configuration it has not seen.
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "some files could not be read, so this configuration is not fully described",
            details={"unreadable": ", ".join(unreadable)},
        )
    left_out = inspection.skipped
    if left_out and not partial:
        # Oversized files and refused links were seen and deliberately not
        # captured. Registering over them by default would present part of a
        # configuration as the whole of one; the operator says `partial` out
        # loud, and the passport records it.
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this capture leaves files out, and a complete one was asked for",
            details={"skipped": ", ".join(left_out)},
            next_actions=[
                "setup import register --partial "
                f"--root {inspection.root} --harness {inspection.harness_id} ... --json"
            ],
        )

    own_operation = operation_id is None
    if operation_id is None:
        operation_id = journal.begin(connection, "setup.import", at)
    try:
        with transaction(connection):
            stable_id = new_id("setup")
            stored = revisions.commit(
                connection,
                _graph_content(
                    inspection,
                    stable_id,
                    held,
                    owner_id,
                    plan_digest,
                    components or [],
                    at,
                    partial=partial,
                    harness_version=harness_version,
                )
                if plan_digest
                else _content(
                    inspection,
                    stable_id,
                    held,
                    owner_id,
                    at,
                    partial=partial,
                    harness_version=harness_version,
                ),
                device_id=device_id,
                operation_id=operation_id,
            )
    except BaseException as error:
        if own_operation:
            journal.settle(connection, operation_id, "failed", at, type(error).__name__)
        raise
    if own_operation:
        journal.settle(connection, operation_id, "verified", at)
    return Imported(stable_id=stable_id, revision_id=stored.revision_id, backup_id=backup_id)


def register_graph(
    connection: sqlite3.Connection,
    inspection: Inspection,
    *,
    expected_plan_digest: str,
    target_id: str,
    provider_ref: str,
    owner_id: str,
    device_id: str,
    at: str,
    partial: bool = False,
    harness_version: str = "",
) -> Imported:
    """Atomically materialize the exact confirmed import plan.

    The plan is rebuilt from the second inspection supplied by the command.
    Confirmation therefore applies only while every observed byte still has
    the digest the user reviewed. Backup identity, component artifacts,
    component passports and the setup graph commit together or not at all.
    """
    proposed = plan(inspection)
    if proposed.plan_digest != expected_plan_digest:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the native configuration changed after the import plan was reviewed",
            details={"expected": expected_plan_digest, "found": proposed.plan_digest},
            next_actions=[
                "setup import plan "
                f"--root {inspection.root} --harness {inspection.harness_id} --json"
            ],
        )
    # Idempotent replay before any effect. A client that dies after the commit
    # and before the answer retries the same confirmed digest; without this,
    # five kill-and-retry rounds registered four complete setups for one
    # directory. The plan digest binds root, inventory and decomposition, so a
    # graph recorded under it *is* this registration's outcome.
    already = _already_registered(connection, expected_plan_digest)
    if already is not None:
        return already
    if proposed.blocked_by:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the confirmed import plan still has blocking files",
            details={"blocked_by": ", ".join(proposed.blocked_by)},
        )
    if not proposed.components:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "there are no component drafts in this import plan",
            details={"root": inspection.root},
        )

    operation_id = journal.begin(connection, "setup.import.graph", at)
    try:
        with transaction(connection):
            held = record_backup(
                connection,
                harness_id=inspection.harness_id,
                target_id=target_id,
                provider_ref=provider_ref,
                at=at,
            )
            components: list[dict[str, JsonValue]] = []
            component_ids: list[str] = []
            by_path = {item.path: item for item in inspection.findings}
            root = Path(inspection.root)
            for candidate in proposed.components:
                artifact_bytes, content_format, source_name = _package(
                    root, candidate, {path: item.digest for path, item in by_path.items()}
                )
                artifact = content.put(connection, artifact_bytes, at=at)
                component_id = new_id("component")
                stored = revisions.commit(
                    connection,
                    _component_content(
                        inspection,
                        candidate,
                        component_id,
                        artifact.digest,
                        artifact.byte_length,
                        owner_id,
                        at,
                        content_format=content_format,
                        source_name=source_name,
                    ),
                    device_id=device_id,
                    operation_id=operation_id,
                )
                component_ids.append(component_id)
                components.append(
                    {
                        "stable_id": component_id,
                        "revision_id": stored.revision_id,
                        "candidate_id": candidate.candidate_id,
                        "artifact_digest": artifact.digest,
                    }
                )

            imported = register(
                connection,
                inspection,
                backup_id=held.backup_id,
                owner_id=owner_id,
                device_id=device_id,
                at=at,
                plan_digest=proposed.plan_digest,
                components=components,
                operation_id=operation_id,
                partial=partial,
                harness_version=harness_version,
            )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", at, type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", at)
    return Imported(
        stable_id=imported.stable_id,
        revision_id=imported.revision_id,
        backup_id=held.backup_id,
        plan_digest=proposed.plan_digest,
        component_ids=tuple(component_ids),
    )


def _already_registered(connection: sqlite3.Connection, plan_digest: str) -> Imported | None:
    """The graph a previous run of this exact confirmed plan already created.

    Read from the setup passports themselves: the revision records the plan
    digest, the component ids and the backup, which is everything the original
    answer carried. A linear scan over local setup revisions is fine — the
    table is small and the alternative is a second index for one replay path.
    """
    rows = connection.execute(
        "SELECT revision_id, content FROM revision WHERE stable_id LIKE 'setup_%'"
    ).fetchall()

    def value_of(facts: dict[str, JsonValue], name: str) -> JsonValue:
        fact = facts.get(name)
        if not isinstance(fact, dict):
            return None
        return cast(dict[str, JsonValue], fact).get("value")

    for row in rows:
        document = cast(dict[str, JsonValue], json.loads(str(row["content"])))
        facts = cast(dict[str, JsonValue], document.get("facts") or {})
        if value_of(facts, "plan_digest") != plan_digest:
            continue
        members = value_of(facts, "components")
        listed = cast(list[JsonValue], members) if isinstance(members, list) else []
        return Imported(
            stable_id=str(document["stable_id"]),
            revision_id=str(row["revision_id"]),
            backup_id=str(value_of(facts, "backup_id") or ""),
            plan_digest=plan_digest,
            component_ids=tuple(
                str(cast(dict[str, JsonValue], item).get("stable_id", ""))
                for item in listed
                if isinstance(item, dict)
            ),
        )
    return None


def _reread(root: Path, relative: str, expected_digest: str) -> tuple[bytes, int]:
    """The registration-time read: no link followed, no substitution accepted.

    Inspection classified this path as a regular file; registration reads it
    again through the shared discipline — `O_NOFOLLOW`, an inode re-check, a
    bound — and then demands the bytes still hash to what the reviewed plan
    recorded. A path that became a link, gained a second name, or changed
    content between the two reads is a conflict, not an input.
    """
    place = root / relative
    kind, held = reading.classify_place(place)
    if kind != reading.PLACE_REGULAR or held is None:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "a native file changed shape while the import was being registered",
            details={"path": relative, "found": kind},
            next_actions=["setup import plan --root <root> --harness <harness> --json"],
        )
    raw = reading.read_regular(place, held, limit=MAX_FILE_BYTES, subject="import")
    if content.address_of(raw) != expected_digest:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "a native file changed while the import was being registered",
            details={"path": relative},
            next_actions=["setup import plan --root <root> --harness <harness> --json"],
        )
    return raw, 0o755 if stat.S_IMODE(held.st_mode) & 0o111 else 0o644


def _package(
    root: Path, candidate: ProposedComponent, digests: dict[str, str]
) -> tuple[bytes, str, str]:
    """The component's artifact in the format adoption would have stored.

    Three shapes, one owner each. A contribution carries the key's value,
    scrubbed in the host's format (`ADR-0129`). A single file carries its
    scrubbed bytes. A directory is sealed through the same tree encoder
    adoption uses, with every member relative to the component boundary.

    The envelope this replaced kept every member at its harness-root-relative
    path, so a file-shaped component reached the compiler as a named member
    and a directory-shaped one re-rooted under itself — a path stored without
    the root it was relative to, and the last link the capture round-trip was
    missing (`#63`). Returns the bytes, their format and the component's name.
    """
    boundary = candidate.boundary
    if candidate.declared_key:
        relative = candidate.paths[0]
        raw, _mode = _reread(root, relative, digests[relative])
        from ai_stp_cli.local import contribution

        host = Path(relative).name
        value = contribution.extract_value(host=host, content=raw, key=candidate.declared_key)
        value_suffix = ".toml" if PurePosixPath(host).suffix.casefold() == ".toml" else ".json"
        cleaned, _names = scrub(value, suffix=value_suffix)
        return cleaned, components.COMPONENT_FILE_FORMAT, host
    name = PurePosixPath(boundary).name
    if len(candidate.paths) == 1 and candidate.paths[0] == boundary:
        raw, _mode = _reread(root, boundary, digests[boundary])
        cleaned, _names = scrub(raw, suffix=PurePosixPath(boundary).suffix)
        return cleaned, components.COMPONENT_FILE_FORMAT, name
    prefix = f"{boundary}/"
    files: list[components.ComponentFile] = []
    for relative in candidate.paths:
        if not relative.startswith(prefix):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "an import member lies outside its component boundary",
                details={"path": relative, "boundary": boundary},
            )
        raw, mode = _reread(root, relative, digests[relative])
        cleaned, _names = scrub(raw, suffix=PurePosixPath(relative).suffix)
        files.append(components.ComponentFile(relative[len(prefix) :], cleaned, mode))
    return (
        components.encode_tree_artifact(files, root / boundary),
        components.COMPONENT_TREE_FORMAT,
        name,
    )


def _component_content(
    inspection: Inspection,
    candidate: ProposedComponent,
    stable_id: str,
    artifact_digest: str,
    artifact_size: int,
    owner_id: str,
    at: str,
    *,
    content_format: str,
    source_name: str,
) -> dict[str, JsonValue]:
    facts = {
        "component_type": _fact(candidate.component_type, at),
        "native_role": _fact(candidate.native_role, at),
        "harness_id": _fact(inspection.harness_id, at),
        # Global by construction: an import inspects one configuration root,
        # which is the global scope's. Project trees come through `component
        # discover`, which reads scope from the same catalogue.
        "scope": _fact("global", at),
        # The `~`-relative spelling, never the absolute one: an absolute root
        # is one machine's identity, and this passport is a revision that can
        # travel. The exact absolute path stays in the command's own output.
        "source_root": _fact(redact_any_home(Path(inspection.root)), at),
        "source_paths": _fact(list(candidate.paths), at),
        "candidate_id": _fact(candidate.candidate_id, at),
        "file_set_digest": _fact(candidate.file_set_digest, at),
        "boundary": _fact(candidate.boundary, at),
        # The same three facts adoption records, so the compiler names the
        # component's root and checks its projection the same way for both
        # capture paths.
        "source_name": _fact(source_name, at),
        "content_format": _fact(content_format, at),
        "content_digest": _fact(artifact_digest, at),
        "byte_length": _fact(artifact_size, at),
    }
    managed = (
        ()
        if candidate.declared_key
        else composition.covers(candidate.component_type, inspection.harness_id, source_name)
    )
    if managed:
        facts["managed_paths"] = _fact(list(managed), at)
    if candidate.declared_key:
        # A contribution's identity is what it declares, not what it sits in:
        # the entry names are the native identifiers, and the locator names the
        # exact key of the exact host file the value came from.
        facts["declared_key"] = _fact(candidate.declared_key, at)
        facts["native_ids"] = _fact(list(candidate.entry_names), at)
        facts["source_locator"] = _fact(f"{candidate.paths[0]}#{candidate.declared_key}", at)
    return {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": facts,
    }


def _graph_content(
    inspection: Inspection,
    stable_id: str,
    held: BackupRef,
    owner_id: str,
    plan_digest: str,
    components: list[dict[str, JsonValue]],
    at: str,
    *,
    partial: bool = False,
    harness_version: str = "",
) -> dict[str, JsonValue]:
    document = _content(
        inspection, stable_id, held, owner_id, at, partial=partial, harness_version=harness_version
    )
    facts = cast(dict[str, JsonValue], document["facts"])
    facts["plan_digest"] = _fact(plan_digest, at)
    facts["components"] = _fact(cast(list[JsonValue], components), at)
    return document


def _content(
    inspection: Inspection,
    stable_id: str,
    held: BackupRef,
    owner_id: str,
    at: str,
    *,
    partial: bool = False,
    harness_version: str = "",
) -> dict[str, JsonValue]:
    """The imported setup's passport, built by naming every field it may hold.

    A whitelist and not a filter: the one thing this passport must never carry
    is a secret value, and a filter has to be right about every field somebody
    adds later.
    """
    files: list[JsonValue] = [
        {"path": item.path, "digest": item.digest, "byte_length": item.byte_length}
        for item in inspection.findings
    ]
    facts: dict[str, JsonValue] = {
        "harness_id": _fact(inspection.harness_id, at),
        "origin": _fact("imported", at),
        # Provenance: where these bytes came from, so the setup can be checked
        # against its source rather than taken on trust. The `~`-relative
        # spelling: an absolute root is one machine's identity, and a passport
        # travels.
        "source_root": _fact(redact_any_home(Path(inspection.root)), at),
        "files": _fact(files, at),
        # A reference to a separate object (`REQ-814`), never its identity.
        "backup_id": _fact(held.backup_id, at),
        # `REQ-815`: names, and only names.
        "redacted_keys": _fact(list(inspection.redacted_keys), at),
        "detection_rule": _fact(inspection.detection_rule, at),
        # Form-checked against the kit's own pattern and taken from the
        # operator; no provider was asked whether it exists. The value changes
        # to `provider_status` only when a status read actually confirms the
        # reference — a passport must not claim a verification nobody ran.
        "backup_verification": _fact("recorded_unverified", at),
        # Whether this snapshot claims to be the whole configuration. A partial
        # one names what it left out, so the incompleteness travels with the
        # object rather than with the operator's memory.
        "capture_mode": _fact("partial" if partial else "complete", at),
        # The exact instrument, always, and the harness build when one was
        # detectable: a captured setup without the versions it was captured
        # against cannot answer later whether it still applies. An empty
        # harness version is a statement — the tree was imported on a machine
        # where that harness did not answer — not an omission.
        "capture_tool_version": _fact(f"ai-stp-cli={_cli_version()}", at),
        "harness_version": _fact(harness_version, at),
    }
    if partial:
        facts["excluded_paths"] = _fact(list(inspection.skipped), at)
    return {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": at,
        # Private, always. An imported setup is somebody's working machine and
        # publishing it is a separate decision nobody has made here.
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": facts,
    }


#: Maps whose keys are environment variable names, so every value inside is an
#: environment variable's value. `REQ-815` lets an imported setup carry those
#: *names* and nothing else, which makes the whole map a value rule rather than
#: a name rule.
#:
#: Measured on 2026-08-29: an MCP configuration with
#: `"env": {"GITHUB_TOKEN": "ghp_…"}` came back from `scrub` untouched. The
#: neighbouring `Authorization` was redacted because that word is in
#: `SECRET_KEYS`; `GITHUB_TOKEN` is not, and the comparison is exact against a
#: folded key rather than a substring — deliberately, because substrings call a
#: `tokenizer` a credential. The platform's safety scanner had the same hole
#: and closing it there did not close it here.
#:
#: A longer word list would be the wrong repair: it has to be right about every
#: name a vendor invents next. The contract already says what travels.
ENVIRONMENT_MAPS: Final[frozenset[str]] = frozenset({"env", "environment"})


def _walk(value: object, names: set[str], prefix: str = "") -> JsonValue:
    """Rewrite a decoded document, removing values under credential keys."""
    if isinstance(value, dict):
        cleaned: dict[str, JsonValue] = {}
        for key, item in cast(dict[object, object], value).items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            if is_secret_key(name):
                names.add(path)
                cleaned[name] = REDACTED
                continue
            if _fold_key(name) in ENVIRONMENT_MAPS and isinstance(item, dict):
                cleaned[name] = _environment(cast(dict[object, object], item), names, path)
                continue
            cleaned[name] = _walk(item, names, path)
        return cleaned
    if isinstance(value, list):
        held = cast(list[object], value)
        return [_walk(item, names, f"{prefix}[]") for item in held]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _environment(block: dict[object, object], names: set[str], prefix: str) -> JsonValue:
    """Keep every variable name; keep no value at all.

    Not "redact the ones that look like credentials". A scrubber that decides
    which environment values are harmless is guessing at exactly the point where
    it must not, and `MODEL=sonnet` costs nothing to lose while one wrong guess
    writes a live token into the registry.
    """
    kept: dict[str, JsonValue] = {}
    for key, _value in block.items():
        variable = str(key)
        names.add(f"{prefix}.{variable}")
        kept[variable] = REDACTED
    return kept


def _cli_version() -> str:
    from ai_stp_cli.runtime import cli_version

    return cli_version()


def _fact(value: JsonValue, at: str) -> JsonValue:
    return {"value": value, "origin": "observed", "confirmation": "none", "observed_at": at}
