"""Verify the immutable released schema60 consumer; never claim a new compilation."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path
from typing import Any

REPOSITORY = "ai-engineers-guild/ai-stp"
TAG = "cli-v0.2.1"
TAG_OBJECT = "966d75b61c42e2516c87c020448aa441092b9e40"
SOURCE = "3221fe08dc70630987c81997ede5af6454c988d2"
TREE = "d8e39aad89ccdb8fa6d2043b8d561a4dd7f7eb1c"
ASSET_ID = 686946958
ARCHIVE_NAME = "ai-stp-cli-0.2.1-x86_64-unknown-linux-gnu.tar.gz"
ARCHIVE_BYTES = 13_840_643
ARCHIVE_SHA256 = "077096f96c7f912e2dab0c4bfc35e8d0ed2f0361f551331c59fb71bfd975ab72"
BINARY_BYTES = 34_308_280
BINARY_SHA256 = "5c19e71a6c21bac22decc19e717628d2564572465609914d30cede49625c103a"
SBOM = "ai-stp-cli.cdx.json"


def api(path: str, *, binary: bool = False) -> Any:
    arguments = ["gh", "api", "--allow-escape-sequences"]
    if binary:
        arguments.extend(["-H", "Accept: application/octet-stream"])
    result = subprocess.run(
        [*arguments, f"repos/{REPOSITORY}/{path}"],
        capture_output=True,
        check=True,
        timeout=45,
    )
    return result.stdout if binary else json.loads(result.stdout)


def archive() -> bytes:
    ref = api(f"git/ref/tags/{TAG}")
    assert ref["object"] == {"sha": TAG_OBJECT, "type": "tag", "url": ref["object"]["url"]}
    tag = api(f"git/tags/{TAG_OBJECT}")
    assert tag["tag"] == TAG and tag["object"]["type"] == "commit"
    assert tag["object"]["sha"] == SOURCE
    assert api(f"git/commits/{SOURCE}")["tree"]["sha"] == TREE
    release = api(f"releases/tags/{TAG}")
    assert release["tag_name"] == TAG and not release["draft"] and not release["prerelease"]
    assets = [item for item in release["assets"] if item["id"] == ASSET_ID]
    assert len(assets) == 1
    asset = assets[0]
    assert asset["name"] == ARCHIVE_NAME and asset["size"] == ARCHIVE_BYTES
    assert asset["digest"] == "sha256:" + ARCHIVE_SHA256
    data = api(f"releases/assets/{ASSET_ID}", binary=True)
    assert len(data) == ARCHIVE_BYTES and hashlib.sha256(data).hexdigest() == ARCHIVE_SHA256
    return data


def executable(data: bytes) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        assert len(members) == 4 and {member.name for member in members} == {
            "LICENSE",
            "ai-stp",
            "release.json",
            SBOM,
        }
        assert all(member.isfile() and 0 < member.size <= BINARY_BYTES for member in members)
        files: dict[str, bytes] = {}
        for member in members:
            stream = archive.extractfile(member)
            assert stream is not None
            with stream:
                files[member.name] = stream.read(member.size + 1)
            assert len(files[member.name]) == member.size
        binary = files["ai-stp"]
        assert len(binary) == BINARY_BYTES and binary.startswith(b"\x7fELF")
        assert archive.getmember("ai-stp").mode & 0o7777 == 0o755
        assert hashlib.sha256(binary).hexdigest() == BINARY_SHA256
        manifest = json.loads(files["release.json"])
        assert manifest == {
            "schema_version": 2,
            "package": "ai-stp-cli",
            "version": "0.2.1",
            "release_channel": "stable",
            "source_commit": SOURCE,
            "target": "x86_64-unknown-linux-gnu",
            "binary": "ai-stp",
            "binary_sha256": BINARY_SHA256,
            "license_sha256": hashlib.sha256(files["LICENSE"]).hexdigest(),
            "sbom": SBOM,
            "sbom_sha256": hashlib.sha256(files[SBOM]).hexdigest(),
        }
        return binary


def prepare(root: Path) -> None:
    assert root.is_absolute() and root.parent.resolve() == Path(os.environ["RUNNER_TEMP"]).resolve()
    assert "\n" not in str(root) and "\r" not in str(root)
    binary = executable(archive())
    root.mkdir(mode=0o700)
    path = root / "ai-stp"
    with path.open("xb") as stream:
        stream.write(binary)
    path.chmod(0o755)
    assert stat.S_ISREG(path.lstat().st_mode) and path.stat().st_size == BINARY_BYTES
    home = root / "qualification-home"
    home.mkdir(mode=0o700)
    environment = {
        key: str(home)
        for key in ("HOME", "USERPROFILE", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")
    }
    environment["PATH"] = ""
    report = subprocess.run(
        [str(path), "help", "--json"],
        cwd=home,
        env=environment,
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert not report.stderr and len(report.stdout) <= 1024 * 1024
    envelope = json.loads(report.stdout)
    assert envelope["ok"] is True and envelope["data"]["cli_version"] == "0.2.1"
    paths = [tuple(command["path"]) for command in envelope["data"]["commands"]]
    assert len(paths) == len(set(paths))
    assert ("corporate", "project", "binding-retire", "plan") in paths
    assert ("corporate", "project", "location-anchor", "plan") not in paths
    assert not any(home.iterdir()), "metadata inventory created persistent state"
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
        output.write(f"AI_STP_TEST_PREVIOUS_LOCATION_CLI_BINARY={path}\n")
        output.write(f"AI_STP_TEST_PREVIOUS_LOCATION_CLI_SOURCE={SOURCE}\n")
    print(
        json.dumps(
            {
                "previous_released_writer": 60,
                "release_tag": TAG,
                "source_commit": SOURCE,
                "archive_sha256": ARCHIVE_SHA256,
                "binary_sha256": BINARY_SHA256,
                "registry_digest": envelope["data"]["registry_digest"],
                "compiled_by_this_job": False,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    prepare(parser.parse_args().root)
