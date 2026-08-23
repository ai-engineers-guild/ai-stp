"""Delivering the canonical Agent Skill to a harness (issue #77).

The Skill is the product's control plane: the agent reads it to learn how to
drive this CLI. It was generated into the repository and shipped nowhere, so a
user who installed the wheel received a binary and no procedure — the primary
consumer got nothing.

It now travels inside the package and is installed by naming a destination. The
destination is named rather than discovered, and that is deliberate: where each
harness looks for a native Skill is a fact about that harness, it differs across
five of them, and inventing five paths would be exactly the confident guess this
whole module exists to avoid. Discovery arrives with the harness detectors of
`SPEC-014`; until then the caller — a person, an agent, or the site installer —
passes the path it knows.

Nothing is ever overwritten silently. An installation writes an ownership record
beside the file, and removal takes back only what that record claims.
"""

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import redact_home, write_private
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER

#: Harnesses with a generated native projection, in the order they are declared.
#: Anything else is not a supported target rather than a target that might work.
HARNESSES: Final[tuple[str, ...]] = HARNESS_ID_ORDER

#: The record naming what this CLI put here. Kept beside the file rather than in
#: the local registry: a target directory can be removed, copied or restored
#: without this CLI being involved, and an ownership claim that lives elsewhere
#: would then describe a file that is not there.
MANIFEST: Final[str] = ".ai-stp-skill.json"

SKILL_FILENAME: Final[str] = "SKILL.md"


@dataclass(frozen=True)
class Installed:
    """What is at a destination, and whether this CLI put it there."""

    #: `absent`, `owned`, `foreign`, or `stale` when owned but since edited.
    state: str
    digest: str | None
    harness: str | None


def available(harness: str | None) -> str:
    """The Skill text this build ships for a harness, or the canonical one."""
    root = resources.files("ai_stp_cli").joinpath("skills")
    if harness is None:
        return root.joinpath("canonical", SKILL_FILENAME).read_text(encoding="utf-8")
    if harness not in HARNESSES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"no projection is shipped for harness: {harness}",
            details={"supported": ", ".join(HARNESSES)},
            next_actions=["capabilities --json"],
        )
    return root.joinpath("projections", f"{harness}.md").read_text(encoding="utf-8")


def digest_of(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def inspect(target: Path) -> Installed:
    """What is at `target`, without changing it."""
    skill = target / SKILL_FILENAME
    if not skill.exists():
        return Installed("absent", None, None)
    present = digest_of(skill.read_text(encoding="utf-8"))
    claim = _claim(target)
    if claim is None:
        # Something else put a Skill here. It is not ours to replace.
        return Installed("foreign", present, None)
    return Installed(
        "owned" if claim.get("digest") == present else "stale",
        present,
        claim.get("harness"),
    )


def install(target: Path, harness: str | None) -> Installed:
    """Put the Skill at `target`, refusing to overwrite what is not ours.

    Idempotent: installing the same text again rewrites the same bytes and the
    answer is unchanged. A file this CLI owns is replaced; one it does not is
    refused, because a harness configuration a user wrote by hand is theirs.
    """
    text = available(harness)
    wanted = digest_of(text)
    present = inspect(target)
    if present.state == "foreign":
        raise CliFailure(
            "AI_STP_CONFLICT",
            "a skill this installation does not own is already at that destination",
            details={"path": redact_home(target)},
            next_actions=["skill status --target <path> --json"],
        )
    if present.state == "stale":
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the installed skill was edited after this installation wrote it",
            details={"path": redact_home(target)},
            next_actions=["skill remove --target <path> --json"],
        )

    write_private(target / SKILL_FILENAME, text)
    write_private(
        target / MANIFEST,
        json.dumps({"digest": wanted, "harness": harness}, sort_keys=True) + "\n",
    )
    return Installed("owned", wanted, harness)


def remove(target: Path) -> Installed:
    """Take back only what the ownership record claims.

    A file this CLI did not write is left alone and said so. Removal here is
    about the control plane; the local registry and anything the user set up are
    a different thing and are never touched.
    """
    present = inspect(target)
    if present.state == "absent":
        return present
    if present.state == "foreign":
        raise CliFailure(
            "AI_STP_CONFLICT",
            "that skill was not installed by this installation",
            details={"path": redact_home(target)},
            next_actions=["skill status --target <path> --json"],
        )
    (target / SKILL_FILENAME).unlink(missing_ok=True)
    (target / MANIFEST).unlink(missing_ok=True)
    return Installed("absent", None, None)


def _claim(target: Path) -> dict[str, str] | None:
    path = target / MANIFEST
    if not path.exists():
        return None
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    document = cast(dict[str, object], parsed)
    return {str(key): str(value) for key, value in document.items() if value is not None}
