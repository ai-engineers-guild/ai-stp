"""The closed protocol v3 vocabulary has one owner, and prose may not restate it.

`protocol_v3.py` is the executable owner and `provider-kit/v3/manifest.json` is
its generated projection. Before this gate the same closed lists were also
written by hand in `provider-protocol.md`, `SPEC-008` and `ADR-0061` — three
copies that happened to agree, which is the state just before they stop
agreeing.

The gate targets the *enumeration*, not the mention. A requirement that names
the two commands it constrains is doing its job; a fenced block or a table
column that lists the set is a second owner. Counting mentions instead would
flag honest prose and collect exemptions until it meant nothing, which is the
failure mode its own docstring warns about in `test_reachability.py`.
"""

import re
from pathlib import Path

import pytest

from ai_stp_cli.provider import protocol_v3

#: Enough of the set to be an enumeration rather than an example.
ENUMERATION = 4

#: Generated, or an index over generated files. These are projections of the
#: owner, so repeating it is exactly what they are for.
GENERATED = (
    "provider-kit/",
    "docs/adr/index.md",
    "docs/index.md",
    "skills/projections/",
)

VOCABULARIES: tuple[frozenset[str], ...] = (
    frozenset(protocol_v3.COMMANDS),
    frozenset(operation.value for operation in protocol_v3.Operation),
)


def _documents() -> list[Path]:
    roots = (Path("docs"), Path("specs"))
    found = [path for root in roots for path in root.rglob("*.md") if path.is_file()]
    return [path for path in found if not any(mark in str(path) for mark in GENERATED)]


def _fenced_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    for body in re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL):
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if lines:
            blocks.append(lines)
    return blocks


def _first_column_runs(text: str) -> list[list[str]]:
    """Every run of consecutive table rows, by their first cell."""
    runs: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cell = stripped.strip("|").split("|")[0].strip().strip("`")
            current.append(cell)
            continue
        if current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def _enumerations(text: str, vocabulary: frozenset[str]) -> list[list[str]]:
    found: list[list[str]] = []
    for block in _fenced_blocks(text):
        named = [line for line in block if line in vocabulary]
        if len(named) >= ENUMERATION and len(named) == len(block):
            found.append(named)
    for run in _first_column_runs(text):
        named = [cell for cell in run if cell in vocabulary]
        if len(named) >= ENUMERATION:
            found.append(named)
    return found


@pytest.mark.parametrize("document", _documents(), ids=str)
def test_no_document_restates_the_closed_protocol_vocabulary(document: Path) -> None:
    text = document.read_text(encoding="utf-8")
    for vocabulary in VOCABULARIES:
        restated = _enumerations(text, vocabulary)
        assert not restated, (
            f"{document} enumerates the closed protocol v3 vocabulary: {restated}. "
            "The set belongs to provider-kit/v3/manifest.json, generated from "
            "protocol_v3.py. Reference it instead of copying it."
        )


def test_the_gate_recognises_an_enumeration_when_it_sees_one() -> None:
    """A gate nobody has watched fail is a gate nobody knows the shape of."""
    fenced = "```text\n" + "\n".join(protocol_v3.CORE_COMMANDS) + "\n```\n"
    assert _enumerations(fenced, frozenset(protocol_v3.COMMANDS))

    table = "| Operation | Kind |\n|---|---|\n" + "".join(
        f"| `{operation.value}` | core |\n" for operation in protocol_v3.CORE_OPERATIONS
    )
    assert _enumerations(table, frozenset(op.value for op in protocol_v3.Operation))

    prose = "`plan-operation` is pure and `apply-operation` takes its exact digest.\n"
    assert not _enumerations(prose, frozenset(protocol_v3.COMMANDS))
