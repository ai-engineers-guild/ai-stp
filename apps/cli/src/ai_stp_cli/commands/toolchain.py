"""`ai-stp toolchain` — what the managed profile pins (issue #151)."""

from collections.abc import Mapping

from ai_stp_cli import toolchain
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harness_catalog
from ai_stp_cli.local import harnesses as harness_detection
from ai_stp_cli.paths import redact_home
from ai_stp_cli.toolchain import install
from ai_stp_contracts.machine_help import (
    EcosystemCoverage,
    HarnessCapabilityRow,
    HarnessCapabilityTable,
    HarnessInstallation,
    HarnessPresence,
    HarnessSurvey,
    PinnedTool,
    ToolchainProfile,
    ToolInstallation,
)


def harness_capabilities(_parameters: Mapping[str, object]) -> Answer[HarnessCapabilityTable]:
    """Return the exact declarative layouts and capabilities this build consumes."""
    return Answer(
        HarnessCapabilityTable(
            harnesses=[
                HarnessCapabilityRow(
                    harness_id=item.harness_id,  # pyright: ignore[reportArgumentType]
                    title=item.title,
                    support=item.support,  # pyright: ignore[reportArgumentType]
                    component_types=sorted(  # pyright: ignore[reportArgumentType]
                        {layout.component_type for layout in item.layouts}
                    ),
                    native_authoring=sorted(item.native_authoring),
                    global_layouts=sorted(
                        layout.relative
                        for layout in item.layouts
                        if layout.scope == harness_catalog.G
                    ),
                    project_layouts=sorted(
                        layout.relative
                        for layout in item.layouts
                        if layout.scope == harness_catalog.P
                    ),
                    layout_sources=sorted({layout.source for layout in item.layouts}),
                    gaps=list(item.gaps),
                )
                for item in harness_catalog.DEFINITIONS
            ]
        )
    )


def profile(_parameters: Mapping[str, object]) -> Answer[ToolchainProfile]:
    """Report the managed toolchain profile as it resolves on this machine.

    Reads the manifest this build ships and changes nothing. The answer covers
    every declared ecosystem, including the ones nothing is pinned for yet:
    `REQ-1407` asks for those to be named with a reason, because a caller
    reading a short list cannot tell "nothing needed" from "nothing yet".
    """
    manifest = toolchain.load()
    target = toolchain.current_platform()
    return Answer(
        ToolchainProfile(
            profile=manifest.profile,
            platform=target,
            ecosystems=[
                EcosystemCoverage(
                    ecosystem=plan.ecosystem,
                    title=plan.title,
                    state=plan.state,  # pyright: ignore[reportArgumentType]
                    reason=plan.reason,
                    tools=[
                        PinnedTool(
                            tool_id=tool.tool_id,
                            purpose=tool.purpose,
                            version=tool.version,
                            license=tool.license,
                            source=tool.artifacts[target].url,
                            digest=tool.artifacts[target].digest,
                            digest_source=tool.digest_source,  # pyright: ignore[reportArgumentType]
                        )
                        for tool in plan.tools
                    ],
                )
                for plan in toolchain.plan(manifest, target)
            ],
        )
    )


def harnesses(_parameters: Mapping[str, object]) -> Answer[HarnessSurvey]:
    """Report every declared harness and whether it is on this machine.

    Reads and changes nothing: no file is opened for writing, the home
    directory is not walked, and only the executables the detector table names
    are looked for. `REQ-1416` asks for a filesystem that is byte-identical
    afterwards, and not writing is how that is obtained rather than promised.
    """
    return Answer(
        HarnessSurvey(
            harnesses=[
                HarnessPresence(
                    harness_id=found.harness_id,
                    title=found.title,
                    support=found.support,  # pyright: ignore[reportArgumentType]
                    state=found.state,  # pyright: ignore[reportArgumentType]
                    installations=[
                        HarnessInstallation(
                            path=redact_home(item.path),
                            version=item.version,
                            reason=item.reason,
                            surface=item.surface,  # pyright: ignore[reportArgumentType]
                            version_source=item.version_source,  # pyright: ignore[reportArgumentType]
                            diagnostic=item.diagnostic,
                        )
                        for item in found.installations
                    ],
                    configuration=redact_home(found.configuration) if found.configuration else None,
                    reason=found.reason,
                )
                for found in harness_detection.detect_all()
            ]
        )
    )


def pinned_for(tool_id: str) -> tuple[toolchain.Tool, toolchain.Artifact]:
    """Find one pinned tool and the artifact for this machine, or say why not."""
    manifest = toolchain.load()
    target = toolchain.current_platform()
    found = next((item for item in manifest.tools if item.tool_id == tool_id), None)
    if found is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            f"the managed profile pins no tool called {tool_id}",
            next_actions=["toolchain profile --json"],
        )
    artifact = found.artifacts.get(target)
    if artifact is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            f"{tool_id} {found.version} is pinned, but nothing for {target}",
            details={"platform": target, "available": ", ".join(sorted(found.artifacts))},
            next_actions=["toolchain profile --json"],
        )
    return found, artifact


def install_tool(parameters: Mapping[str, object]) -> Answer[ToolInstallation]:
    """Install one pinned tool into the managed directory (`SPEC-014` REQ-1405).

    Plan first, then verify, then unpack beside the target, then move a single
    pointer. Nothing from the archive is executed at any point (`REQ-1406`), and
    nothing outside the user's own data directory is written (`REQ-1410`) — so
    there is no path here that would want a password, rather than a rule saying
    it must not ask for one.
    """
    tool_id = parameters.get("tool")
    if tool_id is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a tool id is required",
            next_actions=["toolchain profile --json"],
        )
    offline = bool(parameters.get("offline"))
    tool, artifact = pinned_for(str(tool_id))
    prepared = install.plan(tool, artifact, offline=offline)

    if prepared.action in {"already_installed", "needs_user_action"}:
        return Answer(
            ToolInstallation(
                tool_id=tool.tool_id,
                version=tool.version,
                action=prepared.action,  # pyright: ignore[reportArgumentType]
                reason=prepared.reason,
                binary=redact_home(install.binary(tool)),
                offline_capable=prepared.offline_capable,
            )
        )

    # A cached artifact is used whether or not offline was asked for: it is the
    # same bytes, already verified, and fetching them again would be a request
    # made for no reason.
    content = (
        install.cached_bytes(artifact.digest)
        if prepared.cached.exists()
        else install.download(artifact.url)
    )
    _, created = install.perform(tool, artifact, content)
    return Answer(
        ToolInstallation(
            tool_id=tool.tool_id,
            version=tool.version,
            action="installed",
            reason=f"verified against {artifact.digest} and made current",
            binary=redact_home(install.binary(tool)),
            offline_capable=True,
            paths=[redact_home(path) for path in created],
        )
    )


def remove_tool(parameters: Mapping[str, object]) -> Answer[ToolInstallation]:
    """Remove one managed tool, and only what this CLI created (`REQ-1411`).

    The ownership manifest is the list. Deciding at removal time which files
    look like ours is how a cleanup takes a user's own data with it, so anything
    not on the list is left in place and reported as left in place.
    """
    tool_id = parameters.get("tool")
    if tool_id is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a tool id is required",
            next_actions=["toolchain profile --json"],
        )
    tool, _ = pinned_for(str(tool_id))
    # After the tool is named and resolved, so the question names what it will
    # delete. `_require_declared_flags` skips confirmation flags on purpose: a
    # missing one is a decision the user has not made, which is exit class 4 and
    # not a malformed call, so the use case raises it. `destructive` is defined
    # as needing "a decision of its own even when the caller already approved
    # the surrounding work", and this was the only one of four that never asked.
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "removing a managed tool requires explicit confirmation",
            next_actions=[f"toolchain remove --tool {tool.tool_id} --confirm --json"],
        )
    removed, kept = install.remove(tool.tool_id)
    return Answer(
        ToolInstallation(
            tool_id=tool.tool_id,
            version=tool.version,
            action="removed",
            reason=f"{len(removed)} owned paths removed, {len(kept)} left in place",
            offline_capable=True,
            paths=[redact_home(path) for path in removed],
            kept=[redact_home(path) for path in kept],
        )
    )
