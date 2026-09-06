"""The Agent Skills authoring contract, checked against the published standard.

`#455`. Of the closed component kinds, `skill` is the one with an external
specification that exists independently of this estate — <https://agentskills.io
/specification> — so it is the one where a validator can be right or wrong about
something other than our own opinion. Every limit below is quoted from that
document rather than chosen here, and the constant carries the sentence it came
from so a later reader can check it without re-deriving it.

What this does *not* do is judge the body. The specification says the Markdown
after the frontmatter has no format restrictions, and a validator that invents
some would be enforcing taste as though it were the standard.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import yaml

#: The one required file, at the root of the skill directory. "A skill is a
#: directory containing, at minimum, a `SKILL.md` file." Not `payload/SKILL.md`:
#: a wrapper directory makes the package non-conforming for every reader that
#: implements the standard rather than ours.
ENTRY_POINT: Final[str] = "SKILL.md"

#: "Max 64 characters. Lowercase letters, numbers, and hyphens only. Must not
#: start or end with a hyphen." Consecutive hyphens are refused too, which the
#: specification states separately and an obvious regex allows.
NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX: Final[int] = 64
DESCRIPTION_MAX: Final[int] = 1024
COMPATIBILITY_MAX: Final[int] = 500

#: Every field the standard defines, and which of them a package must carry.
REQUIRED_FIELDS: Final[tuple[str, ...]] = ("name", "description")
OPTIONAL_FIELDS: Final[tuple[str, ...]] = ("license", "compatibility", "metadata", "allowed-tools")

#: Directories the standard names as conventions. Their absence is not a defect
#: and their presence is not required; they are listed so an unknown directory
#: can be reported as unrecognised rather than as wrong — "A skill directory may
#: contain any files and directories beyond the required `SKILL.md`."
STANDARD_DIRECTORIES: Final[tuple[str, ...]] = ("scripts", "references", "assets")

#: Directories this estate adds. They are an extension, not a deviation: the
#: standard permits any additional content, so carrying evaluations beside a
#: skill cannot make the package non-conforming. Named here so the report can
#: say which of the two a directory is.
EXTENSION_DIRECTORIES: Final[tuple[str, ...]] = ("evals", "tests", "fixtures")

#: A directory under `skills/` holding one of these is a plugin, not a skill —
#: the products put both under the same parent and tell them apart by manifest,
#: not by location. A validator that does not know this reports a perfectly good
#: plugin as a skill with no entry point.
PLUGIN_MANIFEST: Final[str] = "plugin.json"
PLUGIN_MANIFEST_SUFFIX: Final[str] = "-plugin"


@dataclass(frozen=True)
class Finding:
    """One deviation, named precisely enough to fix without guessing."""

    #: Stable, so a caller can branch on it rather than on the sentence.
    code: str
    summary: str

    #: The field or path it is about. Always set: a finding nobody can locate
    #: is a finding that has not been reported.
    at: str


@dataclass(frozen=True)
class Report:
    """Whether a directory is a conforming skill package, and what is wrong."""

    path: str

    #: `skill`, or `plugin` when the directory is packaged as one. A plugin is
    #: not a malformed skill and is not reported as one.
    packaged_as: str

    conforms: bool
    findings: tuple[Finding, ...] = ()

    #: What the frontmatter declared, when it could be read at all.
    name: str = ""
    description: str = ""

    #: Directories found, split by what they are. Neither list is a defect.
    standard_directories: tuple[str, ...] = ()
    extension_directories: tuple[str, ...] = ()
    other_entries: tuple[str, ...] = ()


def is_plugin(place: Path) -> bool:
    """Whether this directory is packaged as a plugin rather than a skill.

    Two shapes, because the products use two: a manifest at the root, and a
    vendor-prefixed manifest directory matched on its **suffix** rather than
    against a list of the vendors met so far — a list makes the next vendor a
    silent miss.
    """
    if not place.is_dir():
        return False
    if (place / PLUGIN_MANIFEST).is_file():
        return True
    return any(
        child.is_dir()
        and child.name.startswith(".")
        and child.name.endswith(PLUGIN_MANIFEST_SUFFIX)
        and (child / PLUGIN_MANIFEST).is_file()
        for child in _entries(place)
    )


def validate(place: Path) -> Report:
    """Check one directory against the Agent Skills Specification."""
    resolved = place.expanduser()
    if not resolved.is_dir():
        return Report(
            str(resolved),
            "unknown",
            False,
            (Finding("SK001", "a skill package is a directory", str(resolved)),),
        )
    if is_plugin(resolved):
        # Not a finding: the directory is a well-formed something else, and
        # calling it a broken skill would send the author to fix the wrong file.
        return Report(str(resolved), "plugin", True)

    findings: list[Finding] = []
    entry = resolved / ENTRY_POINT
    if not entry.is_file():
        wrapped = next(
            (child for child in _entries(resolved) if (child / ENTRY_POINT).is_file()), None
        )
        findings.append(
            Finding(
                "SK002",
                f"{ENTRY_POINT} must be at the package root"
                + (f", not inside {wrapped.name}/" if wrapped else ""),
                ENTRY_POINT,
            )
        )
        return _reported(resolved, False, tuple(findings))

    frontmatter, malformed = _frontmatter(entry)
    if malformed is not None:
        findings.append(malformed)
        return _reported(resolved, False, tuple(findings))

    name = str(frontmatter.get("name") or "")
    description = str(frontmatter.get("description") or "")
    findings.extend(_check_name(name, resolved))
    findings.extend(_check_description(description))
    findings.extend(_check_optional(frontmatter))

    return _reported(resolved, not findings, tuple(findings), name=name, description=description)


def _reported(
    place: Path,
    conforms: bool,
    findings: tuple[Finding, ...],
    *,
    name: str = "",
    description: str = "",
) -> Report:
    """One report, with the package's contents read the same way every time."""
    held = _contents(place)
    return Report(
        path=str(place),
        packaged_as="skill",
        conforms=conforms,
        findings=findings,
        name=name,
        description=description,
        standard_directories=held.standard_directories,
        extension_directories=held.extension_directories,
        other_entries=held.other_entries,
    )


def _check_name(name: str, place: Path) -> list[Finding]:
    if not name:
        return [Finding("SK010", "the frontmatter must declare a name", "name")]
    found: list[Finding] = []
    if len(name) > NAME_MAX:
        found.append(
            Finding(
                "SK011", f"a name is at most {NAME_MAX} characters, and this is {len(name)}", "name"
            )
        )
    if not NAME_PATTERN.fullmatch(name):
        found.append(
            Finding(
                "SK012",
                "a name is lowercase letters, digits and single hyphens, and may not"
                " start or end with one",
                "name",
            )
        )
    if name != place.name:
        # "Must match the parent directory name." Two names for one skill is
        # how a package installs under one and is referred to by the other.
        found.append(
            Finding("SK013", f"the name must match the directory, which is {place.name!r}", "name")
        )
    return found


def _check_description(description: str) -> list[Finding]:
    if not description.strip():
        return [Finding("SK020", "the frontmatter must declare a description", "description")]
    if len(description) > DESCRIPTION_MAX:
        return [
            Finding(
                "SK021",
                f"a description is at most {DESCRIPTION_MAX} characters,"
                f" and this is {len(description)}",
                "description",
            )
        ]
    return []


def _check_optional(frontmatter: dict[str, Any]) -> list[Finding]:
    """The optional fields, checked only where the standard states a constraint."""
    found: list[Finding] = []
    compatibility = frontmatter.get("compatibility")
    if compatibility is not None and len(str(compatibility)) > COMPATIBILITY_MAX:
        found.append(
            Finding(
                "SK030",
                f"compatibility is at most {COMPATIBILITY_MAX} characters",
                "compatibility",
            )
        )
    metadata = frontmatter.get("metadata")
    if metadata is not None and not _is_string_map(metadata):
        found.append(
            Finding("SK031", "metadata is a map from string keys to string values", "metadata")
        )
    tools = frontmatter.get("allowed-tools")
    if tools is not None and not isinstance(tools, str):
        found.append(Finding("SK032", "allowed-tools is a space-separated string", "allowed-tools"))
    unknown = sorted(set(frontmatter) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    for field in unknown:
        # A warning shaped as a finding, because the standard neither defines
        # the field nor forbids it: `metadata` is where a client's own keys
        # belong, and a bare unknown key at the top level is more often a typo
        # than a deliberate extension.
        found.append(Finding("SK033", f"{field!r} is not a field the specification defines", field))
    return found


def _is_string_map(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    items = cast(dict[object, object], value)
    return all(isinstance(key, str) and isinstance(item, str) for key, item in items.items())


def _frontmatter(entry: Path) -> tuple[dict[str, Any], Finding | None]:
    """The YAML frontmatter of `SKILL.md`, or the reason there is none."""
    try:
        text = entry.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return {}, Finding(
            "SK003", f"{ENTRY_POINT} cannot be read: {type(error).__name__}", ENTRY_POINT
        )
    if not text.startswith("---"):
        return {}, Finding("SK004", f"{ENTRY_POINT} must open with YAML frontmatter", ENTRY_POINT)
    _, _, rest = text.partition("\n")
    block, marker, _ = rest.partition("\n---")
    if not marker:
        return {}, Finding("SK005", "the frontmatter block is not closed", ENTRY_POINT)
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}, Finding("SK006", "the frontmatter is not valid YAML", ENTRY_POINT)
    if not isinstance(parsed, dict):
        return {}, Finding("SK007", "the frontmatter must be a mapping of fields", ENTRY_POINT)
    return cast(dict[str, Any], parsed), None


@dataclass(frozen=True)
class Contents:
    """What the package holds, split into the standard, ours, and everything else."""

    standard_directories: tuple[str, ...]
    extension_directories: tuple[str, ...]
    other_entries: tuple[str, ...]


def _contents(place: Path) -> Contents:
    """Read the package's entries and sort them into those three."""
    standard: list[str] = []
    extension: list[str] = []
    other: list[str] = []
    for child in _entries(place):
        if child.name == ENTRY_POINT:
            continue
        if child.is_dir() and child.name in STANDARD_DIRECTORIES:
            standard.append(child.name)
        elif child.is_dir() and child.name in EXTENSION_DIRECTORIES:
            extension.append(child.name)
        else:
            other.append(child.name)
    return Contents(tuple(sorted(standard)), tuple(sorted(extension)), tuple(sorted(other)))


def _entries(place: Path) -> tuple[Path, ...]:
    """Direct children, sorted, tolerating a directory that cannot be listed."""
    try:
        return tuple(sorted(place.iterdir()))
    except OSError:
        return ()
