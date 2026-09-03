"""The deterministic harness bundle (`#167`, `harness-bundle.md`).

One canonical input produces one bundle, one manifest and one digest. Nothing
that varies between machines reaches the hashed content: not the build time, not
a local path, not the order a directory happened to be read in. That is why the
digest can be compared across operating systems at all — the property is a
consequence of what goes in, not of running the same code twice.

**The bundle is compiled, never written to a target.** `ADR-0012` gives the
final write to the provider alone, so nothing here touches a harness
configuration. This produces bytes and a manifest; installing them is a separate
plan with its own confirmation.

**Every path is rejected or normalised, never repaired.** A path that escapes,
repeats or differs only by case is refused with its own code. Silently
normalising one would resolve a collision by picking a winner, and picking a
winner is what `REQ-626` forbids the builder from doing.

**A link is not a file.** A symlink, a hard link and a device node all describe
something outside the bundle, and `harness-bundle.md` rejects them by name. They
are refused on their kind rather than on where they point, because where they
point can change between reading and installing. The kind arrives with the
source rather than being derived here: a symlink and the file it points at have
the same bytes, so a reader that lost the distinction would bundle the target as
though the link were a file.
"""

import hashlib
import io
import unicodedata
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from ai_stp_cli.local import composition
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_canonical

#: The bundle's own hash domain (`canonical-data.md`).
BUNDLE_DOMAIN: Final[str] = "ai-stp:bundle:v1"
PASSPORT_DOMAIN: Final[str] = "ai-stp:passport:v1"

#: The compiler's version, recorded in every manifest. A bundle that cannot say
#: which builder made it cannot be reproduced on purpose.
BUILDER_VERSION: Final[str] = "1.0"

#: The exact container syntax understood by a provider. The logical bundle
#: schema and the ZIP container are versioned together: changing entry names,
#: ordering or metadata changes the format rather than silently changing v1.
BUNDLE_FORMAT: Final[Literal["ai-stp-bundle/1"]] = "ai-stp-bundle/1"
BUNDLE_FORMAT_V2: Final[Literal["ai-stp-bundle/2"]] = "ai-stp-bundle/2"

#: ZIP has no timestamp-free representation. This oldest representable value is
#: fixed by the format and never taken from the host clock.
ZIP_TIMESTAMP: Final[tuple[int, int, int, int, int, int]] = (1980, 1, 1, 0, 0, 0)

#: The provider protocol this bundle is shaped for. Frozen by `#169`; declared
#: here so a provider can refuse a bundle from a future one rather than
#: misreading it.
PROTOCOL_VERSION: Final[int] = 1

#: Every refusal the compiler can produce, closed by `harness-bundle.md`.
REFUSALS: Final[frozenset[str]] = frozenset(
    {
        "path_not_relative",
        "path_escapes_target",
        "path_empty_segment",
        "path_invalid_character",
        "path_too_long",
        "path_not_portable",
        "path_duplicate",
        "path_case_conflict",
        "path_undeclared",
        "declared_path_absent",
        "link_not_allowed",
        "special_file_not_allowed",
        "mode_not_allowed",
        "secret_in_bundle",
        "file_too_large",
        "bundle_too_large",
        "too_many_files",
        "setup_passport_mismatch",
        "adaptation_binding_missing",
        "adaptation_binding_mismatch",
        "projection_profile_mismatch",
    }
)

#: The two modes a bundled file may carry. A file is readable, or readable and
#: executable; anything else — setuid, group-writable, world-writable — is a
#: permission decision the bundle has no business making.
MODE_FILE: Final[int] = 0o644
MODE_EXECUTABLE: Final[int] = 0o755
ALLOWED_MODES: Final[frozenset[int]] = frozenset({MODE_FILE, MODE_EXECUTABLE})

#: Resource limits, declared and returned so a bundle that reached one is
#: distinguishable from a complete one.
MAX_FILES: Final[int] = 2000
MAX_FILE_BYTES: Final[int] = 4 * 1024 * 1024
MAX_BUNDLE_BYTES: Final[int] = 64 * 1024 * 1024
MAX_PATH_BYTES: Final[int] = 1024
MAX_SEGMENT_BYTES: Final[int] = 255

#: What a file name says about holding a credential. Decided by name only —
#: opening a file to find out is the harm the rule exists to prevent — and
#: shared in spirit with the project index, which refuses the same names.
SECRET_NAMES: Final[frozenset[str]] = frozenset(
    {".env", ".netrc", ".npmrc", "credentials", "id_rsa", "id_ed25519", ".pgpass"}
)
SECRET_PREFIXES: Final[tuple[str, ...]] = (".env.",)
SECRET_SUFFIXES: Final[tuple[str, ...]] = (".pem", ".key", ".p12", ".pfx", ".keystore")

KIND_FILE: Final[str] = "file"
KIND_SYMLINK: Final[str] = "symlink"
KIND_HARDLINK: Final[str] = "hardlink"
KIND_DIRECTORY: Final[str] = "directory"
KIND_SPECIAL: Final[str] = "special"


@dataclass(frozen=True)
class Source:
    """One thing offered for the bundle, and what it actually is.

    `kind` is carried rather than inferred from the bytes, because a symlink and
    the file it points at have the same bytes and completely different
    consequences. A reader that lost the distinction would bundle the target of
    a link as though the link were a file.
    """

    path: str
    content: bytes
    owner: str
    kind: str = KIND_FILE
    mode: int = MODE_FILE


@dataclass(frozen=True)
class FileEntry:
    """One record in the file manifest."""

    path: str
    digest: str
    byte_length: int
    mode: int
    owner: str

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "path": self.path,
            "digest": self.digest,
            "byte_length": self.byte_length,
            "mode": self.mode,
            "owner": self.owner,
        }


@dataclass(frozen=True)
class ProjectionProfileBinding:
    """Exact provider surface selected before one v2 bundle is compiled."""

    profile_id: str
    profile_digest: str
    target_scope: str

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "profile_id": self.profile_id,
            "profile_digest": self.profile_digest,
            "target_scope": self.target_scope,
        }


@dataclass(frozen=True)
class ComponentAdaptationBinding:
    """One component passport's exact adaptation atom carried into bundle v2."""

    stable_id: str
    version: str
    passport_digest: str
    adaptation_id: str
    projection_artifact_digest: str
    projection_artifact_size: int
    provider_component_kind: str
    projection_kind: str
    member_paths: tuple[str, ...]

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "stable_id": self.stable_id,
            "version": self.version,
            "passport_digest": self.passport_digest,
            "adaptation_id": self.adaptation_id,
            "projection_artifact": {
                "digest": self.projection_artifact_digest,
                "size_bytes": self.projection_artifact_size,
            },
            "provider_component_kind": self.provider_component_kind,
            "projection_kind": self.projection_kind,
            "member_paths": list(self.member_paths),
        }


@dataclass(frozen=True)
class Refusal:
    """One reason this bundle cannot be compiled."""

    code: str
    summary: str
    details: dict[str, str]


@dataclass(frozen=True)
class Bundle:
    """A compiled bundle: exact archive bytes, manifest and two digests.

    ``digest`` is the domain-separated logical identity carried in
    ``bundle.json``. ``artifact_digest`` hashes the literal ZIP bytes a provider
    receives. Both are required: the first is stable object identity, while the
    second detects any change to the container itself.
    """

    manifest: dict[str, JsonValue]
    files: tuple[FileEntry, ...]
    digest: str
    archive: bytes
    artifact_digest: str
    refusals: tuple[Refusal, ...]

    @property
    def compiled(self) -> bool:
        return not self.refusals


def normalise(path: str) -> str:
    """One spelling of one path: NFC, forward slashes, no trailing separator.

    Unicode first, because two spellings of one accented name are one path on a
    macOS filesystem and two on a Linux one. Normalising them apart would make
    the same bundle collide on one machine and not on the other.
    """
    return unicodedata.normalize("NFC", path.replace("\\", "/")).rstrip("/")


def compile_bundle(
    sources: tuple[Source, ...],
    *,
    setup_stable_id: str,
    setup_version: str,
    setup_digest: str,
    harness_id: str,
    declared_paths: frozenset[str],
    setup_passport: JsonValue,
    composition_report: JsonValue,
    conversion_report: JsonValue,
    input_digest: str,
    target_scope: str = "global",
    bundle_format: str = BUNDLE_FORMAT,
    projection_profile: ProjectionProfileBinding | None = None,
    adaptation_bindings: tuple[ComponentAdaptationBinding, ...] = (),
) -> Bundle:
    """Compile one bundle, or refuse with every reason it cannot be compiled.

    The digest covers the manifest, which covers every file by content. Build
    time and local paths are absent by construction rather than filtered out: a
    filter has to be right about every field somebody adds later, and a manifest
    built by naming its fields cannot carry one nobody listed.
    """
    refusals: list[Refusal] = []
    entries: list[FileEntry] = []
    accepted: list[Source] = []
    seen: dict[str, str] = {}
    folded: dict[str, str] = {}
    total = 0

    if bundle_format == BUNDLE_FORMAT_V2:
        if projection_profile is None or not adaptation_bindings:
            refusals.append(
                _refuse(
                    "adaptation_binding_missing",
                    "bundle v2 requires one profile and every component adaptation binding",
                    "bundle.json",
                    setup_stable_id,
                )
            )
        elif projection_profile.target_scope != target_scope:
            refusals.append(
                _refuse(
                    "projection_profile_mismatch",
                    "the selected profile scope differs from the bundle target scope",
                    "bundle.json",
                    setup_stable_id,
                )
            )
    elif bundle_format != BUNDLE_FORMAT:
        refusals.append(
            _refuse(
                "projection_profile_mismatch",
                "the requested bundle format is unsupported",
                "bundle.json",
                setup_stable_id,
            )
        )

    passport_digest = digest_canonical(PASSPORT_DOMAIN, setup_passport)
    passport_stable_id = (
        str(setup_passport.get("stable_id") or "") if isinstance(setup_passport, dict) else ""
    )
    if passport_digest != setup_digest or passport_stable_id != setup_stable_id:
        refusals.append(
            _refuse(
                "setup_passport_mismatch",
                "the SetupVersion passport does not match its exact reference",
                "setup-passport.json",
                setup_stable_id,
                {
                    "expected_digest": setup_digest,
                    "observed_digest": passport_digest,
                    "observed_stable_id": passport_stable_id,
                },
            )
        )

    for source in sorted(sources, key=lambda item: (normalise(item.path), item.owner)):
        path = normalise(source.path)
        problem = _path_problem(path)
        if problem is not None:
            refusals.append(_refuse(problem[0], problem[1], path, source.owner))
            continue
        if source.kind in {KIND_SYMLINK, KIND_HARDLINK, KIND_DIRECTORY}:
            refusals.append(
                _refuse(
                    "link_not_allowed",
                    "a link or directory entry cannot be a bundled file",
                    path,
                    source.owner,
                )
            )
            continue
        if source.kind != KIND_FILE:
            refusals.append(
                _refuse(
                    "special_file_not_allowed",
                    "a device, socket or pipe cannot be a bundled file",
                    path,
                    source.owner,
                )
            )
            continue
        if _is_secret(path):
            refusals.append(
                _refuse(
                    "secret_in_bundle",
                    "this name says the file holds a credential",
                    path,
                    source.owner,
                )
            )
            continue
        if source.mode not in ALLOWED_MODES:
            refusals.append(
                _refuse(
                    "mode_not_allowed",
                    "a bundled file is readable or readable and executable, nothing else",
                    path,
                    source.owner,
                    {"mode": oct(source.mode)},
                )
            )
            continue
        if path in seen:
            refusals.append(
                _refuse(
                    "path_duplicate",
                    "two files normalise to the same path",
                    path,
                    source.owner,
                    {"also": seen[path]},
                )
            )
            continue
        lowered = path.casefold()
        if lowered in folded:
            # A case-insensitive filesystem would collapse these into one file
            # and install whichever arrived last. Refusing keeps the bundle
            # meaning the same thing on every machine.
            refusals.append(
                _refuse(
                    "path_case_conflict",
                    "two paths differ only by case and would collide",
                    path,
                    source.owner,
                    {"also": folded[lowered]},
                )
            )
            continue
        if declared_paths and not any(
            composition.path_covers(root, path) for root in declared_paths
        ):
            refusals.append(
                _refuse(
                    "path_undeclared",
                    "this path is not among the composition's managed paths",
                    path,
                    source.owner,
                )
            )
            continue
        if len(source.content) > MAX_FILE_BYTES:
            refusals.append(
                _refuse(
                    "file_too_large",
                    "this file is larger than the declared bound",
                    path,
                    source.owner,
                    {"limit": str(MAX_FILE_BYTES)},
                )
            )
            continue

        total += len(source.content)
        if total > MAX_BUNDLE_BYTES:
            refusals.append(
                _refuse(
                    "bundle_too_large",
                    "this bundle is larger than the declared bound",
                    path,
                    source.owner,
                    {"limit": str(MAX_BUNDLE_BYTES)},
                )
            )
            continue
        if len(entries) >= MAX_FILES:
            refusals.append(
                _refuse(
                    "too_many_files",
                    "this bundle holds more files than the declared bound",
                    path,
                    source.owner,
                    {"limit": str(MAX_FILES)},
                )
            )
            continue

        seen[path] = source.owner
        folded[lowered] = path
        entries.append(
            FileEntry(
                path=path,
                digest=f"sha256:{hashlib.sha256(source.content).hexdigest()}",
                byte_length=len(source.content),
                mode=source.mode,
                owner=source.owner,
            )
        )
        accepted.append(
            Source(path=path, content=source.content, owner=source.owner, mode=source.mode)
        )

    # The other direction, which nothing asked until a hook shipped without its
    # handler. `path_undeclared` above refuses a file that arrived and was not
    # declared; a path that was **declared and did not arrive** produced no
    # entry, so no iteration of that loop ever saw it and nothing noticed.
    #
    # Measured on Windows against antigravity: a passport declaring
    # `config/hooks.json` and `config/hooks/h01.py` released, composed and
    # planned, and the plan emitted `write the 1 declared files`. The provider
    # reported the install verified — correctly, because it wrote everything the
    # bundle held. The bundle was what had been quietly weakened, and the
    # installed hook could not execute.
    #
    # A one-sided check is the shape this estate keeps finding: the assertion
    # that a set has nothing extra says nothing about it being complete.
    held_paths = {item.path for item in entries}
    absent = (
        sorted(
            root
            for root in declared_paths
            if not any(composition.path_covers(root, path) for path in held_paths)
        )
        if declared_paths
        else []
    )
    for path in absent:
        refusals.append(
            _refuse(
                "declared_path_absent",
                "the composition declares this managed path and no source carries it",
                path,
                seen.get(path, ""),
            )
        )

    if bundle_format == BUNDLE_FORMAT_V2 and adaptation_bindings:
        bound_owners = {binding.stable_id for binding in adaptation_bindings}
        bound_paths = {
            (binding.stable_id, path)
            for binding in adaptation_bindings
            for path in binding.member_paths
        }
        file_paths = {(entry.owner, entry.path) for entry in entries}
        if {entry.owner for entry in entries} != bound_owners or not file_paths.issubset(
            bound_paths
        ):
            refusals.append(
                _refuse(
                    "adaptation_binding_mismatch",
                    "bundle files do not close over the declared component adaptations",
                    "bundle.json",
                    setup_stable_id,
                )
            )

    refusals.sort(key=lambda item: (item.code, item.details.get("path", "")))
    if refusals:
        # `REQ-608`: a blocked bundle is not a partial one. A manifest beside a
        # list of refusals would read as "almost built".
        return Bundle(
            manifest={},
            files=(),
            digest="",
            archive=b"",
            artifact_digest="",
            refusals=tuple(refusals),
        )

    identity_manifest = _manifest(
        entries,
        setup_stable_id=setup_stable_id,
        setup_version=setup_version,
        setup_digest=setup_digest,
        harness_id=harness_id,
        setup_passport=setup_passport,
        composition_report=composition_report,
        conversion_report=conversion_report,
        input_digest=input_digest,
        target_scope=target_scope,
        bundle_format=bundle_format,
        projection_profile=projection_profile,
        adaptation_bindings=adaptation_bindings,
    )
    digest = digest_canonical(BUNDLE_DOMAIN, identity_manifest)
    manifest = {**identity_manifest, "bundle_digest": digest}
    archive = _archive(
        manifest,
        accepted,
        setup_passport=setup_passport,
        composition_report=composition_report,
        conversion_report=conversion_report,
    )
    if len(archive) > MAX_BUNDLE_BYTES:
        refusal = _refuse(
            "bundle_too_large",
            "the serialized bundle is larger than the declared bound",
            "bundle.zip",
            "",
            {"limit": str(MAX_BUNDLE_BYTES), "received": str(len(archive))},
        )
        return Bundle(
            manifest={},
            files=(),
            digest="",
            archive=b"",
            artifact_digest="",
            refusals=(refusal,),
        )
    return Bundle(
        manifest=manifest,
        files=tuple(entries),
        digest=digest,
        archive=archive,
        artifact_digest=f"sha256:{hashlib.sha256(archive).hexdigest()}",
        refusals=(),
    )


def _manifest(
    entries: list[FileEntry],
    *,
    setup_stable_id: str,
    setup_version: str,
    setup_digest: str,
    harness_id: str,
    setup_passport: JsonValue,
    composition_report: JsonValue,
    conversion_report: JsonValue,
    input_digest: str,
    target_scope: str = "global",
    bundle_format: str = BUNDLE_FORMAT,
    projection_profile: ProjectionProfileBinding | None = None,
    adaptation_bindings: tuple[ComponentAdaptationBinding, ...] = (),
) -> dict[str, JsonValue]:
    """The manifest, built by naming every field it may hold.

    A whitelist rather than a copy with removals: `harness-bundle.md` forbids
    build time, local paths and model explanations in the hashed content, and a
    removal has to be right about every field invented later.
    """
    # Present only away from the default. A bundle compiled for the harness
    # home is byte-identical to one compiled before scopes were chosen, so
    # every digest a released plan already binds stays what it was.
    scoped: dict[str, JsonValue] = (
        {} if target_scope == "global" else {"target_scope": target_scope}
    )
    return {
        "schema_version": 1,
        "bundle_format": bundle_format,
        "protocol_version": PROTOCOL_VERSION,
        "builder_version": BUILDER_VERSION,
        "harness_id": harness_id,
        **scoped,
        **(
            {
                "projection_profile": projection_profile.as_json(),
                "component_adaptations": [
                    item.as_json()
                    for item in sorted(adaptation_bindings, key=lambda item: item.stable_id)
                ],
            }
            if bundle_format == BUNDLE_FORMAT_V2 and projection_profile is not None
            else {}
        ),
        "setup": {
            "stable_id": setup_stable_id,
            "version": setup_version,
            "passport_digest": setup_digest,
        },
        "input_digest": input_digest,
        "managed_paths": [item.path for item in entries],
        "files": [item.as_json() for item in entries],
        "documents": {
            "setup_passport": _document("setup-passport.json", setup_passport),
            "composition_report": _document("composition-report.json", composition_report),
            "conversion_report": _document("conversion-report.json", conversion_report),
        },
        "limits": {
            "max_files": MAX_FILES,
            "max_file_bytes": MAX_FILE_BYTES,
            "max_bundle_bytes": MAX_BUNDLE_BYTES,
        },
        "composition_report": composition_report,
        "conversion_report": conversion_report,
    }


def _document(path: str, value: JsonValue) -> dict[str, JsonValue]:
    content = canonize(value)
    return {
        "path": path,
        "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
        "byte_length": len(content),
    }


def _archive(
    manifest: dict[str, JsonValue],
    sources: list[Source],
    *,
    setup_passport: JsonValue,
    composition_report: JsonValue,
    conversion_report: JsonValue,
) -> bytes:
    """Serialize the complete v1 package with host-independent ZIP metadata."""
    members: list[tuple[str, bytes, int, bool]] = [
        ("bundle.json", canonize(manifest), MODE_FILE, False),
        ("setup-passport.json", canonize(setup_passport), MODE_FILE, False),
        ("composition-report.json", canonize(composition_report), MODE_FILE, False),
        ("conversion-report.json", canonize(conversion_report), MODE_FILE, False),
        ("files/", b"", MODE_EXECUTABLE, True),
    ]
    members.extend(
        (f"files/{source.path}", source.content, source.mode, False) for source in sources
    )
    members.append(("attestations/", b"", MODE_EXECUTABLE, True))

    holder = io.BytesIO()
    with zipfile.ZipFile(holder, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for path, content, mode, directory in members:
            info = zipfile.ZipInfo(path, date_time=ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            file_type = 0o040000 if directory else 0o100000
            info.external_attr = (file_type | mode) << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, content)
    return holder.getvalue()


def _path_problem(path: str) -> tuple[str, str] | None:
    """Which rule a path breaks, if it breaks one."""
    if not path:
        return "path_empty_segment", "a bundled path cannot be empty"
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        return "path_invalid_character", "a bundled path cannot contain control characters"
    encoded = path.encode("utf-8")
    if len(encoded) > MAX_PATH_BYTES or any(
        len(segment.encode("utf-8")) > MAX_SEGMENT_BYTES for segment in path.split("/")
    ):
        return "path_too_long", "a bundled path exceeds the portable byte bound"
    if path.startswith("/") or path.startswith("~") or (len(path) > 1 and path[1] == ":"):
        return "path_not_relative", "a bundled path is relative to the target"
    segments = path.split("/")
    if any(segment == ".." for segment in segments):
        return "path_escapes_target", "a bundled path cannot climb out of the target"
    if any(segment in {"", "."} for segment in segments):
        return "path_empty_segment", "a bundled path cannot hold an empty or dot segment"
    return _portability_problem(segments)


#: Names Windows reserves for devices, whatever extension follows them. `CON.md`
#: is the device, not a file, so the test is on the stem rather than the whole
#: segment.
_RESERVED_STEMS: Final[frozenset[str]] = frozenset(
    {"con", "prn", "aux", "nul"}
    # `¹²³` are not decoration. `learn.microsoft.com/windows/win32/fileio/naming-a-file`
    # says Windows "recognizes the 8-bit ISO/IEC 8859-1 superscript digits ¹, ²,
    # and ³ as digits and treats them as valid parts of COM# and LPT# device
    # names, making them reserved in every directory", and gives the worked
    # example: `echo test > COM¹` fails to create a file.
    #
    # Raised by the provider side, which read the page, implemented it, and then
    # deliberately did *not* ship stricter than this compiler — a validator that
    # refuses what the other blessed is `plugins/local` with the roles reversed,
    # and that cost a release to open a window for. Verified here before
    # widening rather than taken on the report.
    | {f"com{digit}" for digit in "123456789¹²³"}
    | {f"lpt{digit}" for digit in "123456789¹²³"}
)

#: Characters the same page reserves outright. `/` is the separator and `\` is
#: refused as a path shape elsewhere, so these are the rest of that list.
_RESERVED_CHARACTERS: Final[str] = '<>"|?*'


def _portability_problem(segments: Sequence[str]) -> tuple[str, str] | None:
    """One bundle, one installability, on every supported operating system.

    Each of these is an ordinary file on Linux and is either impossible or a
    *different object* on Windows: a reserved device name is not a file whatever
    extension follows it, a trailing dot or space is stripped so the written
    name is not the manifested one, and a colon selects an NTFS alternate data
    stream rather than a path.

    Refused here rather than left to the provider because the alternative is a
    digest that means "installable" on the host that built it and something else
    on the host that receives it. The bundle is the unit of identity, so its
    validity cannot depend on where it lands.

    Checked on the stem, not by substring: `console.md`, `connect.json` and
    `com10.txt` are real names people use, and a guard that cost them would be
    paid for every day to prevent something rare.
    """
    for segment in segments:
        stem = segment.split(".", 1)[0].lower()
        if stem in _RESERVED_STEMS:
            return (
                "path_not_portable",
                "a bundled path names a reserved device and cannot exist on every target",
            )
        if segment.endswith((".", " ")):
            return (
                "path_not_portable",
                "a bundled path segment ends in a dot or space, which is not preserved",
            )
        if ":" in segment:
            return (
                "path_not_portable",
                "a bundled path segment carries a stream separator rather than a name",
            )
        if any(character in segment for character in _RESERVED_CHARACTERS):
            return (
                "path_not_portable",
                "a bundled path segment holds a character no Windows name may carry",
            )
    return None


def _is_secret(path: str) -> bool:
    """Whether this name says the file holds a credential.

    By name only. Opening a file to decide whether it holds a secret is the harm
    the rule exists to prevent, and a name is enough to keep it out.
    """
    name = path.rsplit("/", 1)[-1]
    return (
        name in SECRET_NAMES or name.startswith(SECRET_PREFIXES) or name.endswith(SECRET_SUFFIXES)
    )


def _refuse(
    code: str, summary: str, path: str, owner: str, extra: dict[str, str] | None = None
) -> Refusal:
    if code not in REFUSALS:  # pragma: no cover - guarded by the registry test
        raise KeyError(code)
    details = {"path": path, **(extra or {})}
    if owner:
        details["owner"] = owner
    return Refusal(code, summary, details)
