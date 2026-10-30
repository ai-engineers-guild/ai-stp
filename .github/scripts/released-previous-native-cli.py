"""Verify an immutable released native consumer; never claim a new compilation."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, overload

REPOSITORY = "ai-engineers-guild/ai-stp"


@dataclass(frozen=True)
class Release:
    version: str
    tag_object: str
    source: str
    tree: str
    asset_id: int
    archive_bytes: int
    archive_sha256: str
    binary_bytes: int
    binary_sha256: str
    environment: str

    @property
    def tag(self) -> str:
        return f"cli-v{self.version}"

    @property
    def archive_name(self) -> str:
        return f"ai-stp-cli-{self.version}-x86_64-unknown-linux-gnu.tar.gz"


RELEASES = {
    60: Release(
        "0.2.1",
        "966d75b61c42e2516c87c020448aa441092b9e40",
        "3221fe08dc70630987c81997ede5af6454c988d2",
        "d8e39aad89ccdb8fa6d2043b8d561a4dd7f7eb1c",
        686946958,
        13_840_643,
        "077096f96c7f912e2dab0c4bfc35e8d0ed2f0361f551331c59fb71bfd975ab72",
        34_308_280,
        "5c19e71a6c21bac22decc19e717628d2564572465609914d30cede49625c103a",
        "LOCATION",
    ),
    61: Release(
        "0.2.2",
        "01220607e4f29adbf4f10f22077a2244039d9f2a",
        "1327533ccbfb8d1aa92ccdd346790246f8eac28c",
        "7bf99b51aa0e9ef169b5bb79974f2a52dad355af",
        691115795,
        13_944_526,
        "01cec61a5363447a4dd9adb0dc4b934a60797661aae2fded622ed8e4e870c73f",
        34_590_008,
        "047f806ba78dce3cab36caaa109a9c0209af7678ba4a5abbe8a4ab7aff150491",
        "MISSING_CHECKOUT",
    ),
}
SBOM = "ai-stp-cli.cdx.json"


@overload
def api(path: str, *, binary: Literal[False] = False) -> dict[str, Any]: ...


@overload
def api(path: str, *, binary: Literal[True]) -> bytes: ...


def api(path: str, *, binary: bool = False) -> dict[str, Any] | bytes:
    arguments = ["gh", "api", "--allow-escape-sequences"]
    if binary:
        arguments.extend(["-H", "Accept: application/octet-stream"])
    result = subprocess.run(
        [*arguments, f"repos/{REPOSITORY}/{path}"],
        capture_output=True,
        check=True,
        timeout=45,
    )
    if binary:
        return result.stdout
    metadata: dict[str, Any] = json.loads(result.stdout)
    assert isinstance(metadata, dict)
    return metadata


def archive(release: Release) -> bytes:
    ref = api(f"git/ref/tags/{release.tag}")
    assert ref["object"] == {"sha": release.tag_object, "type": "tag", "url": ref["object"]["url"]}
    tag = api(f"git/tags/{release.tag_object}")
    assert tag["tag"] == release.tag and tag["object"]["type"] == "commit"
    assert tag["object"]["sha"] == release.source
    assert api(f"git/commits/{release.source}")["tree"]["sha"] == release.tree
    published = api(f"releases/tags/{release.tag}")
    assert (
        published["tag_name"] == release.tag
        and not published["draft"]
        and not published["prerelease"]
    )
    assets = [item for item in published["assets"] if item["id"] == release.asset_id]
    assert len(assets) == 1
    asset = assets[0]
    assert asset["name"] == release.archive_name and asset["size"] == release.archive_bytes
    assert asset["digest"] == "sha256:" + release.archive_sha256
    data = api(f"releases/assets/{release.asset_id}", binary=True)
    assert (
        len(data) == release.archive_bytes
        and hashlib.sha256(data).hexdigest() == release.archive_sha256
    )
    return data


def executable(data: bytes, release: Release) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        assert len(members) == 4 and {member.name for member in members} == {
            "LICENSE",
            "ai-stp",
            "release.json",
            SBOM,
        }
        assert all(
            member.isfile() and 0 < member.size <= release.binary_bytes for member in members
        )
        files: dict[str, bytes] = {}
        for member in members:
            stream = archive.extractfile(member)
            assert stream is not None
            with stream:
                files[member.name] = stream.read(member.size + 1)
            assert len(files[member.name]) == member.size
        binary = files["ai-stp"]
        assert len(binary) == release.binary_bytes and binary.startswith(b"\x7fELF")
        assert archive.getmember("ai-stp").mode & 0o7777 == 0o755
        assert hashlib.sha256(binary).hexdigest() == release.binary_sha256
        manifest = json.loads(files["release.json"])
        assert manifest == {
            "schema_version": 2,
            "package": "ai-stp-cli",
            "version": release.version,
            "release_channel": "stable",
            "source_commit": release.source,
            "target": "x86_64-unknown-linux-gnu",
            "binary": "ai-stp",
            "binary_sha256": release.binary_sha256,
            "license_sha256": hashlib.sha256(files["LICENSE"]).hexdigest(),
            "sbom": SBOM,
            "sbom_sha256": hashlib.sha256(files[SBOM]).hexdigest(),
        }
        return binary


def prepare(root: Path, schema: int) -> None:
    release = RELEASES[schema]
    assert root.is_absolute() and root.parent.resolve() == Path(os.environ["RUNNER_TEMP"]).resolve()
    assert "\n" not in str(root) and "\r" not in str(root)
    binary = executable(archive(release), release)
    root.mkdir(mode=0o700)
    path = root / "ai-stp"
    with path.open("xb") as stream:
        stream.write(binary)
    path.chmod(0o755)
    assert stat.S_ISREG(path.lstat().st_mode) and path.stat().st_size == release.binary_bytes
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
    assert envelope["ok"] is True and envelope["data"]["cli_version"] == release.version
    paths = [tuple(command["path"]) for command in envelope["data"]["commands"]]
    assert len(paths) == len(set(paths))
    assert ("corporate", "project", "binding-retire", "plan") in paths
    assert (("corporate", "project", "location-anchor", "plan") in paths) == (schema == 61)
    assert ("corporate", "project", "binding-retire-missing", "plan") not in paths
    assert not any(home.iterdir()), "metadata inventory created persistent state"
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
        output.write(f"AI_STP_TEST_PREVIOUS_{release.environment}_CLI_BINARY={path}\n")
        output.write(f"AI_STP_TEST_PREVIOUS_{release.environment}_CLI_SOURCE={release.source}\n")
    print(
        json.dumps(
            {
                "previous_released_writer": schema,
                "release_tag": release.tag,
                "source_commit": release.source,
                "archive_sha256": release.archive_sha256,
                "binary_sha256": release.binary_sha256,
                "registry_digest": envelope["data"]["registry_digest"],
                "compiled_by_this_job": False,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--schema", type=int, choices=tuple(RELEASES), default=60)
    args = parser.parse_args()
    prepare(args.root, args.schema)
