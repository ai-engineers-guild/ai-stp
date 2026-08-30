"""What ships in the wheel (issue #77).

The gate already proves the wheel installs and runs (`just back-regress`). This
proves what is *inside* it: the licence a user is entitled to see, the declared
dependency tree, and the absence of anything that describes the machine it was
built on. A wheel carrying an absolute source path, a credential or a
per-checkout runtime marker is a wheel that leaked the developer's environment
into everyone's install.
"""

import ast
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Final

import pytest

ROOT = Path(__file__).parents[2]

#: The real locations of the machine running this, not a pattern that looks like
#: one. A generic `/home/<name>/` matcher flags the illustrative paths in
#: docstrings and proves nothing; these two strings are what an actual leak would
#: contain.
BUILD_MACHINE: tuple[str, ...] = (str(Path.home()), str(ROOT), str(Path(sys.prefix)))

#: Per-checkout state that `git-workflow-and-repository-facts` keeps out of
#: shared history for the same reason it must stay out of a wheel: it describes
#: one machine.
RUNTIME_MARKERS = (
    ".auto_sync_head",
    ".flow_blocker_ack.json",
    ".flow_post_task_state.json",
    ".flow_sync_marker",
    ".serena_sync_state.json",
)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--package", "ai-stp-cli", "--out-dir", str(out), "-q"],
        cwd=ROOT,
        check=True,
    )
    built = sorted(out.glob("*.whl"))
    assert built, "no wheel was produced"
    return built[0]


def _metadata(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        name = next(item for item in archive.namelist() if item.endswith("METADATA"))
        return archive.read(name).decode("utf-8")


def test_the_wheel_declares_the_project_licence(wheel: Path) -> None:
    metadata = _metadata(wheel)
    assert "License-Expression: AGPL-3.0-or-later" in metadata
    with zipfile.ZipFile(wheel) as archive:
        assert any(item.endswith("LICENSE") for item in archive.namelist())


#: Import name to distribution name, where the two differ. Everything else is
#: assumed to match, which is true for every remaining dependency here.
DISTRIBUTION_OF: Final[dict[str, str]] = {
    "ai_stp_assurance": "ai-stp-assurance",
    "yaml": "pyyaml",
    "ai_stp_contracts": "ai-stp-contracts",
    "ai_stp_foundation": "ai-stp-foundation",
    "ai_stp_passports": "ai-stp-passports",
}

#: Reasons on the record: `click` by `ADR-0057`, `cryptography` and `keyring` by
#: `ADR-0058`, `httpx` by `#75`, `pyyaml` for the configuration file, `pydantic`
#: for the wire and report models, `ai-stp-passports` for the passport envelope,
#: `ai-stp-assurance` for the signed attestation boundary, and `tomlkit` by
#: `ADR-0129` for format-preserving writes to a host file a component
#: contributes one key to — `tomllib` in the standard library only reads, and
#: writing values back would erase every comment the file's owner put there.
#: A name reaching this set without a reason is the thing to argue about.
ALLOWED_DEPENDENCIES: Final[frozenset[str]] = frozenset(
    {
        "ai-stp-assurance",
        "ai-stp-contracts",
        "ai-stp-foundation",
        "ai-stp-passports",
        "click",
        "cryptography",
        "httpx",
        "keyring",
        "pydantic",
        "pyyaml",
        "tomlkit",
    }
)


def _declared(wheel: Path) -> set[str]:
    return {
        line.removeprefix("Requires-Dist: ").split(">")[0].split("=")[0].strip()
        for line in _metadata(wheel).splitlines()
        if line.startswith("Requires-Dist: ")
    }


def _directly_imported() -> set[str]:
    """Every distribution the CLI sources import by name."""
    found: set[str] = set()
    for source in (ROOT / "apps" / "cli" / "src").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # A relative import is this package talking to itself.
                names = [node.module or ""] if not node.level else []
            else:
                continue
            for name in names:
                top = name.split(".", 1)[0]
                if not top or top in sys.stdlib_module_names or top == "ai_stp_cli":
                    continue
                found.add(DISTRIBUTION_OF.get(top, top))
    return found


def test_every_directly_imported_distribution_is_declared(wheel: Path) -> None:
    """Derived from the imports, not from a list kept by hand.

    The list was kept by hand, and it was wrong: `pydantic` and
    `ai-stp-passports` were imported directly and declared nowhere, arriving
    only because `ai-stp-contracts` happened to bring them. A refactor there
    would have broken this package at runtime without changing one line of its
    metadata, and the test asserting the incomplete set would have stayed green.
    """
    missing = _directly_imported() - _declared(wheel)
    assert not missing, f"imported but not declared: {sorted(missing)}"


def test_nothing_is_declared_that_is_not_imported(wheel: Path) -> None:
    """The other direction, so a dependency that stops being used is noticed."""
    unused = _declared(wheel) - _directly_imported()
    assert not unused, f"declared but not imported: {sorted(unused)}"


def test_no_dependency_arrives_without_a_recorded_reason(wheel: Path) -> None:
    assert _declared(wheel) <= ALLOWED_DEPENDENCIES


def test_the_wheel_names_a_console_entry_point(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        name = next(item for item in archive.namelist() if item.endswith("entry_points.txt"))
        assert "ai-stp = ai_stp_cli.app:run" in archive.read(name).decode("utf-8")


def test_the_wheel_carries_nothing_from_the_machine_that_built_it(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            content = archive.read(item).decode("utf-8", errors="replace")
            for location in BUILD_MACHINE:
                assert location not in item.filename, (item.filename, location)
                assert location not in content, (item.filename, location)


def test_the_wheel_carries_no_runtime_state_and_no_tests(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    for marker in RUNTIME_MARKERS:
        assert not any(marker in name for name in names), marker
    assert not any(name.startswith("tests/") for name in names)
    assert not any("/.serena/" in name or name.startswith(".serena/") for name in names)


def test_the_wheel_ships_the_typing_marker(wheel: Path) -> None:
    # Without it a consumer's type checker treats the package as untyped, and
    # the strict typing the gate enforces stops at the boundary.
    with zipfile.ZipFile(wheel) as archive:
        assert "ai_stp_cli/py.typed" in archive.namelist()


def test_the_version_output_identifies_the_build_without_a_path() -> None:
    # `#77`: the version answer carries CLI and schema identity and no build
    # path. It is what a bug report quotes.
    from ai_stp_cli.commands import version

    report = version.run({}).payload
    rendered = report.model_dump_json()
    assert report.wire_schema_version == 1
    for location in BUILD_MACHINE:
        assert location not in rendered, location


#: Names of model clients and their tokenisers. `SPEC-011` REQ-1118 and the hard
#: invariant in `AGENTS.md`: `ai_stp` calls no model interface and needs no model
#: key, and the absence of such a key must not degrade any function.
MODEL_CLIENTS = (
    "anthropic",
    "openai",
    "cohere",
    "mistralai",
    "litellm",
    "ollama",
    "google.generativeai",
    "google.genai",
    "langchain",
    "llama_index",
    "transformers",
    "tiktoken",
)


def test_no_source_file_reaches_for_a_model_client() -> None:
    # The dependency closure is checked in `just smoke-cli`, where the real
    # installed set exists. This is the other half: an import that would make
    # the CLI need one.
    for source in (ROOT / "apps").rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for client in MODEL_CLIENTS:
            root_module = client.split(".")[0]
            assert f"import {root_module}" not in text, (source.name, client)
            assert f"from {client}" not in text, (source.name, client)


def test_no_declared_configuration_field_can_hold_a_model_key() -> None:
    # `SPEC-003` REQ-308 as well as `SPEC-011` REQ-1118: the absence of a model
    # key must not degrade any function, so no field may ask for one.
    # A field named for a model key would make the absence of one a
    # configuration problem, which REQ-1118 forbids.
    from ai_stp_cli.config import declared_fields

    forbidden = ("model", "llm", "api_key", "anthropic", "openai")
    for field in declared_fields():
        assert not any(word in field.path.lower() for word in forbidden), field.path


def test_the_wheel_declares_no_model_client(wheel: Path) -> None:
    declared = {
        line.removeprefix("Requires-Dist: ").split(">")[0].split("=")[0].strip().lower()
        for line in _metadata(wheel).splitlines()
        if line.startswith("Requires-Dist: ")
    }
    for client in MODEL_CLIENTS:
        assert client.split(".")[0] not in declared, client
