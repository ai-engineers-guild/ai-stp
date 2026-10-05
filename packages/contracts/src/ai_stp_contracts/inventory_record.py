"""Generated record of the standard inventory (SPEC-060 REQ-6005, REQ-6006).

`ai-stp version` and `ai-stp contract inventory` report the contract digest.
Computing it renders the JSON Schema of every exported model and digests each
canonical body — about five hundred models, 4.2s of CPU per `version` call
against the 0.8s budget `#453` sets for a local read
(`docs/engineering/cli-performance.md`). The answer is a property of the
source, not of the call, so the generator writes it next to this module and
`back-static` refuses a record that differs from the models.

This module must stay cheap to import: reading the record is the whole point,
and `ai_stp_contracts.schemas` is imported only to regenerate or check it.
"""

from __future__ import annotations

import argparse
import sys
from importlib.resources import files
from pathlib import Path
from typing import Final

from ai_stp_contracts.standard import StandardInventory

RECORD_NAME: Final[str] = "standard_inventory.json"


def recorded() -> StandardInventory:
    """The inventory the generator recorded for this build."""
    text = files("ai_stp_contracts").joinpath(RECORD_NAME).read_text(encoding="utf-8")
    return StandardInventory.model_validate_json(text)


def render(inventory: StandardInventory) -> str:
    """Stable text form of one inventory, as written to the record."""
    return inventory.model_dump_json(indent=2) + "\n"


def _default_target() -> Path:
    return Path(__file__).with_name(RECORD_NAME)


def _current() -> str:
    from ai_stp_contracts.schemas import current_inventory

    return render(current_inventory())


def write(target: Path | None = None) -> Path:
    """Regenerate the record from the exported models."""
    path = target if target is not None else _default_target()
    path.write_text(_current(), encoding="utf-8", newline="\n")
    return path


def check(target: Path | None = None) -> list[str]:
    """Problems with the record; empty when it matches the models."""
    path = target if target is not None else _default_target()
    if not path.is_file():
        return [f"missing generated inventory record: {path}"]
    if path.read_text(encoding="utf-8") != _current():
        return [f"inventory record drifted from the exported models: {path}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    parser.add_argument("target", nargs="?", type=Path, help="record path")
    arguments = parser.parse_args(argv)
    if arguments.check:
        problems = check(arguments.target)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    print(write(arguments.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
