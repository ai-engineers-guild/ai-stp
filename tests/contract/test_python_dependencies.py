"""Exercise the dependency boundary through the actual uv/deptry command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

DRIVER = Path(__file__).resolve().parents[2] / "release_scripts" / "python_dependencies.py"


def run_probe(
    tmp_path: Path,
    source: str,
    dependencies: tuple[str, ...] = (),
    extra_config: str = "",
) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "workspace with spaces"
    member = root / "packages" / "probe"
    (member / "src").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "ownership-root"\nversion = "0.0.0"\nrequires-python = ">=3.12"\n'
        '[tool.uv]\npackage = false\n[tool.uv.workspace]\nmembers = ["packages/*"]\n',
        encoding="utf-8",
    )
    (member / "pyproject.toml").write_text(
        '[project]\nname = "ownership-probe"\nversion = "0.0.0"\nrequires-python = ">=3.12"\n'
        f"dependencies = {json.dumps(dependencies)}\n{extra_config}",
        encoding="utf-8",
    )
    (member / "src" / "ownership_probe.py").write_text(source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(DRIVER)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def test_accepts_declared_runtime_dependency(tmp_path: Path) -> None:
    result = run_probe(tmp_path, "import pydantic\n", ("pydantic>=2",))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("source", "dependencies", "extra_config", "rule"),
    [
        ("import dependency_ownership_probe_missing\n", (), "", "DEP001"),
        ("import sys\n", ("pydantic>=2",), "", "DEP002"),
        ("import fastapi\nimport starlette\n", ("fastapi>=0.161.1",), "", "DEP003"),
        (
            "import pydantic\n",
            (),
            '[dependency-groups]\ndev = ["pydantic>=2"]\n',
            "DEP004",
        ),
        ("import tomllib\n", ("tomllib",), "", "DEP005"),
    ],
)
def test_rejects_dependency_ownership_errors(
    tmp_path: Path,
    source: str,
    dependencies: tuple[str, ...],
    extra_config: str,
    rule: str,
) -> None:
    result = run_probe(tmp_path, source, dependencies, extra_config)
    assert result.returncode != 0
    assert rule in result.stdout + result.stderr


def test_accepts_toml_11_with_the_selected_parser_companion(tmp_path: Path) -> None:
    result = run_probe(
        tmp_path,
        "import sys\n",
        ("pydantic>=2",),
        '[tool.deptry]\nper_rule_ignores = {\n DEP002 = ["pydantic"],\n}\n',
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_refuses_malformed_owner_metadata(tmp_path: Path) -> None:
    result = run_probe(tmp_path, "import sys\n", extra_config="[broken\n")
    assert result.returncode != 0
