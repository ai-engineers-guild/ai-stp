"""Read exact environment prerequisites without preparing or executing them."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import harness, toolchain
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, cli_program, installation, project_passport, revisions, versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_cli.toolchain import install as tool_install
from ai_stp_contracts.machine_help import EnvironmentInspection, EnvironmentRequirement
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(str(item) for item in cast(tuple[object, ...] | list[object], value))
    return ()


def _document(
    connection: sqlite3.Connection, stable_id: str, version: str, expected_digest: str = ""
) -> dict[str, JsonValue]:
    held = versions.held(connection, stable_id, version)
    stored = revisions.get(connection, held.revision_id) if held else None
    if held is None or stored is None:
        raise CliFailure("AI_STP_NOT_FOUND", "an exact environment dependency is missing")
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    if (
        document.get("stable_id") != stable_id
        or document.get("version") != version
        or cache.digest_of(document) != held.passport_digest
        or (expected_digest and expected_digest != held.passport_digest)
    ):
        raise CliFailure("AI_STP_CONFLICT", "an environment dependency has changed identity")
    return document


def _prefixes(parameters: Mapping[str, object], harnesses: set[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for item in _strings(parameters.get("harness-prefix")):
        name, separator, value = item.partition("=")
        path = Path(value).expanduser()
        if not separator or name not in harnesses or name in result or not path.is_absolute():
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR", "name each harness prefix once as harness=absolute-path"
            )
        result[name] = path
    return result


def inspect(parameters: Mapping[str, object]) -> Answer[EnvironmentInspection]:
    """Join exact requirements with local observations and concrete next steps."""
    references = tuple(sorted(set(_strings(parameters.get("setup")))))
    project_id = str(parameters.get("project") or "")
    target = Path(str(parameters.get("target") or "")).expanduser()
    if not references or not project_id or not target.is_absolute() or not target.is_dir():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "environment inspection requires exact setups and an absolute project target",
        )
    with closing(open_readonly(configured_path())) as connection:
        if project_passport.stable_id_for(connection, target.resolve()) != project_id:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the environment target does not match its project passport",
            )
        setups: list[SetupVersionPassport] = []
        components: dict[str, ComponentVersionPassport] = {}
        try:
            for reference in references:
                stable_id, separator, version = reference.partition("@")
                if not separator or not version:
                    raise CliFailure(
                        "AI_STP_VALIDATION_ERROR",
                        "environment setups require exact id@X.Y coordinates",
                    )
                setup = SetupVersionPassport.model_validate(
                    _document(connection, stable_id, version)
                )
                setups.append(setup)
                for member in setup.components:
                    coordinate = f"{member.stable_id}@{member.version}"
                    component = ComponentVersionPassport.model_validate(
                        _document(
                            connection, member.stable_id, member.version, member.passport_digest
                        )
                    )
                    components[coordinate] = component
        except ValidationError as error:
            raise CliFailure(
                "AI_STP_CONFLICT", "an environment dependency passport is invalid"
            ) from error
        prefixes = _prefixes(parameters, {setup.harness_id for setup in setups})
        requirements: list[EnvironmentRequirement] = []
        for setup in setups:
            requirements.append(_harness_requirement(connection, setup, prefixes, target))
        passports: list[SetupVersionPassport | ComponentVersionPassport] = [
            *setups,
            *components.values(),
        ]
        requirements.extend(_access_requirements(passports))
        for coordinate, component in sorted(components.items()):
            if component.component_type != "cli":
                continue
            observed = cli_program.status(
                connection, stable_id=component.stable_id, version=component.version
            )
            present = observed.state == "present"
            requirements.append(
                EnvironmentRequirement(
                    kind="shared_program",
                    identity=component.stable_id,
                    version=component.version,
                    digest=component.artifact.digest,
                    sources=[coordinate],
                    state="satisfied" if present else "action_required",
                    reason="the exact shared program bytes are installed"
                    if present
                    else "the exact shared program must be installed",
                    actions=[]
                    if present
                    else [
                        [
                            "ai-stp",
                            "component",
                            "program",
                            "install",
                            "--id",
                            component.stable_id,
                            "--version",
                            component.version,
                            "--json",
                        ]
                    ],
                )
            )
        for tool_id in sorted(set(_strings(parameters.get("tool")))):
            requirements.append(_tool_requirement(tool_id, offline=bool(parameters.get("offline"))))
    return Answer(
        EnvironmentInspection(
            project_id=project_id,
            setups=list(references),
            prerequisites_satisfied=all(row.state == "satisfied" for row in requirements),
            requirements=requirements,
            detected_harnesses=toolchain.harnesses({}).payload,
        )
    )


def _harness_requirement(
    connection: sqlite3.Connection,
    setup: SetupVersionPassport,
    prefixes: dict[str, Path],
    target: Path,
) -> EnvironmentRequirement:
    source = f"{setup.stable_id}@{setup.version}"
    prefix = prefixes.get(setup.harness_id)
    if prefix is None:
        return EnvironmentRequirement(
            kind="harness_program",
            identity=setup.harness_id,
            sources=[source],
            state="not_observed",
            reason="an explicit managed harness prefix is required for program observation",
        )
    observed = harness.status({"harness": setup.harness_id, "prefix": str(prefix)}).payload
    present = observed.state == "present"
    if present and (
        installation.plan(connection, observed.operation_id).program_harness_id != setup.harness_id
    ):
        return EnvironmentRequirement(
            kind="harness_program",
            identity=setup.harness_id,
            sources=[source],
            state="blocked",
            reason="the program receipt does not bind this harness identity",
        )
    compatible = (
        not setup.supported_harness_versions or observed.version in setup.supported_harness_versions
    )
    return EnvironmentRequirement(
        kind="harness_program",
        identity=setup.harness_id,
        version=observed.version,
        sources=[source],
        state=("satisfied" if compatible else "blocked")
        if present
        else (
            "action_required"
            if observed.state in {"never_installed", "removed", "lost"}
            else "blocked"
        ),
        reason=observed.reason
        if not present or compatible
        else "the observed harness version is outside the setup's exact supported versions",
        actions=[]
        if present or observed.state in {"foreign", "interrupted"}
        else [
            [
                "ai-stp",
                "harness",
                "install",
                "--harness",
                setup.harness_id,
                "--prefix",
                str(prefix),
                "--target",
                str(target),
                "--json",
            ]
        ],
    )


def _access_requirements(
    passports: list[SetupVersionPassport | ComponentVersionPassport],
) -> list[EnvironmentRequirement]:
    variables: dict[str, list[str]] = {}
    authorizations: dict[str, list[str]] = {}
    for passport in passports:
        source = f"{passport.stable_id}@{passport.version}"
        for requirement in passport.required_env:
            variables.setdefault(requirement.name, []).append(source)
        if passport.requires_authorization != "none":
            authorizations.setdefault(passport.requires_authorization, []).append(source)
        elif passport.requires_credentials:
            authorizations.setdefault("credentials", []).append(source)
    present = frozenset(os.environ)
    return [
        EnvironmentRequirement(
            kind="environment_variable",
            identity=name,
            sources=sorted(set(sources)),
            state="satisfied" if name in present else "action_required",
            reason="the variable name is present in this process"
            if name in present
            else "the declared variable is absent from this process",
        )
        for name, sources in sorted(variables.items())
    ] + [
        EnvironmentRequirement(
            kind="authorization",
            identity=name,
            sources=sorted(set(sources)),
            state="not_observed",
            reason="authorization requires fresh provider or service evidence",
        )
        for name, sources in sorted(authorizations.items())
    ]


def _tool_requirement(tool_id: str, *, offline: bool) -> EnvironmentRequirement:
    try:
        tool, artifact = toolchain.pinned_for(tool_id)
        planned = tool_install.plan(tool, artifact, offline=offline)
    except CliFailure as error:
        return EnvironmentRequirement(
            kind="toolchain_tool",
            identity=tool_id,
            state="blocked",
            reason=error.message,
        )
    present = planned.action == "already_installed"
    return EnvironmentRequirement(
        kind="toolchain_tool",
        identity=tool_id,
        version=tool.version,
        digest=artifact.digest,
        state="satisfied"
        if present
        else "blocked"
        if planned.action == "needs_user_action"
        else "action_required",
        reason=planned.reason,
        actions=[]
        if present or planned.action == "needs_user_action"
        else [
            [
                "ai-stp",
                "toolchain",
                "install",
                "--tool",
                tool_id,
                *(["--offline"] if offline else []),
                "--json",
            ]
        ],
    )
