"""An owned PostgreSQL SDK and cluster for disposable macOS/Windows API consumers."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import stat
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from tests.support.native_runner import disposable_runner, report_stage


def run_command(program: Path, *arguments: str, input_data: bytes | None = None) -> str:
    # Daemon launchers use a file so descendants cannot hold pipe EOF open.
    # Only foreground initdb uses private stdin and in-memory output; detaching
    # its console makes PostgreSQL's non-echoing prompt read that owned pipe.
    private_input = input_data is not None
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(
                [str(program), *arguments],
                stdin=None if private_input else subprocess.DEVNULL,
                input=input_data,
                stdout=subprocess.PIPE if private_input else output,
                stderr=subprocess.STDOUT,
                start_new_session=private_input and os.name != "nt",
                creationflags=subprocess.CREATE_NO_WINDOW
                if private_input and os.name == "nt"
                else 0,
                timeout=90,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("PostgreSQL command exceeded its time bound") from None
        if private_input:
            payload = result.stdout
            assert input_data is not None
            assert not any(line and line in payload for line in input_data.splitlines()), (
                "PostgreSQL command echoed private input"
            )
        else:
            output.seek(0)
            payload = output.read(64 * 1024 + 1)
    assert len(payload) <= 64 * 1024, "PostgreSQL command output exceeded its bound"
    text = payload.decode("utf-8", errors="replace")
    assert result.returncode == 0, (
        program.name,
        result.returncode,
        "Private input command failed" if private_input else text[-4096:],
    )
    return text


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _windows_sdk(root: Path, pin: dict[str, Any]) -> Path:
    archive = root / pin["file"]
    with urllib.request.urlopen(pin["url"], timeout=60) as response, archive.open("xb") as output:
        assert response.url == pin["url"], "PostgreSQL archive changed origin"
        size = 0
        deadline = time.monotonic() + 180
        while chunk := response.read(1024 * 1024):
            assert time.monotonic() < deadline, "PostgreSQL download exceeded its time bound"
            size += len(chunk)
            assert size <= pin["size"]
            output.write(chunk)
    assert size == pin["size"] and _digest(archive) == pin["sha256"]
    with zipfile.ZipFile(archive) as bundle:
        selected = [
            item
            for item in bundle.infolist()
            if item.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/"))
            or item.filename
            in {"pgsql/server_license.txt", "pgsql/commandlinetools_3rd_party_licenses.txt"}
        ]
        assert 0 < len(selected) <= 2000
        assert sum(item.file_size for item in selected) <= 160 * 1024 * 1024
        seen: set[str] = set()
        for item in selected:
            path = PurePosixPath(item.filename)
            assert not path.is_absolute() and all(part not in {".", ".."} for part in path.parts)
            assert "\\" not in item.filename and ":" not in item.filename
            assert stat.S_IFMT(item.external_attr >> 16) != stat.S_IFLNK
            assert item.filename.casefold() not in seen
            seen.add(item.filename.casefold())
            target = root / path
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
    return root / "pgsql"


def _macos_sdk(root: Path, pin: dict[str, Any]) -> Path:
    archive = Path(os.environ["AI_STP_POSTGRESQL_ASSETS"]) / pin["file"]
    assert archive.is_file() and not archive.is_symlink()
    assert archive.stat().st_size == pin["size"] and _digest(archive) == pin["sha256"]
    mount = root / "mount"
    mount.mkdir()
    run_command(
        Path("/usr/bin/hdiutil"),
        "attach",
        "-readonly",
        "-nobrowse",
        "-mountpoint",
        str(mount),
        str(archive),
    )
    marker = root / "mounted"
    marker.touch()
    try:
        source = mount / "Postgres.app/Contents/Versions/18"
        assert source.is_dir() and not source.is_symlink()
        target = root / "pgsql"
        shutil.copytree(source, target, symlinks=True)
        return target
    finally:
        run_command(Path("/usr/bin/hdiutil"), "detach", str(mount))
        marker.unlink()


@contextmanager
def cluster() -> Generator[tuple[str, dict[str, Any]], None, None]:
    """Keep database and SDK lifecycle inside the admitted native fixture owner."""
    disposable_runner()
    native_os = os.environ["RUNNER_OS"]
    assert native_os in {"macOS", "Windows"}
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    assert temporary.is_dir()
    declaration = Path(f".github/postgresql-{native_os}.json")
    document = json.loads(declaration.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1 and len(document["assets"]) == 1
    pin = document["assets"][0]
    root = Path(tempfile.mkdtemp(prefix="ai-stp-postgresql-", dir=temporary))
    pg_ctl: Path | None = None
    data = root / "data"
    try:
        report_stage("postgresql-sdk")
        sdk = _macos_sdk(root, pin) if native_os == "macOS" else _windows_sdk(root, pin)
        suffix = ".exe" if platform.system() == "Windows" else ""
        postgres, initdb, pg_ctl = (
            sdk / "bin" / (name + suffix) for name in ["postgres", "initdb", "pg_ctl"]
        )
        version = run_command(postgres, "--version").strip()
        assert re.fullmatch(
            r"postgres \(PostgreSQL\) " + re.escape(document["postgresql_version"]) + r"(?:\s.*)?",
            version,
        ), version
        password = secrets.token_hex(24)
        report_stage("postgresql-initialize")
        run_command(
            initdb,
            "-D",
            str(data),
            "-U",
            "ai_stp_fixture",
            "--pwprompt",
            "--auth-host=scram-sha-256",
            "--auth-local=scram-sha-256",
            "--encoding=UTF8",
            "--locale=C",
            input_data=((password + "\n") * 2).encode("ascii"),
        )
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        report_stage("postgresql-start")
        run_command(
            pg_ctl,
            "-D",
            str(data),
            "-l",
            str(root / "postgresql.log"),
            "-w",
            "-t",
            "30",
            "-o",
            f"-h 127.0.0.1 -p {port} -c unix_socket_directories=",
            "start",
        )
        yield (
            f"postgresql+asyncpg://ai_stp_fixture:{password}@127.0.0.1:{port}/postgres",
            {
                "version": document["postgresql_version"],
                "archive_sha256": pin["sha256"],
                "server_sha256": _digest(postgres),
                "native_os": native_os,
                "loopback_only": True,
                "ephemeral_cluster": True,
            },
        )
    finally:
        if pg_ctl is not None and (data / "postmaster.pid").exists():
            report_stage("postgresql-stop")
            run_command(pg_ctl, "-D", str(data), "-w", "-t", "30", "-m", "fast", "stop")
        assert not (data / "postmaster.pid").exists(), (
            "Retain the owned cluster while its process is active"
        )
        assert not (root / "mounted").exists(), "Retain the SDK mount until native detach completes"
        shutil.rmtree(root)
