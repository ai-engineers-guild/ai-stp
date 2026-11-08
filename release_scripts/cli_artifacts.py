"""Seal qualified native CLI payloads and stage identical bytes without rebuilding."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import re
import shutil
from pathlib import Path

from release_scripts._github_delivery import GitHub, PromotionRefused, require

PLATFORMS = {
    "x86_64-unknown-linux-gnu": ("tar.gz", "manylinux_2_43_x86_64"),
    "aarch64-apple-darwin": ("tar.gz", "macosx_15_0_arm64"),
    "x86_64-pc-windows-msvc": ("zip", "win_amd64"),
}


def names(version: str, target: str) -> set[str]:
    require(
        bool(re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version)),
        "Stable CLI version required",
    )
    require(target in PLATFORMS, "Unknown native CLI target")
    extension, platform = PLATFORMS[target]
    files = {
        f"ai-stp-cli-{version}-{target}.{extension}",
        f"ai_stp-{version}-py3-none-{platform}.whl",
    }
    if target == "x86_64-unknown-linux-gnu":
        files.add(f"ai-stp-cli-{version}.crate")
    return files | {name + ".sha256" for name in files}


def require_published(api: GitHub, head: str) -> None:
    """Admit the qualified source's public download before changing deploy/prod."""
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head)), "Exact qualified source required")
    document = api.read("contents/packages/contracts/src/ai_stp_contracts/cli_copy.py?ref=" + head)
    require(document["encoding"] == "base64", "Encoded CLI download source required")
    source = base64.b64decode("".join(document["content"].split()), validate=True)
    values = [
        node.value.value
        for node in ast.parse(source).body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "CLI_RELEASES_URL"
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    require(len(values) == 1, "One literal native CLI release link required")
    match = re.fullmatch(
        r"https://github.com/ai-engineers-guild/ai-stp/releases/tag/cli-v"
        r"((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))",
        values[0],
    )
    if match is None:
        raise PromotionRefused("Canonical stable native CLI release link required")
    version = match[1]
    tag = "cli-v" + version
    release = api.read("releases/tags/" + tag)
    require(
        release["tag_name"] == tag
        and release["draft"] is False
        and release["prerelease"] is False
        and bool(release["published_at"]),
        "CLI release is not completely published",
    )
    expected = {name for target in PLATFORMS for name in names(version, target)}
    assets = release["assets"]
    require(
        len(assets) == len(expected) == 14
        and {asset["name"] for asset in assets} == expected
        and all(
            asset["state"] == "uploaded"
            and asset["size"] > 0
            and re.fullmatch(r"sha256:[0-9a-f]{64}", asset["digest"] or "")
            for asset in assets
        ),
        "Complete uploaded CLI release assets and digests required",
    )
    reference = api.read("git/ref/tags/" + tag)["object"]
    require(reference["type"] == "tag", "Annotated CLI release tag required")
    tagged = api.read("git/tags/" + reference["sha"])
    require(
        tagged["tag"] == tag and tagged["object"]["type"] == "commit",
        "CLI release annotation differs",
    )
    comparison = api.read("compare/" + tagged["object"]["sha"] + "..." + head)
    require(comparison["status"] in {"ahead", "identical"}, "CLI release outside source history")
    print(f"Published native CLI {tag}: all 14 assets; source ancestry accepted")


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), "Regular CLI payload files required")
    require(0 < path.stat().st_size <= 256 * 1024 * 1024, "CLI payload exceeds its boundary")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def seal(directory: Path, head: str, version: str, target: str) -> None:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head)), "Exact qualified source required")
    expected = names(version, target)
    require(
        {path.name for path in directory.iterdir()} == expected,
        "CLI source payload inventory differs",
    )
    proof = {
        "schema_version": 1,
        "source_sha": head,
        "version": version,
        "target": target,
        "files": {name: digest(directory / name) for name in sorted(expected)},
    }
    with (directory / f"qualification-{target}.json").open("x") as stream:
        json.dump(proof, stream, sort_keys=True)


def verify(directory: Path, output: Path, head: str, version: str) -> None:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head)), "Exact qualified source required")
    expected = set().union(*(names(version, target) for target in PLATFORMS))
    manifests = {f"qualification-{target}.json" for target in PLATFORMS}
    require(
        {path.name for path in directory.iterdir()} == expected | manifests,
        "Exactly three qualified native CLI payloads are required",
    )
    for target in PLATFORMS:
        path = directory / f"qualification-{target}.json"
        require(
            not path.is_symlink() and path.stat().st_size <= 16 * 1024,
            "Invalid CLI qualification inventory",
        )
        proof = json.loads(path.read_bytes())
        require(
            proof.get("schema_version") == 1
            and proof.get("source_sha") == head
            and proof.get("version") == version
            and proof.get("target") == target,
            "CLI inventory is not this qualified source",
        )
        files = proof.get("files")
        require(
            isinstance(files, dict) and set(files) == names(version, target),
            "CLI qualification file inventory differs",
        )
        for name, expected_digest in files.items():
            require(digest(directory / name) == expected_digest, "Qualified CLI bytes changed")
            if name.endswith(".sha256"):
                payload = name.removesuffix(".sha256")
                checksum = (directory / name).read_text().strip()
                require(
                    checksum == f"{files[payload]}  {payload}",
                    "CLI checksum differs from its qualified payload",
                )
    require(not output.exists(), "Publication staging directory must be new")
    output.mkdir(parents=True, mode=0o700)
    for name in sorted(expected):
        shutil.copyfile(directory / name, output / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seal", "verify"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--target", choices=PLATFORMS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "seal":
            if args.target is None:
                raise PromotionRefused("Native target required")
            seal(args.directory, args.source, args.version, args.target)
        else:
            if args.output is None:
                raise PromotionRefused("Publication staging directory required")
            verify(args.directory, args.output, args.source, args.version)
    except (PromotionRefused, KeyError, ValueError, OSError) as error:
        raise SystemExit(f"CLI publication refused: {error}") from None


if __name__ == "__main__":
    main()
