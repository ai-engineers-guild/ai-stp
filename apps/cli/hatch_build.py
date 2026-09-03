# pyright: reportMissingImports=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUntypedBaseClass=false
"""Bundle workspace runtime modules into the published ``ai-stp-cli`` artifacts.

The CLI remains a workspace member that imports ``ai_stp_foundation`` and
neighbours as ordinary packages. The public wheel cannot depend on those
projects on PyPI (`ADR-0146`), so the build copies their source trees into
the same artifact. Paths stay outside ``apps/cli/src`` in the checkout; they
are vendored into ``src/`` only inside the sdist so a rebuild from the sdist
sees the same modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from hatchling.builders.hooks.plugin.interface import (  # pyright: ignore[reportMissingImports]
    BuildHookInterface,
)

BUNDLED: Final[tuple[tuple[str, str], ...]] = (
    ("ai_stp_foundation", "packages/foundation/src/ai_stp_foundation"),
    ("ai_stp_passports", "packages/passports/src/ai_stp_passports"),
    ("ai_stp_assurance", "packages/assurance/src/ai_stp_assurance"),
    ("ai_stp_contracts", "packages/contracts/src/ai_stp_contracts"),
    ("ai_stp_sources", "packages/sources/src/ai_stp_sources"),
)


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        # Editable workspace installs must keep using the sibling packages.
        # Bundling here would copy those modules into site-packages and shadow
        # the live sources API, platform and tests import.
        if version == "editable":
            return
        root = Path(self.root).resolve()
        extra = build_data.setdefault("force_include", {})
        if not isinstance(extra, dict):
            raise TypeError("hatch force_include must be a mapping")
        for name, relative in BUNDLED:
            source = _source(root, name, relative)
            destination = name if self.target_name == "wheel" else f"src/{name}"
            extra.update(_files(source, destination))


def _source(root: Path, name: str, relative: str) -> Path:
    checkout = root.parents[1] / relative
    vendored = root / "src" / name
    if checkout.is_dir():
        return checkout
    if vendored.is_dir():
        return vendored
    raise OSError(f"bundled module {name} is missing from the CLI build")


def _files(source: Path, destination: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        mapping[str(path)] = str(Path(destination) / path.relative_to(source))
    if not mapping:
        raise OSError(f"bundled module {source} contains no files")
    return mapping
