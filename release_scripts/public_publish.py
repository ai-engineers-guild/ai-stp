"""Publish the built public tree as one commit, with this machine's identity.

Written because doing it by hand got the identity wrong. The Git data API
attributes a commit to the token's account unless the author is stated, so
three commits went out under an address that is not the one this repository
requires. Identity belongs to the tool, not to whoever remembers.

It also exists because the transport is not always symmetric: `push` has worked
here while `clone` and `fetch` stalled for minutes. This compares the published
tree against the built one through the API and sends only what differs, so
nothing has to be downloaded to publish an update — and the history stays
honest, without a forced overwrite.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent


class PublishError(RuntimeError):
    """The publication cannot proceed as described."""


@dataclass(frozen=True)
class Identity:
    name: str
    email: str


def identity() -> Identity:
    """Name and email from the global Git config, which is their only owner.

    Refused rather than defaulted when either is empty: a commit published
    under a guessed identity is worse than one not published.
    """
    values: list[str] = []
    for key in ("user.name", "user.email"):
        try:
            found = subprocess.run(
                ["git", "config", "--global", "--get", key],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise PublishError(f"global git config has no {key}") from error
        if not found:
            raise PublishError(f"global git config has an empty {key}")
        values.append(found)
    return Identity(values[0], values[1])


def api(
    repo: str, endpoint: str, *args: str, method: str | None = None, body: str | None = None
) -> Any:
    command = ["gh", "api", f"repos/{repo}/{endpoint}"]
    if method:
        command += ["--method", method]
    if body is not None:
        command += ["--input", "-"]
    command += list(args)
    try:
        completed = subprocess.run(command, input=body, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or error
        raise PublishError(f"{endpoint} failed: {detail}") from error
    return json.loads(completed.stdout) if completed.stdout.strip() else None


def published_blobs(repo: str, tree_sha: str) -> dict[str, str]:
    """Path to blob SHA for everything the published tree holds."""
    # Query in the URL rather than as a field: `gh api` switches to POST the
    # moment a field is given, and this endpoint answers GET only.
    listing = api(repo, f"git/trees/{tree_sha}?recursive=1")
    if listing.get("truncated"):
        raise PublishError("published tree listing was truncated; publish by push instead")
    return {item["path"]: item["sha"] for item in listing["tree"] if item["type"] == "blob"}


def local_blobs(tree: Path) -> dict[str, str]:
    """Path to Git blob SHA for everything the built tree holds.

    Hashed by Git itself rather than reimplemented, so a match here means the
    same object and not merely the same bytes by some other definition.
    """
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-s", "-z"], cwd=tree, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise PublishError(f"could not read the built tree: {error}") from error
    blobs: dict[str, str] = {}
    for record in listed.split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        _mode, sha, _stage = meta.split(" ", 2)
        blobs[path] = sha
    if not blobs:
        raise PublishError("the built tree has nothing staged; run `git add -A` in it first")
    return blobs


def changes(published: dict[str, str], built: dict[str, str]) -> tuple[list[str], list[str]]:
    changed = sorted(path for path, sha in built.items() if published.get(path) != sha)
    removed = sorted(path for path in published if path not in built)
    return changed, removed


def publish(repo: str, tree: Path, message: str, *, dry_run: bool = False) -> int:
    who = identity()
    head = api(repo, "git/ref/heads/main")["object"]["sha"]
    base_tree = api(repo, f"git/commits/{head}")["tree"]["sha"]
    changed, removed = changes(published_blobs(repo, base_tree), local_blobs(tree))

    print(f"published head: {head[:8]}")
    for path in changed:
        print(f"  changed: {path}")
    for path in removed:
        print(f"  removed: {path}")
    if not changed and not removed:
        print("nothing to publish")
        return 0
    if dry_run:
        return 0

    entries: list[dict[str, Any]] = []
    for path in changed:
        blob = api(
            repo,
            "git/blobs",
            "-f",
            f"content={base64.b64encode((tree / path).read_bytes()).decode()}",
            "-f",
            "encoding=base64",
            method="POST",
        )
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    for path in removed:
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})

    new_tree = api(
        repo,
        "git/trees",
        method="POST",
        body=json.dumps({"base_tree": base_tree, "tree": entries}),
    )["sha"]
    author = {"name": who.name, "email": who.email}
    commit = api(
        repo,
        "git/commits",
        method="POST",
        body=json.dumps(
            {
                "message": message,
                "tree": new_tree,
                "parents": [head],
                "author": author,
                "committer": author,
            }
        ),
    )["sha"]
    api(repo, "git/refs/heads/main", "-f", f"sha={commit}", "-F", "force=false", method="PATCH")
    print(f"published {commit[:8]} as {who.name} <{who.email}>")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="ai-engineers-guild/ai-stp")
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--message-file", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return publish(
            args.repo,
            args.tree,
            args.message_file.read_text(encoding="utf-8"),
            dry_run=args.dry_run,
        )
    except (PublishError, OSError) as error:
        print(f"publication failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
