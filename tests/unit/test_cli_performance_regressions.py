"""Structural guards for the costs `#453` measured and removed.

Assert the underlying properties directly so runner load does not determine
whether a performance regression passes.
"""

import ast
import hashlib
import importlib
import pkgutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from threading import Barrier
from typing import Any, TypeAliasType

import pytest
from pydantic import BaseModel

import ai_stp_contracts
from ai_stp_cli.application import select
from ai_stp_cli.local import harnesses, project_index
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.model import ContractModel

@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def test_every_harness_is_asked_its_version_at_the_same_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every detection must start before any detection can finish."""
    # The timeout only bounds a deadlock when concurrency regresses; it is
    # not a performance budget for the runner.
    started = Barrier(len(harnesses.DETECTORS), timeout=10)

    def overlapping(detector: Any, **_kwargs: Any) -> Any:
        started.wait()
        return harnesses.Found(
            harness_id=detector.harness_id,
            title=detector.harness_id,
            support="supported",
            state="available",
            installations=(),
            configuration=None,
            reason="stubbed",
        )

    monkeypatch.setattr(harnesses, "detect", overlapping)
    found = harnesses.detect_all()

    # Concurrency must not reorder the answer: `map` yields in input order, and
    # a set of harnesses that arrives in completion order would make the output
    # depend on which program booted first.
    assert [item.harness_id for item in found] == [
        detector.harness_id for detector in harnesses.DETECTORS
    ]


def test_an_index_without_digests_says_so_rather_than_looking_truncated(
    tmp_path: Path,
) -> None:
    """`digest is None` must not have to mean two things at once.

    It already meant "too large to read". Letting it also mean "no hash was
    asked for" would leave a reader unable to tell an unread file from an
    unhashed one, so the index states which it is.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# b\n", encoding="utf-8")

    full = project_index.build(tmp_path)
    assert full.digested
    assert all(item.digest for item in full.entries)

    plain = project_index.build(tmp_path, digests=False)
    assert not plain.digested
    assert all(item.digest is None for item in plain.entries)
    # Everything the inventory is for is unchanged: the same files, the same
    # languages, the same sizes. Only the hash is absent.
    assert [(i.path, i.language, i.size_bytes) for i in plain.entries] == [
        (i.path, i.language, i.size_bytes) for i in full.entries
    ]


def test_assessing_eligibility_hashes_no_project_file(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command reads names, languages and `.git`, so it should hash nothing.

    Hashing was three quarters of its walk — 0.91s against 0.29s to read the
    same 4080 files — and no digest reached the answer. This asserts the
    absence directly rather than a duration, because the duration is a
    consequence of it and the absence is the thing that must not come back.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.go").write_text("package main\n", encoding="utf-8")

    hashed = 0
    real = hashlib.sha256

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal hashed
        hashed += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha256", counted)
    target = select._target(  # pyright: ignore[reportPrivateUsage]
        "claude-code", tmp_path, for_redistribution=False, owner_id="account_01J" + "0" * 20 + "FAR"
    )
    assert hashed == 0
    # And the languages still arrive — this is the capability set the engine
    # refuses components on, so an empty one would pass this test for the
    # wrong reason.
    assert "project.language.python" in target.capabilities
    assert "project.language.go" in target.capabilities


def test_version_reads_the_recorded_inventory_instead_of_rendering_schemas() -> None:
    """`version` and `contract inventory` must not import the schema generator.

    The contract digest digests the JSON Schema of every exported model. Doing
    that per call cost 4.2s of CPU against 0.41s once the generated record
    answered instead (Linux, Python 3.14.7) — `version` is the first probe an
    agent or the desktop shell runs. Asserted as the absence of the import,
    which is the cause, rather than as a duration, which is its symptom.
    """
    probe = (
        "import sys\n"
        "from ai_stp_cli.commands import contract, version\n"
        "version.run({})\n"
        "contract.inventory({})\n"
        "print('ai_stp_contracts.schemas' in sys.modules)\n"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == "False", finished.stderr


def test_every_contract_model_defers_its_build() -> None:
    """Every contract model builds on first use, normally through `ContractModel`.

    The CLI imports about five hundred contract models before it runs any
    command, and building them all was about half a second of each invocation
    (1.65s against 0.93s of user CPU for `version --json`). After the import,
    only the few models the command registry instantiates are built. A model
    declared on `BaseModel` directly would build eagerly again; it is named here.
    """
    eager = sorted(
        f"{value.__module__}.{value.__qualname__}"
        for info in pkgutil.walk_packages(ai_stp_contracts.__path__, "ai_stp_contracts.")
        for value in vars(importlib.import_module(info.name)).values()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value.__module__ == info.name
        and value is not ContractModel
        and not value.model_config.get("defer_build")
    )
    assert eager == []


def test_a_local_command_does_not_import_the_http_stack() -> None:
    """The post-command heartbeat and update checks read local state only.

    Both ran after every command and imported httpx at module level, about a
    twentieth of a second each time; the network code now imports it when a
    heartbeat is due or the update cache has expired.
    """
    probe = (
        "import sys\n"
        "from ai_stp_cli.app import main\n"
        "sys.argv = ['ai-stp', 'version', '--json']\n"
        "try:\n"
        "    main()\n"
        "except SystemExit:\n"
        "    pass\n"
        "print('httpx' in sys.modules, file=sys.stderr)\n"
    )
    finished = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert finished.stderr.strip().splitlines()[-1] == "False", finished.stderr


@pytest.mark.parametrize(
    "argv",
    [
        ["version", "--json"],
        ["capabilities", "--json"],
        ["help", "--agent"],
        ["config", "show", "--json"],
    ],
)
def test_a_local_command_loads_only_the_contract_families_it_uses(argv: list[str]) -> None:
    """An agent's first probes import their own family, not the whole contract.

    Every invocation used to import `ai_stp_contracts.machine_help` — 215
    definitions and the catalog, corporate, publication and technology contracts
    behind them — and the package root imported seven more modules eagerly:
    about 0.5s of the 1.1s of user CPU `version --json` cost. `capabilities`
    also imported the doctor checks and task-intent models it never used. The
    families loaded here are the registry every command needs, `runtime` for
    `version` and `config show`, and `identity` and `self_update` for the
    checks that end each command.
    """
    probe = (
        "import sys\n"
        "from ai_stp_cli.app import main\n"
        f"sys.argv = ['ai-stp', *{argv!r}]\n"
        "try:\n"
        "    main()\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(','.join(sorted(sys.modules)), file=sys.stderr)\n"
    )
    finished = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    loaded = set(finished.stderr.strip().splitlines()[-1].split(","))
    assert "ai_stp_contracts.machine_help" not in loaded
    assert "ai_stp_contracts.catalog" not in loaded
    families = {
        name.removeprefix("ai_stp_contracts.cli.")
        for name in loaded
        if name.startswith("ai_stp_contracts.cli.")
    }
    assert families == {"identity", "registry", "runtime", "self_update"}


def test_the_contract_package_root_names_load_from_their_modules() -> None:
    """The root keeps its exported names without importing their modules.

    Three lists describe one export set: the `TYPE_CHECKING` imports type
    checkers read, the map `__getattr__` loads from, and `__all__`. A name
    added to one and not the others would type-check and then fail at runtime,
    or load and be invisible to a type checker.
    """
    source = Path(ai_stp_contracts.__file__).read_text(encoding="utf-8")
    guarded = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.If) and ast.unparse(node.test) == "TYPE_CHECKING"
    )
    imported = {
        (statement.module, alias.name)
        for statement in guarded.body
        if isinstance(statement, ast.ImportFrom)
        for alias in statement.names
    }
    mapped = {
        (f"ai_stp_contracts.{module}", name)
        for module, names in ai_stp_contracts._EXPORTS.items()  # pyright: ignore[reportPrivateUsage]
        for name in names
    }
    assert imported == mapped
    assert sorted(ai_stp_contracts.__all__) == sorted(name for _, name in mapped)
    for module, name in sorted(mapped):
        assert getattr(ai_stp_contracts, name) is getattr(importlib.import_module(module), name)


def test_machine_help_re_exports_every_contract_family_name() -> None:
    """The aggregate is what the schema generator and the platform read.

    A definition added to an `ai_stp_contracts.cli` family and not to
    `machine_help` would be a payload the CLI returns and no published schema
    describes.
    """
    from ai_stp_contracts import cli, machine_help

    defined = {
        name
        for info in pkgutil.iter_modules(cli.__path__, "ai_stp_contracts.cli.")
        for name, value in vars(importlib.import_module(info.name)).items()
        if not name.startswith("_")
        and getattr(value, "__module__", None) == info.name
        and isinstance(value, type | TypeAliasType)
    }
    assert sorted(machine_help.__all__) == sorted(defined)
