"""Shared executable lifecycle for catalog `cli` components."""

from collections.abc import Mapping
from contextlib import closing
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cli_program
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_contracts.machine_help import CliProgram


def install(parameters: Mapping[str, object]) -> Answer[CliProgram]:
    """Install one recorded cli artifact under the shared prefix."""
    stable_id = _required(parameters, "id")
    version = str(parameters.get("version") or "") or None
    with closing(open_registry(configured_path(), create=False)) as connection:
        return Answer(cli_program.install(connection, stable_id=stable_id, version=version))


def invoke(parameters: Mapping[str, object]) -> Answer[CliProgram]:
    """Run the installed pointer with the supplied arguments."""
    stable_id = _required(parameters, "id")
    version = str(parameters.get("version") or "") or None
    raw = parameters.get("arg") or ()
    if isinstance(raw, str):
        arguments: tuple[str, ...] = (raw,)
    elif isinstance(raw, list):
        arguments = tuple(str(item) for item in cast(list[object], raw))
    elif isinstance(raw, tuple):
        arguments = tuple(str(item) for item in cast(tuple[object, ...], raw))
    else:
        arguments = ()
    with closing(open_registry(configured_path(), create=False)) as connection:
        return Answer(
            cli_program.invoke(
                connection, stable_id=stable_id, version=version, arguments=arguments
            )
        )


def status(parameters: Mapping[str, object]) -> Answer[CliProgram]:
    """Report whether the shared executable is present."""
    stable_id = _required(parameters, "id")
    path = configured_path()
    if not path.exists():
        return Answer(
            CliProgram(
                stable_id=stable_id,
                version="0.0",
                operation="status",
                state="never_installed",
                prefix=str(cli_program.prefix()),
            )
        )
    with closing(open_readonly(path)) as connection:
        return Answer(
            cli_program.status(
                connection,
                stable_id=stable_id,
                version=str(parameters.get("version") or "") or None,
            )
        )


def remove(parameters: Mapping[str, object]) -> Answer[CliProgram]:
    """Remove the shared executable. Confirmation is required."""
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "removing a cli program requires explicit confirmation",
            details={"id": str(parameters.get("id") or "")},
            next_actions=["component program remove --id <id> --confirm --json"],
        )
    return Answer(cli_program.remove(stable_id=_required(parameters, "id")))


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value
