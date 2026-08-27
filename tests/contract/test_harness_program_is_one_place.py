"""`ADR-0122`: one place reports the state of a harness program, and one only.

The record deferred this guard on purpose. Written before `harness status`
existed it would have been green because the path it guards did not exist yet,
and a green sentinel over nothing reads as coverage while staying green through
any future mistake. `harness status` exists now, so the guard is written now.

What it protects is a collision that already happened once in this vocabulary.
`toolchain harnesses` answers *what is visible on this machine* and spells one
of its answers `installed`. A program lifecycle that also spelled a state
`installed` would give one word two subjects — the product being present
somewhere, and this CLI having put a specific build under a specific prefix.
The two are not the same claim and an agent cannot tell them apart by reading.
"""

from __future__ import annotations

from typing import Final, get_args, get_origin

from ai_stp_cli.registry import DECLARATIONS
from ai_stp_contracts.machine_help import HarnessPresence, HarnessProgramStatus
from ai_stp_contracts.schemas import CLI_MODELS

#: The prefix is the program lifecycle's own noun: `--target` holds the
#: configuration and `--prefix` holds the program. A model that names a prefix
#: is therefore talking about the program, and every one of them has to belong
#: to this family. A third place reporting program state needs a prefix to say
#: which one, so this set is where it would show up.
_PROGRAM_FAMILY: Final[frozenset[str]] = frozenset(
    {"cli-harness-program", "cli-harness-program-status"}
)


def _literal_values(annotation: object) -> frozenset[str]:
    """The closed set a `Literal[...]` field admits."""
    if get_origin(annotation) is None:
        return frozenset()
    return frozenset(str(item) for item in get_args(annotation))


def test_exactly_one_command_reports_the_state_of_a_harness_program() -> None:
    declared = [
        " ".join(item.path)
        for item in DECLARATIONS
        if item.result_schema == "urn:ai-stp:schema:v1:cli-harness-program-status"
    ]
    assert declared == ["harness status"]


def test_only_the_program_family_names_a_prefix() -> None:
    # A handful of exported schemas are hand-written dictionaries rather than
    # models; they carry no fields to inspect and none of them is a program.
    naming = {
        key
        for key, model in CLI_MODELS.items()
        if isinstance(model, type) and "prefix" in model.model_fields
    }
    assert naming == _PROGRAM_FAMILY


def test_program_state_and_detection_state_share_no_word() -> None:
    """One word, one subject.

    `toolchain harnesses` keeps detection; `harness status` keeps the program.
    An overlap would not fail any other check — both models would still be
    valid — and would still make the answer unreadable.
    """
    program = _literal_values(HarnessProgramStatus.model_fields["state"].annotation)
    detection = _literal_values(HarnessPresence.model_fields["state"].annotation)

    assert program, "the program status must close its own state vocabulary"
    assert detection, "the detection survey must close its own state vocabulary"
    assert not (program & detection)


def test_detection_commands_did_not_learn_the_program() -> None:
    """`toolchain harnesses` and `harness-capabilities` stay what they were.

    Named by path rather than by schema so that renaming the schema underneath
    them does not quietly satisfy this.
    """
    detection = {
        " ".join(item.path): item.result_schema
        for item in DECLARATIONS
        if item.path[:1] == ["toolchain"]
    }
    assert detection["toolchain harnesses"] == "urn:ai-stp:schema:v1:cli-harness-survey"
    assert (
        detection["toolchain harness-capabilities"]
        == "urn:ai-stp:schema:v1:cli-harness-capability-table"
    )
