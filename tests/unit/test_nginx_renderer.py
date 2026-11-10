"""Exercise host renderer boundaries without touching host configuration or nginx."""

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
    tmp_path: Path,
    *,
    unavailable_root: bool,
    values: dict[str, str] | None = None,
    export_values: bool = False,
    certificate: bool = False,
    fail: str | None = None,
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
        ""
        if export_values
        else "".join(f"{name}={value}\n" for name, value in (values or {}).items()),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    env = {
        "PATH": f"{commands}{os.pathsep}{os.environ['PATH']}",
        "AI_STP_ENV_FILE": str(environment_file),
        "AI_STP_NGINX_CONF_DIR": str(output),
        "AI_STP_NGINX_TEST_LOG": str(calls),
    }
    if export_values:
        env.update(values or {})
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
    script = ROOT / "deploy/nginx/render.sh"
    if certificate:
        # The shell still checks a real file. Redirect only its system certificate directory.
        fixture = tmp_path / "checkout/deploy/nginx"
        fixture.mkdir(parents=True)
        for template in script.parent.glob("*.conf.template"):
            shutil.copyfile(template, fixture / template.name)
        certificates = tmp_path / "certificates"
        chain = certificates / "example.invalid/fullchain.pem"
        chain.parent.mkdir(parents=True)
        chain.write_text("fixture certificate\n", encoding="utf-8")
        source = script.read_text(encoding="utf-8")
        assert source.count("/etc/letsencrypt/live/") == 1
        script = fixture / script.name
        script.write_text(
            source.replace("/etc/letsencrypt/live/", f"{certificates}/"), encoding="utf-8"
        )
    if fail:
        command = commands / fail
        command.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        command.chmod(0o700)
    result = subprocess.run(
        [bash, str(script)],
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
        ("AI_STP_API_BIND", "127.0.0.1:00000"),
        ("AI_STP_TLS_LINEAGE", ".."),
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


def test_multiline_host_environment_refuses_before_nginx(tmp_path: Path) -> None:
    result, calls = _render(
        tmp_path,
        unavailable_root=False,
        values={"AI_STP_PUBLIC_HOST": "example.invalid\nother.invalid"},
        export_values=True,
    )
    assert result.returncode == 2
    assert "invalid AI_STP_PUBLIC_HOST" in result.stderr
    assert not calls.exists()
    assert not list((tmp_path / "output").iterdir())


@pytest.mark.parametrize(
    ("hosts", "bind"),
    [
        ("  http://example.invalid\tHTTPS://www.example.invalid  ", "localhost:1"),
        ("*.example.invalid .example.invalid _", "[::1]:65535"),
        ("[2001:db8::1]", "127.0.0.1:05808"),
    ],
)
def test_supported_host_and_upstream_shapes_reach_certificate_check(
    tmp_path: Path, hosts: str, bind: str
) -> None:
    lineage = f"ai-stp-missing-test-{tmp_path.name}"
    result, calls = _render(
        tmp_path,
        unavailable_root=False,
        values={
            "AI_STP_PUBLIC_HOST": hosts,
            "AI_STP_TLS_LINEAGE": lineage,
            "AI_STP_API_BIND": bind,
        },
    )
    assert result.returncode == 1, result.stderr
    assert f"no certificate under lineage '{lineage}'" in result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["-t", "-s reload"]
    assert not list((tmp_path / "output").iterdir())


def _existing_route(tmp_path: Path) -> Path:
    target = tmp_path / "output/zz-ai-stp-example.invalid.conf"
    target.parent.mkdir()
    target.write_bytes(b"previous route\n")
    target.chmod(0o640)
    os.setxattr(target, "user.ai_stp_test", b"retained")
    return target


@pytest.mark.parametrize("failure", ["mktemp", "sed", "cp", "sync", "mv"])
def test_existing_route_survives_install_failure(tmp_path: Path, failure: str) -> None:
    target = _existing_route(tmp_path)
    original = target.stat()
    result, calls = _render(
        tmp_path,
        unavailable_root=False,
        values={"AI_STP_PUBLIC_HOST": "example.invalid"},
        certificate=True,
        fail=failure,
    )
    assert result.returncode == 2, result.stderr
    assert target.read_bytes() == b"previous route\n"
    assert target.stat().st_ino == original.st_ino
    assert target.stat().st_mode == original.st_mode
    assert os.getxattr(target, "user.ai_stp_test") == b"retained"
    assert list(target.parent.iterdir()) == [target]
    assert not calls.exists()


def test_existing_route_is_replaced_with_its_attributes(tmp_path: Path) -> None:
    target = _existing_route(tmp_path)
    original = target.stat()
    result, calls = _render(
        tmp_path,
        unavailable_root=False,
        values={
            "AI_STP_PUBLIC_HOST": "example.invalid",
            "AI_STP_DOCS_HOST": "docs.example.invalid",
        },
        certificate=True,
    )
    assert result.returncode == 1, result.stderr
    assert "no certificate" in result.stderr
    assert "server_name example.invalid;" in target.read_text(encoding="utf-8")
    replacement = target.stat()
    assert replacement.st_ino != original.st_ino
    assert (replacement.st_uid, replacement.st_gid, replacement.st_mode) == (
        original.st_uid,
        original.st_gid,
        original.st_mode,
    )
    assert os.getxattr(target, "user.ai_stp_test") == b"retained"
    assert list(target.parent.iterdir()) == [target]
    assert calls.read_text(encoding="utf-8").splitlines() == ["-t", "-s reload"]


@pytest.mark.parametrize("link", ["symbolic", "hard"])
def test_route_links_refuse_before_any_replacement(tmp_path: Path, link: str) -> None:
    target = _existing_route(tmp_path)
    other = target.with_name("other.conf")
    target.rename(other)
    if link == "symbolic":
        target.symlink_to(other)
    else:
        target.hardlink_to(other)
    result, calls = _render(
        tmp_path,
        unavailable_root=False,
        values={"AI_STP_PUBLIC_HOST": "example.invalid"},
        certificate=True,
    )
    assert result.returncode == 2, result.stderr
    assert "regular file with one link" in result.stderr
    assert target.samefile(other)
    assert other.read_bytes() == b"previous route\n"
    assert not calls.exists()


@pytest.mark.skipif(
    not shutil.which("setfacl") or not shutil.which("getfacl"),
    reason="requires the native ACL tools",
)
def test_replacing_a_route_preserves_its_access_list(tmp_path: Path) -> None:
    target = _existing_route(tmp_path)
    subprocess.run(["setfacl", "-m", "u:65534:r--", str(target)], check=True, capture_output=True)
    command = ["getfacl", "-cp", str(target)]
    expected = subprocess.check_output(command)
    result, _ = _render(
        tmp_path,
        unavailable_root=False,
        values={"AI_STP_PUBLIC_HOST": "example.invalid"},
        certificate=True,
    )
    assert result.returncode == 0, result.stderr
    assert b"user:nobody:r--" in expected or b"user:65534:r--" in expected
    assert subprocess.check_output(command) == expected
