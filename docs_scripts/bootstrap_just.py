#!/usr/bin/env python3
"""Скачать pinned just binary для CI без curl|bash installer."""

from __future__ import annotations

import hashlib
import http.client
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

VERSION = "1.43.0"

# SHA256 официальных архивов case-sensitive по имени asset из GitHub Releases.
# Если версии меняются, сначала обновляется эта таблица, потом CI.
SHA256 = {
    "just-1.43.0-x86_64-unknown-linux-musl.tar.gz": (
        "a1bc93654f31669fd964ea3011a5e5e9676b9b6f8adcd762606e5140632ea72d"
    ),
    "just-1.43.0-aarch64-unknown-linux-musl.tar.gz": (
        "4fcd8310081c32742eb984b1fdd0eee2e5d4d0f1be9629318012d42606ec9b3e"
    ),
    "just-1.43.0-aarch64-apple-darwin.tar.gz": (
        "bb0d35f6ca04709b798a19217693c16f4086170c580cc3b5c2531ad2794d2e32"
    ),
    "just-1.43.0-x86_64-apple-darwin.tar.gz": (
        "687f66a6bd4d7d946ef5ff1e3efebb3d39dadad151a8c6b1de884cc93adc06a5"
    ),
    "just-1.43.0-x86_64-pc-windows-msvc.zip": (
        "04be7b6d7f8419288ce75532f1962cee1756992e494e6c8063bb3ab8db21b52c"
    ),
    "just-1.43.0-aarch64-pc-windows-msvc.zip": (
        "4abcc7ac09473f01b6837738e6bb4c3cdc167d6ebfa6c2cfd8b5656aa1b03d6c"
    ),
}


#: Платформа к части имени asset. macOS здесь не потому, что там гоняется CI —
#: платный раннер снят по решению владельца, — а потому что без этого `just` не
#: поднимется у разработчика на Mac, и он упрётся ровно в ту же стену.
#:
#: Windows появился по той же причине и ещё по одной. Публичный кросс-платформенный
#: job ставил `just` через `choco`, то есть через community-фид без закрепления
#: контрольной суммы, и 2026-08-21 этот шаг упал, потратив сто пять секунд и не
#: сказав ничего: вывод уходил в `/dev/null`. Здесь тот же закреплённый архив с
#: тем же сравнением SHA256, что и на двух других системах.
ASSET_FOR = {
    ("linux", "x86_64"): f"just-{VERSION}-x86_64-unknown-linux-musl.tar.gz",
    ("linux", "aarch64"): f"just-{VERSION}-aarch64-unknown-linux-musl.tar.gz",
    ("darwin", "arm64"): f"just-{VERSION}-aarch64-apple-darwin.tar.gz",
    ("darwin", "x86_64"): f"just-{VERSION}-x86_64-apple-darwin.tar.gz",
    ("windows", "x86_64"): f"just-{VERSION}-x86_64-pc-windows-msvc.zip",
    ("windows", "arm64"): f"just-{VERSION}-aarch64-pc-windows-msvc.zip",
}

#: Одно и то же железо называется по-разному в зависимости от того, кто
#: спрашивает.
ALIASES = {"amd64": "x86_64", "aarch64": "aarch64", "arm64": "arm64"}

DOWNLOAD_ATTEMPTS = 4
RETRY_DELAYS_SECONDS = (5, 15, 30)

type Download = Callable[[str, Path], object]
type Sleep = Callable[[float], object]


def target_asset() -> str:
    system = platform.system().lower()
    machine = ALIASES.get(platform.machine().lower(), platform.machine().lower())
    if system == "linux" and machine == "arm64":
        machine = "aarch64"
    if system == "darwin" and machine == "aarch64":
        machine = "arm64"
    if system == "windows" and machine == "aarch64":
        machine = "arm64"
    asset = ASSET_FOR.get((system, machine))
    if asset is None:
        raise RuntimeError(f"unsupported CI platform: {platform.system()} {platform.machine()}")
    return asset


def download_verified(
    url: str,
    archive: Path,
    expected_sha256: str,
    *,
    download: Download = urllib.request.urlretrieve,
    sleep: Sleep = time.sleep,
) -> None:
    """Download one pinned asset, retrying only failures that may be transient."""
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        archive.unlink(missing_ok=True)
        try:
            download(url, archive)
        except urllib.error.HTTPError as error:
            if error.code < 500 or error.code >= 600 or attempt == DOWNLOAD_ATTEMPTS:
                raise
            _wait_before_retry(attempt, error, sleep)
            continue
        except (
            urllib.error.URLError,
            ConnectionError,
            TimeoutError,
            http.client.HTTPException,
        ) as error:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise
            _wait_before_retry(attempt, error, sleep)
            continue

        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise RuntimeError(f"SHA256 mismatch for {archive.name}: {actual}")
        return


def _wait_before_retry(attempt: int, error: BaseException, sleep: Sleep) -> None:
    delay = RETRY_DELAYS_SECONDS[attempt - 1]
    print(
        f"bootstrap_just: download attempt {attempt}/{DOWNLOAD_ATTEMPTS} failed "
        f"({type(error).__name__}); retrying in {delay}s",
        file=sys.stderr,
    )
    sleep(delay)


def main() -> int:
    asset = target_asset()
    expected = SHA256[asset]
    if expected.startswith("REPLACE_"):
        raise RuntimeError(f"missing SHA256 for {asset}")

    url = f"https://github.com/casey/just/releases/download/{VERSION}/{asset}"
    install_dir = Path(os.environ.get("JUST_INSTALL_DIR", "/usr/local/bin"))
    install_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        archive = tmp / asset
        download_verified(url, archive, expected)

        binary = "just.exe" if asset.endswith(".zip") else "just"
        extracted = tmp / binary
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as bundle:
                name = next((item for item in bundle.namelist() if Path(item).name == binary), None)
                if name is None:
                    raise RuntimeError("just binary not found in archive")
                extracted.write_bytes(bundle.read(name))
        else:
            with tarfile.open(archive, "r:gz") as tar:
                member = next((m for m in tar.getmembers() if Path(m.name).name == binary), None)
                if member is None:
                    raise RuntimeError("just binary not found in archive")
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError("just binary cannot be read from archive")
                extracted.write_bytes(source.read())

        target = install_dir / binary
        shutil.copy2(extracted, target)
        # Windows decides executability by extension, and `chmod` there accepts
        # only the read-only bit — asking for the POSIX bits is meaningless
        # rather than harmful, so it is simply not asked.
        if os.name != "nt":
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"bootstrap_just: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
