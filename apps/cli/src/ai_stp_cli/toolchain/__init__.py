"""The managed toolchain profile and the manifest that pins it (`SPEC-014`).

`REQ-1402` makes the profile a matter of policy: an empty project and a project
holding only documentation resolve to the same `mvp-full`, because what a
developer needs installed is not deducible from what they have written so far.

`REQ-1403` is the reason this module is mostly refusals. Every entry must carry
an exact version, an exact source, a proof of integrity, a licence and the
systems it supports — and a manifest that cannot state one of those is rejected
rather than trusted. Adding a tool "for now, without a checksum" is therefore
impossible, which is the point.

Two integrity proofs of different strength are kept apart on purpose. A checksum
the vendor published is an upstream statement about the artifact; one we
computed during a single download only proves nothing changed *since* we pinned
it. Folding both into one field would lose exactly the distinction that matters
when deciding whether to trust a new entry.
"""

import platform
import tomllib
from dataclasses import dataclass
from importlib import resources
from typing import Final, cast

from ai_stp_cli.errors import CliFailure

#: The one profile of the MVP (`REQ-1402`). A second one would be a policy
#: decision, and there is no requirement asking for one.
PROFILE: Final[str] = "mvp-full"

MANIFEST_FILE: Final[str] = "mvp-full.toml"

#: The shape of this file that this build understands.
MANIFEST_SCHEMA_VERSION: Final[int] = 1

#: How a platform is named here. One spelling, chosen once: the same machine
#: answers `arm64` on macOS and `aarch64` on Linux, and a table keyed by
#: whatever `platform.machine()` happened to say would have two names for one
#: thing.
LINUX_X86_64: Final[str] = "linux-x86_64"
WINDOWS_X86_64: Final[str] = "windows-x86_64"
SUPPORTED_PLATFORMS: Final[tuple[str, ...]] = (
    LINUX_X86_64,
    "linux-aarch64",
    "darwin-arm64",
    "darwin-x86_64",
    WINDOWS_X86_64,
)

#: Words that make a source floating rather than exact (`REQ-1403`). A URL that
#: resolves to something different tomorrow is not a pinned dependency, however
#: precise its checksum looks.
FLOATING_MARKERS: Final[tuple[str, ...]] = (
    "/latest/",
    "/main/",
    "/master/",
    "/head/",
    "/edge/",
    "/nightly/",
)

#: How an integrity proof was obtained, strongest first.
DIGEST_SOURCES: Final[frozenset[str]] = frozenset({"vendor_published", "pinned_on_download"})


@dataclass(frozen=True)
class Artifact:
    """One downloadable file for one platform."""

    url: str
    digest: str


@dataclass(frozen=True)
class Tool:
    """One pinned tool, with everything `REQ-1403` requires it to state."""

    tool_id: str
    ecosystem: str
    purpose: str
    version: str
    license: str
    entry_point: str
    digest_source: str
    artifacts: dict[str, Artifact]


@dataclass(frozen=True)
class Manifest:
    """The whole profile: which ecosystems it covers and what it pins."""

    profile: str
    ecosystems: dict[str, str]
    tools: tuple[Tool, ...]


@dataclass(frozen=True)
class EcosystemPlan:
    """What this profile offers for one ecosystem on one platform."""

    ecosystem: str
    title: str

    #: `available` when something is pinned for this platform, `not_available`
    #: otherwise — with a reason, because `REQ-1407` asks for the reason and an
    #: empty list would leave the caller guessing whether it asked wrongly.
    state: str
    reason: str | None
    tools: tuple[Tool, ...]


def current_platform() -> str:
    """This machine, in the one spelling the manifest uses."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        return "linux-aarch64" if machine in {"aarch64", "arm64"} else LINUX_X86_64
    if system == "darwin":
        return "darwin-arm64" if machine in {"arm64", "aarch64"} else "darwin-x86_64"
    if system == "windows":
        if machine in {"arm64", "aarch64"}:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "this Windows architecture has no managed toolchain",
                details={"supported": ", ".join(SUPPORTED_PLATFORMS)},
                next_actions=["doctor --json"],
            )
        return WINDOWS_X86_64
    # The registry of codes is closed, and none of the nineteen means
    # "unsupported operating system". A precondition of the environment is not
    # met, which is what this one says.
    raise CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        "this platform has no managed toolchain",
        details={"supported": ", ".join(SUPPORTED_PLATFORMS)},
        next_actions=["doctor --json"],
    )


def load() -> Manifest:
    """Read and validate the manifest this build ships."""
    text = resources.files("ai_stp_cli").joinpath("toolchain", MANIFEST_FILE).read_text("utf-8")
    return parse(text)


def parse(text: str) -> Manifest:
    """Turn manifest text into a manifest, refusing anything under-specified.

    Every refusal names the entry and what is missing. A manifest is edited by a
    person adding a tool, and "invalid manifest" without a field name is a
    message that makes them guess.
    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise _refused("the toolchain manifest is not valid TOML", str(error)) from error

    version = document.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise _refused(
            f"this build reads toolchain manifest schema {MANIFEST_SCHEMA_VERSION}",
            f"found {version!r}",
        )

    ecosystems = document.get("ecosystems")
    if not isinstance(ecosystems, dict) or not ecosystems:
        raise _refused("the manifest declares no ecosystems", "ecosystems")
    named = {str(key): str(value) for key, value in cast(dict[object, object], ecosystems).items()}

    declared = document.get("tools", [])
    if not isinstance(declared, list):
        raise _refused("the manifest declares tools in the wrong shape", "tools")
    tools = tuple(_tool(entry, named) for entry in cast(list[object], declared))
    seen: set[str] = set()
    for tool in tools:
        if tool.tool_id in seen:
            raise _refused("a tool is declared twice", tool.tool_id)
        seen.add(tool.tool_id)

    return Manifest(profile=str(document.get("profile", "")), ecosystems=named, tools=tools)


def _tool(entry: object, ecosystems: dict[str, str]) -> Tool:
    if not isinstance(entry, dict):
        raise _refused("a tool entry is not a table", str(entry)[:40])
    held = {str(key): value for key, value in cast(dict[object, object], entry).items()}
    tool_id = str(held.get("id", "")).strip()
    if not tool_id:
        raise _refused("a tool entry has no identifier", "id")

    for field in ("ecosystem", "purpose", "version", "license", "entry_point", "digest_source"):
        if not str(held.get(field, "")).strip():
            raise _refused(f"tool {tool_id} declares no {field}", field)

    ecosystem = str(held["ecosystem"])
    if ecosystem not in ecosystems:
        raise _refused(f"tool {tool_id} names an undeclared ecosystem", ecosystem)

    digest_source = str(held["digest_source"])
    if digest_source not in DIGEST_SOURCES:
        raise _refused(
            f"tool {tool_id} declares an unknown integrity provenance",
            f"{digest_source}; expected one of {', '.join(sorted(DIGEST_SOURCES))}",
        )

    version = str(held["version"])
    if any(character in version for character in "^~*<>= "):
        # A range is not a version. `REQ-1403` asks for the exact one, and a
        # range would make two installations differ while both look pinned.
        raise _refused(f"tool {tool_id} declares a version range rather than a version", version)

    artifacts = _artifacts(tool_id, held.get("artifacts"), version)
    return Tool(
        tool_id=tool_id,
        ecosystem=ecosystem,
        purpose=str(held["purpose"]),
        version=version,
        license=str(held["license"]),
        entry_point=str(held["entry_point"]),
        digest_source=digest_source,
        artifacts=artifacts,
    )


def _artifacts(tool_id: str, raw: object, version: str) -> dict[str, Artifact]:
    if not isinstance(raw, dict) or not raw:
        raise _refused(f"tool {tool_id} supports no platform", "artifacts")
    found: dict[str, Artifact] = {}
    for key, value in cast(dict[object, object], raw).items():
        name = str(key)
        if name not in SUPPORTED_PLATFORMS:
            raise _refused(
                f"tool {tool_id} names an unsupported platform",
                f"{name}; expected one of {', '.join(SUPPORTED_PLATFORMS)}",
            )
        if not isinstance(value, dict):
            raise _refused(f"tool {tool_id} has a malformed artifact for {name}", name)
        held = {str(inner): str(item) for inner, item in cast(dict[object, object], value).items()}
        url = held.get("url", "")
        digest = held.get("digest", "")
        if not url.startswith("https://"):
            raise _refused(
                f"tool {tool_id} fetches {name} over something other than HTTPS",
                f"{name}: {url or 'absent'}",
            )
        lowered = url.lower()
        if any(marker in lowered for marker in FLOATING_MARKERS):
            raise _refused(f"tool {tool_id} declares a floating source for {name}", url)
        if version not in url:
            # The version must be visible in the source. Otherwise the entry
            # claims a version the URL does not promise to keep serving.
            raise _refused(f"tool {tool_id} has a source that does not pin {version}", url)
        if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
            # Naming the platform matters more than echoing the bad value: an
            # absent digest echoes as nothing, and "invalid" with an empty
            # detail is the message that makes an editor guess.
            raise _refused(
                f"tool {tool_id} has no usable integrity proof for {name}",
                f"{name}: {digest or 'absent'}",
            )
        found[name] = Artifact(url=url, digest=digest)
    return found


def plan(manifest: Manifest, target: str) -> tuple[EcosystemPlan, ...]:
    """What the profile offers on one platform, ecosystem by ecosystem.

    Deterministic and total: every declared ecosystem appears, in declaration
    order, whether or not anything is pinned for it. `REQ-1407` wants the
    missing ones named with a reason rather than absent, because an agent
    reading a short list cannot tell "nothing needed" from "nothing yet".
    """
    plans: list[EcosystemPlan] = []
    for ecosystem, title in manifest.ecosystems.items():
        declared = tuple(item for item in manifest.tools if item.ecosystem == ecosystem)
        usable = tuple(item for item in declared if target in item.artifacts)
        if usable:
            plans.append(EcosystemPlan(ecosystem, title, "available", None, usable))
        elif declared:
            plans.append(
                EcosystemPlan(
                    ecosystem,
                    title,
                    "not_available",
                    f"nothing pinned for {target}",
                    (),
                )
            )
        else:
            plans.append(
                EcosystemPlan(
                    ecosystem,
                    title,
                    "not_available",
                    "no tool is pinned for this ecosystem yet",
                    (),
                )
            )
    return tuple(plans)


def _refused(message: str, detail: str) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        message,
        details={"at": detail},
        next_actions=["toolchain profile --json"],
    )
