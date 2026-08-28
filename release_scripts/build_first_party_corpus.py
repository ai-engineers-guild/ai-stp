"""Build the first-party corpus from the live setup-system repositories.

There was no such tool. The manifests and the embedded artifacts under `v1/`
were assembled outside this repository, which is why the corpus went on citing
an estate that had been transferred to a personal account and archived — nothing
here could rebuild it, so nothing here noticed.

What it does. For each harness it reads the `setups/nddev-builder/` tree of that
harness's setup-system at its current `main` commit, maps every path to a
component using this repository's own projection rules, packages each one, and
emits a manifest beside the artifacts. Git's own tree and blob SHAs are recorded
as `source_tree`, so provenance is the repository's hash rather than ours.

Two things it deliberately does not do.

It does not invent a component for a path no rule routes. `composition.rule_for`
decides, and a file under a namespace this compiler cannot place is reported
rather than packaged — codex's `agents/nddev-builder.toml` is the live case: a
codex role is an `agents.<name>` table in the settings file plus a layer it
points at, so the file is a companion of the setting rather than a component,
and there is no honest kind for it.

It does not reuse stable identifiers. These are new objects from a different
repository, and giving them the old ids would say a published version came from
a source it did not.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

#: harness_id -> setup-system repository. The two differ, and assuming they did
#: not is how a first probe reported two of these as nonexistent.
REPOSITORIES: dict[str, str] = {
    "claude-code": "claude-setup-system",
    "codex": "codex-setup-system",
    "cursor": "cursor-setup-system",
    "grok-build": "grok-setup-system",
    "pi": "pi-setup-system",
    "opencode": "opencode-setup-system",
    "antigravity": "antigravity-setup-system",
}

ORGANISATION = "NDDev-OpenNetwork"
SETUP_PATH = "setups/nddev-builder/setup.json"
HOME_PREFIX = "setups/nddev-builder/home/"

COMPONENT_TREE = "ai-stp-component-tree/1"
COMPONENT_FILE = "ai-stp-component-file/1"


def _gh(path: str, jq: str) -> str:
    result = subprocess.run(
        ["gh", "api", path, "--jq", jq], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {path}: {result.stderr.strip()}")
    return result.stdout.strip()


def _blob(repository: str, sha: str) -> bytes:
    import base64

    raw = _gh(f"repos/{ORGANISATION}/{repository}/git/blobs/{sha}", ".content")
    return base64.b64decode(raw)


def _tree(repository: str) -> tuple[str, list[dict[str, Any]]]:
    commit = _gh(f"repos/{ORGANISATION}/{repository}/commits/main", ".sha")
    raw = _gh(f"repos/{ORGANISATION}/{repository}/git/trees/main?recursive=1", ".tree")
    return commit, json.loads(raw)


def _components(
    harness_id: str, entries: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Map each home path to a component, or report why it is not one."""
    from ai_stp_cli.local import composition

    rules = [rule for rule in composition.PROVIDER_RULES if rule.harness_id == harness_id]
    by_relative = {rule.relative: rule for rule in rules}
    blobs = {item["path"]: item for item in entries if item["type"] == "blob"}
    trees = {item["path"]: item for item in entries if item["type"] == "tree"}

    found: list[dict[str, Any]] = []
    unrouted: list[str] = []
    claimed: set[str] = set()

    for rule in sorted(rules, key=lambda item: -len(item.relative)):
        base = f"{HOME_PREFIX}{rule.relative}"
        if rule.shape == "file":
            if base in blobs and base not in claimed:
                claimed.add(base)
                found.append(
                    {
                        "component_type": rule.component_type,
                        "projection_kind": rule.projection_kind,
                        "slug": rule.relative,
                        "source_path": f"nddev-builder/home/{rule.relative}",
                        "source_tree": blobs[base]["sha"],
                        "artifact_format": COMPONENT_FILE,
                        "source_object_kind": "blob",
                    }
                )
            continue
        # A directory rule: every immediate child is one component.
        for path, item in sorted(trees.items()) + sorted(blobs.items()):
            parent, _, name = path.rpartition("/")
            if parent != base or path in claimed:
                continue
            claimed.add(path)
            found.append(
                {
                    "component_type": rule.component_type,
                    "projection_kind": rule.projection_kind,
                    "slug": name,
                    "source_path": f"nddev-builder/home/{rule.relative}/{name}",
                    "source_tree": item["sha"],
                    "artifact_format": (
                        COMPONENT_TREE if item["type"] == "tree" else COMPONENT_FILE
                    ),
                    "source_object_kind": "tree" if item["type"] == "tree" else "blob",
                }
            )

    for path in sorted(blobs):
        if not path.startswith(HOME_PREFIX) or path in claimed:
            continue
        relative = path[len(HOME_PREFIX) :]
        if any(relative.startswith(f"{item}/") for item in claimed_relatives(claimed)):
            continue
        if relative.split("/")[0] not in by_relative and relative not in by_relative:
            unrouted.append(relative)
    return found, sorted(set(unrouted))


def claimed_relatives(claimed: set[str]) -> list[str]:
    return [path[len(HOME_PREFIX) :] for path in claimed if path.startswith(HOME_PREFIX)]


def _package(repository: str, entries: list[dict[str, Any]], component: dict[str, Any]) -> bytes:
    """The exact bytes of one component, as the corpus embeds them."""
    prefix = f"{HOME_PREFIX}{component['source_path'].split('home/', 1)[1]}"
    if component["source_object_kind"] == "blob":
        return _blob(repository, component["source_tree"])
    members = sorted(
        (
            item
            for item in entries
            if item["type"] == "blob" and item["path"].startswith(f"{prefix}/")
        ),
        key=lambda item: str(item["path"]),
    )
    held = BytesIO()
    with zipfile.ZipFile(held, "w", zipfile.ZIP_STORED) as archive:
        manifest: list[dict[str, Any]] = []
        for item in members:
            content = _blob(repository, item["sha"])
            relative = item["path"][len(prefix) + 1 :]
            info = zipfile.ZipInfo(f"files/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
            import hashlib

            manifest.append(
                {
                    "path": relative,
                    "byte_length": len(content),
                    "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
                    "mode": 420,
                }
            )
        body = json.dumps(
            {"files": manifest, "format": COMPONENT_TREE}, separators=(",", ":"), sort_keys=True
        ).encode()
        info = zipfile.ZipInfo("component.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        archive.writestr(info, body)
    return held.getvalue()


def build(harnesses: Sequence[str], *, out: Path) -> dict[str, Any]:
    from ai_stp_foundation.ids import new_id

    report: dict[str, Any] = {"harnesses": {}, "unrouted": {}}
    manifest: list[dict[str, Any]] = []
    for harness_id in harnesses:
        repository = REPOSITORIES[harness_id]
        commit, entries = _tree(repository)
        components, unrouted = _components(harness_id, entries)
        setup = next((item for item in entries if item["path"] == SETUP_PATH), None)
        if setup is None:
            raise RuntimeError(f"{repository} has no {SETUP_PATH}")
        for component in components:
            # A file rule's slug is its relative path, which may carry a
            # separator — antigravity's setting is `antigravity-cli/settings.json`.
            # An artifact name is a filename, so the separator becomes a dash
            # rather than a directory nobody created.
            flat = component["slug"].replace("/", "-")
            name = f"{harness_id}-{flat}-{component['component_type']}"
            suffix = (
                ".zip"
                if component["source_object_kind"] == "tree"
                else Path(component["slug"]).suffix or ".txt"
            )
            component["artifact_name"] = f"{name}{suffix}"
            component["stable_id"] = new_id("component")
            (out / component["artifact_name"]).write_bytes(_package(repository, entries, component))
        manifest.append(
            {
                "commit": commit,
                "components": components,
                "evidence_ref": f"https://github.com/{ORGANISATION}/{repository}",
                "harness_id": harness_id,
                "repository": f"https://github.com/{ORGANISATION}/{repository}",
                "setup_blob": setup["sha"],
                "setup_id": new_id("setup"),
                "setup_path": SETUP_PATH,
            }
        )
        report["harnesses"][harness_id] = len(components)
        if unrouted:
            report["unrouted"][harness_id] = unrouted
    report["manifest"] = {"harnesses": manifest, "schema_version": 1}
    return report


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--harness", action="append", choices=sorted(REPOSITORIES))
    options = parser.parse_args(arguments)
    options.out.mkdir(parents=True, exist_ok=True)
    report = build(options.harness or sorted(REPOSITORIES), out=options.out)
    (options.out / "corpus-sources.json").write_text(
        json.dumps(
            report.pop("manifest"), separators=(",", ":"), sort_keys=True, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
