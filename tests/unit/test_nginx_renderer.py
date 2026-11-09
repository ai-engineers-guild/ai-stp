"""The host renderer must stop before nginx when its source root is unavailable."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux host renderer")


def _render(
    tmp_path: Path, *, unavailable_root: bool, values: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bash = shutil.which("bash")
    assert bash is not None, "the Linux deployment contract requires Bash"
    commands = tmp_path / "commands"
    commands.mkdir()
    calls = tmp_path / "downstream-calls"
    nginx = commands / "nginx"
    nginx.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$AI_STP_NGINX_TEST_LOG"\n', encoding="utf-8"
    )
    nginx.chmod(0o700)
    environment_file = tmp_path / "empty.env"
    environment_file.write_text(
        "".join(f"{name}={value}\n" for name, value in (values or {}).items()), encoding="utf-8"
    )
    output = tmp_path / "output"
    output.mkdir()
    env = {
        "PATH": f"{commands}{os.pathsep}{os.environ['PATH']}",
        "AI_STP_ENV_FILE": str(environment_file),
        "AI_STP_NGINX_CONF_DIR": str(output),
        "AI_STP_NGINX_TEST_LOG": str(calls),
    }
    if unavailable_root:
        dirname = commands / "dirname"
        dirname.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$AI_STP_NGINX_TEST_MISSING_ROOT"\n', encoding="utf-8"
        )
        dirname.chmod(0o700)
        env["AI_STP_NGINX_TEST_MISSING_ROOT"] = str(tmp_path / "missing-root" / "deep" / "leaf")
        grep = commands / "grep"
        grep.write_text(
            '#!/bin/sh\nprintf "environment-read\\n" >> "$AI_STP_NGINX_TEST_LOG"\nexit 1\n',
            encoding="utf-8",
        )
        grep.chmod(0o700)
    result = subprocess.run(
        [bash, str(ROOT / "deploy/nginx/render.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    return result, calls


def test_empty_site_rehearsal_checks_and_reloads_nginx(tmp_path: Path) -> None:
    result, calls = _render(tmp_path, unavailable_root=False)
    assert result.returncode == 0, result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["-t", "-s reload"]
    assert not list((tmp_path / "output").iterdir())


def test_unavailable_source_root_refuses_before_nginx(tmp_path: Path) -> None:
    result, calls = _render(tmp_path, unavailable_root=True)
    assert "missing-root" in result.stderr
    assert result.returncode != 0
    assert not calls.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("AI_STP_PUBLIC_HOST", "example.invalid;return"),
        ("AI_STP_PUBLIC_HOST", "https://example.invalid/path"),
        ("AI_STP_DOCS_HOST", "docs.example.invalid|replacement"),
        ("AI_STP_API_BIND", "127.0.0.1:58082|replacement"),
        ("AI_STP_WEB_BIND", "localhost:70000"),
        ("AI_STP_DOCS_BIND", "localhost:0"),
        ("AI_STP_TLS_LINEAGE", "../another-site"),
        ("AI_STP_DOCS_TLS_LINEAGE", "fixture;directive"),
    ],
)
def test_unsafe_template_values_refuse_before_service_or_file_changes(
    tmp_path: Path, field: str, value: str
) -> None:
    values = {
        "AI_STP_PUBLIC_HOST": "example.invalid",
        "AI_STP_DOCS_HOST": "docs.example.invalid",
        "AI_STP_TLS_LINEAGE": "fixture",
        "AI_STP_DOCS_TLS_LINEAGE": "fixture",
        field: value,
    }
    result, calls = _render(tmp_path, unavailable_root=False, values=values)
    assert result.returncode == 2
    assert f"invalid {field}" in result.stderr
    assert not calls.exists()
    assert not list((tmp_path / "output").iterdir())
