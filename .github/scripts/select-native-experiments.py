"""Select registered native experiments; an unknown probe never silently skips CI."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

GUEST = "tests/native_confinement/wasi.rs"
PREFIX = "tests/native_confinement/"
INPUTS = {
    GUEST,
    "apps/cli/rust-toolchain.toml",
}


#: A pull request touching any of these runs the Linux native CLI job, whose
#: corporate journeys otherwise first run after the merge, on Dev.
CLI_INPUTS = (
    "apps/cli/",
    "apps/api/",
    "apps/platform/",
    "packages/",
    "release_scripts/",
    "tests/native_contract/",
    "tests/support/",
    ".github/",
)
CLI_FILES = {"justfile", "uv.lock", "pyproject.toml", "alembic.ini"}


def select_cli(event: str, changed: set[str]) -> bool:
    return event != "pull_request" or any(
        path in CLI_FILES or path.startswith(CLI_INPUTS) for path in changed
    )


def select(event: str, changed: set[str], tracked: set[str]) -> bool:
    unknown = {path for path in tracked | changed if path.startswith(PREFIX)} - {GUEST}
    if unknown:
        raise RuntimeError("Every native probe requires an explicit joined CI owner")
    if GUEST not in tracked:
        raise RuntimeError("The registered WASIp2 probe is missing")
    if event not in {"pull_request", "push", "workflow_dispatch"}:
        raise RuntimeError("Unknown qualification event")
    return event != "pull_request" or any(
        path in INPUTS or path.startswith(".github/") for path in changed
    )


def controls() -> None:
    known = {GUEST, "apps/cli/src/main.rs"}
    if select("pull_request", set(), known):
        raise RuntimeError("Unchanged experiment selected unexpectedly")
    for event in ["push", "workflow_dispatch"]:
        if not select(event, set(), known):
            raise RuntimeError("Full qualification must include the registered experiment")
    for change in [GUEST, "apps/cli/rust-toolchain.toml", ".github/scripts/changed.py"]:
        if not select("pull_request", {change}, known):
            raise RuntimeError("Owning source/toolchain/security input must select the experiment")
    for event, changed, tracked in [
        ("pull_request", {PREFIX + "unknown.cpp"}, known),
        ("pull_request", set(), known | {PREFIX + "unknown.mm"}),
        ("pull_request", set(), set()),
        ("unknown_event", set(), known),
    ]:
        try:
            select(event, changed, tracked)
        except RuntimeError:
            continue
        raise RuntimeError("Unknown/deleted/unregistered source control was accepted")
    if select_cli("pull_request", {"apps/web/src/page.tsx"}) or not all(
        select_cli("pull_request", {path})
        for path in ["apps/cli/src/main.rs", "tests/native_contract/verify.py", "uv.lock"]
    ):
        raise RuntimeError("The native CLI selection must follow its owning sources")
    if not select_cli("push", set()):
        raise RuntimeError("Full qualification must include the native CLI job")


def git(*arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], check=True, capture_output=True, timeout=30).stdout


def main() -> None:
    controls()
    event = os.environ["EVENT"]
    source = os.environ["SOURCE_SHA"]
    if (
        not re.fullmatch(r"[0-9a-f]{40}", source)
        or git("rev-parse", "HEAD").decode().strip() != source
    ):
        raise RuntimeError("The consumer checkout must match the exact qualification source")
    tracked = set(git("ls-files", "-z").decode().rstrip("\0").split("\0"))
    mode = git("ls-files", "--stage", "--", GUEST).decode().split()
    if not mode or mode[0] != "100644":
        raise RuntimeError("The registered guest must remain a regular source file")
    changed: set[str] = set()
    if event == "pull_request":
        base, head = os.environ["BASE_SHA"], os.environ["HEAD_SHA"]
        if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in [base, head]):
            raise RuntimeError("Exact original PR base/head commits required")
        changed = set(
            git("diff", "--name-only", "--no-renames", "-z", base, head, "--")
            .decode()
            .rstrip("\0")
            .split("\0")
        ) - {""}
    chosen = select(event, changed, tracked)
    cli = select_cli(event, changed)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"wasi={str(chosen).lower()}\n")
        output.write(f"cli={str(cli).lower()}\n")
    print(
        json.dumps(
            {
                "registered_wasi_selected": chosen,
                "native_cli_selected": cli,
                "selection_controls": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
