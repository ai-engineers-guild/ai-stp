"""Drive the configuration lifecycle of every harness, by the consumer path.

`software-evidence` proves the **program** lifecycle — `harness
install/status/update/remove` against a released provider, on six native legs.
It says nothing about the other subject this product exists for: taking a
machine's own configuration into management and putting it back.

That arc is the vision's sentence, and until now it was measured by hand on one
leg:

    seed a native surface  ->  component adopt  ->  component version release
    ->  select propose     ->  select confirm   ->  install plan
    ->  install approve    ->  install apply    ->  target status/diff/backups
    ->  install plan --action remove -> approve -> apply
    ->  the native path is gone again

One row per harness, seven rows, a typed outcome each, and a missing row is an
error rather than zero failures. The verdict is read **from the target** at each
turn, never from the provider's reply: a provider's answer is testimony, and the
native path either holds the component or it does not.

The seeded surface is derived from the catalog rather than written here, so a
row cannot quietly test a surface the product stopped reading. Every harness but
codex declares a global `skill` directory; codex declares `AGENTS.md`, and the
row records which one it drove.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from release_scripts._evidence import EvidenceError, cli, data, error_code

HARNESSES: Final[tuple[str, ...]] = (
    "claude-code",
    "codex",
    "cursor",
    "opencode",
    "antigravity",
    "pi",
    "grok-build",
)

PASSED: Final[str] = "passed"
FAILED: Final[str] = "failed"
INCONCLUSIVE: Final[str] = "inconclusive"

#: Codes that describe **this machine** rather than the subject under test. A
#: row that hits one is `inconclusive`: the question was never put. Named one by
#: one — a pattern like "anything ending in UNAVAILABLE" would swallow a future
#: code about the product and turn a real failure into a shrug.
_ENVIRONMENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "AI_STP_DEPENDENCY_UNAVAILABLE",
        "AI_STP_TIMEOUT_UNCONFIRMED",
        "AI_STP_RATE_LIMITED",
        "AI_STP_AUTH_REQUIRED",
    }
)

#: What the seeded component says. Non-ASCII on purpose: the bundle, the
#: provider argv and the native write are three encodings boundaries, and a
#: fixture made of ASCII proves none of them (`an-encoding-is-a-contract`).
SEED_BODY: Final[str] = "# Probe\n\nA seeded surface — one component, driven end to end.\n"


def _environment(home: Path) -> dict[str, str]:
    """The same environment `cli` runs in, so roots resolve to the same places."""
    held = dict(os.environ)
    held["HOME"] = str(home)
    held["USERPROFILE"] = str(home)
    held["XDG_CONFIG_HOME"] = str(home / "config")
    held["XDG_DATA_HOME"] = str(home / "data")
    for name in ("CODEX_HOME", "PI_CODING_AGENT_DIR", "OPENCODE_CONFIG_DIR", "GROK_HOME"):
        held.pop(name, None)
    return held


def _config_root(harness_id: str, home: Path) -> Path:
    """The harness's global configuration root inside this home, from the catalog."""
    from ai_stp_cli.local import harnesses

    detector = next(item for item in harnesses.DETECTORS if item.harness_id == harness_id)
    return harnesses.config_root(detector, _environment(home))


def _surface(harness_id: str, home: Path) -> tuple[Path, str, str]:
    """Where to seed, what kind it will be adopted as, and the layout's relative.

    Read from the catalog, not written here: a hand-written path is a second
    copy of a normative fact, and this estate has paid for that twice.
    """
    from ai_stp_cli.local import components

    base = _config_root(harness_id, home)
    rules = [rule for rule in components.GLOBAL_RULES if rule.harness_id == harness_id]
    skills = [
        rule for rule in rules if rule.component_type == "skill" and rule.shape == "directory"
    ]
    if skills:
        rule = skills[0]
        place = base / rule.relative / "probe"
        place.mkdir(parents=True, exist_ok=True)
        (place / "SKILL.md").write_text(SEED_BODY, encoding="utf-8")
        return place, "skill", rule.relative
    instructions = [
        rule
        for rule in rules
        if rule.component_type == "instruction"
        and rule.shape == "file"
        and "override" not in rule.relative
    ]
    if not instructions:
        raise EvidenceError(f"{harness_id} declares no seedable global surface")
    rule = instructions[0]
    place = base / rule.relative
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_text(SEED_BODY, encoding="utf-8")
    return place, "instruction", rule.relative


def _stage(name: str, arguments: list[str], *, home: Path, python: str) -> dict[str, Any]:
    """One command, with the refusal's own words kept beside its code.

    Measured the hard way on the first six-leg run: four legs came back
    `AI_STP_DEPENDENCY_UNAVAILABLE` and the row said only that. Which dependency
    is in the refusal's `details`, and dropping it turned a diagnosable failure
    into a shrug — the same lesson `746ffd4f` taught the software slice.
    """
    envelope = cli(arguments, home=home, python=python, allow_failure=True)
    if envelope.get("ok") is True:
        return {"stage": name, "outcome": PASSED, "data": data(envelope, name)}
    code = error_code(envelope)
    outcome = INCONCLUSIVE if code in _ENVIRONMENT_CODES else FAILED
    held = envelope.get("error")
    message = held.get("message", "") if isinstance(held, dict) else ""
    details = held.get("details", {}) if isinstance(held, dict) else {}
    return {
        "stage": name,
        "outcome": outcome,
        "code": code,
        "message": message,
        "details": details,
    }


def _artifact(directory: Path) -> Path:
    found = [
        item
        for item in sorted(directory.iterdir())
        if item.is_file() and item.name != "release.json"
    ]
    if len(found) != 1:
        raise EvidenceError(f"{directory} holds {len(found)} provider artifacts, expected one")
    return found[0]


def _apply(
    stages: list[dict[str, Any]],
    label: str,
    plan: dict[str, Any],
    *,
    executable: str,
    home: Path,
    python: str,
) -> bool:
    """Approve by exact digest and apply. `False` the moment a stage is not `passed`."""
    operation = str(plan.get("operation_id", ""))
    approved = _stage(
        f"{label}:approve",
        [
            "install",
            "approve",
            "--operation",
            operation,
            "--plan-digest",
            str(plan.get("plan_digest", "")),
        ],
        home=home,
        python=python,
    )
    stages.append(approved)
    if approved["outcome"] != PASSED:
        return False
    applied = _stage(
        f"{label}:apply",
        ["install", "apply", "--operation", operation, "--provider", executable],
        home=home,
        python=python,
    )
    stages.append(applied)
    return applied["outcome"] == PASSED


def _adopted(
    stages: list[dict[str, Any]],
    harness_id: str,
    seeded: Path,
    kind: str,
    *,
    home: Path,
    python: str,
) -> list[str] | None:
    """The seeded surface alone, as one adopted draft."""
    adopted = _stage(
        "adopt",
        ["component", "adopt", "--path", str(seeded), "--kind", kind, "--harness", harness_id],
        home=home,
        python=python,
    )
    stages.append(adopted)
    if adopted["outcome"] != PASSED:
        return None
    return [str(adopted["data"].get("stable_id", ""))]


def _imported(
    stages: list[dict[str, Any]], harness_id: str, *, home: Path, python: str
) -> list[str] | None:
    """The whole configuration root, as the drafts `setup import` decomposes it into."""
    base = str(_config_root(harness_id, home))
    planned = _stage(
        "import:plan",
        ["setup", "import", "plan", "--root", base, "--harness", harness_id],
        home=home,
        python=python,
    )
    stages.append(planned)
    if planned["outcome"] != PASSED:
        return None
    registered = _stage(
        "import:register",
        [
            "setup",
            "import",
            "register",
            "--root",
            base,
            "--harness",
            harness_id,
            # A synthetic reference: the slice seeds the root itself and holds no
            # provider copy of it. The passport records `recorded_unverified`,
            # which is the honest word for exactly this.
            "--backup-ref",
            "slot-000000000000",
            "--plan-digest",
            str(planned["data"].get("plan_digest", "")),
        ],
        home=home,
        python=python,
    )
    stages.append(registered)
    if registered["outcome"] != PASSED:
        return None
    identifiers = [str(item) for item in registered["data"].get("component_ids") or []]
    return identifiers or None


def _row(
    harness_id: str, *, root: Path, tag: str, python: str, from_import: bool = False
) -> dict[str, Any]:
    """One harness, taken from its own native bytes to a clean target and back.

    Two capture paths reach the same confirmed version. `component adopt`
    takes the seeded surface alone; `setup import` takes the whole
    configuration root the surface sits in and releases every draft it made
    (`#63`). Both must end in the same observed target, which is why the
    stages after `confirm` are shared rather than copied.
    """
    home = root / f"home-{harness_id}"
    (home / "config").mkdir(parents=True)
    (home / "data").mkdir(parents=True)
    project = home / "project"
    project.mkdir()
    (project / "README.md").write_text("# probe\n", encoding="utf-8")
    target = root / f"target-{harness_id}"
    target.mkdir()
    directory = root / f"provider-{harness_id}"
    directory.mkdir()

    stages: list[dict[str, Any]] = []
    try:
        cli(
            [
                "provider",
                "fetch",
                "--harness",
                harness_id,
                "--tag",
                tag,
                "--directory",
                str(directory),
            ],
            home=home,
            python=python,
        )
        seeded, kind, relative = _surface(harness_id, home)
    except EvidenceError as error:
        return {
            "harness_id": harness_id,
            "outcome": INCONCLUSIVE,
            "reason": str(error),
            "stages": stages,
        }
    executable = str(_artifact(directory))
    manifest = str(directory / "release.json")

    # The anchors composition needs. They are not the subject, so a failure here
    # is the environment rather than the arc, and the row says so.
    for name, arguments in (
        ("developer", ["passport", "developer", "init"]),
        ("device", ["passport", "device", "refresh"]),
        ("index", ["project", "index", "--root", str(project)]),
        ("project", ["project", "passport", "--root", str(project)]),
    ):
        anchored = _stage(f"anchor:{name}", arguments, home=home, python=python)
        if anchored["outcome"] != PASSED:
            stages.append(anchored)
            return _settle(harness_id, kind, relative, stages, seeded, target)

    if from_import:
        identifiers = _imported(stages, harness_id, home=home, python=python)
    else:
        identifiers = _adopted(stages, harness_id, seeded, kind, home=home, python=python)
    if identifiers is None:
        return _settle(harness_id, kind, relative, stages, seeded, target)

    references: list[str] = []
    for identifier in identifiers:
        released = _stage(
            f"release:{identifier[-6:]}",
            ["component", "version", "release", "--id", identifier, "--major"],
            home=home,
            python=python,
        )
        stages.append(released)
        if released["outcome"] != PASSED:
            return _settle(harness_id, kind, relative, stages, seeded, target)
        versions = released["data"].get("versions") or [{}]
        references.append(f"{identifier}@{versions[-1].get('version', '')}")

    members: list[str] = []
    for reference in references:
        members += ["--member", reference]
    proposed = _stage(
        "propose",
        ["select", "propose", "--harness", harness_id, "--project", str(project), *members],
        home=home,
        python=python,
    )
    stages.append(proposed)
    if proposed["outcome"] != PASSED:
        return _settle(harness_id, kind, relative, stages, seeded, target)
    # The proposal this call recorded, never the first open row: several may
    # be open for one pair, and the first was once an older empty one.
    proposal = str(proposed["data"].get("proposal_id") or "")

    confirmed = _stage(
        "confirm",
        ["select", "confirm", "--proposal", proposal],
        home=home,
        python=python,
    )
    stages.append(confirmed)
    if confirmed["outcome"] != PASSED:
        return _settle(harness_id, kind, relative, stages, seeded, target)

    common = [
        "--provider",
        executable,
        "--provider-manifest",
        manifest,
        "--target",
        str(target),
        "--harness",
        harness_id,
    ]
    planned = _stage(
        "plan", ["install", "plan", "--proposal", proposal, *common], home=home, python=python
    )
    stages.append(planned)
    if planned["outcome"] != PASSED:
        return _settle(harness_id, kind, relative, stages, seeded, target)
    if not _apply(
        stages, "install", planned["data"], executable=executable, home=home, python=python
    ):
        return _settle(harness_id, kind, relative, stages, seeded, target)

    landed = _landed(target, relative, kind)
    project_id = _project_id(home, python)
    observation = [
        "--project",
        project_id,
        "--harness",
        harness_id,
        "--provider",
        executable,
        "--target",
        str(target),
    ]
    for name in ("status", "backups"):
        stages.append(
            _stage(f"observe:{name}", ["target", name, *observation], home=home, python=python)
        )

    removal = _stage(
        "remove:plan",
        ["install", "plan", "--action", "remove", "--proposal", proposal, *common],
        home=home,
        python=python,
    )
    stages.append(removal)
    removed_cleanly = False
    if removal["outcome"] == PASSED and _apply(
        stages, "remove", removal["data"], executable=executable, home=home, python=python
    ):
        removed_cleanly = not _landed(target, relative, kind)

    return _settle(
        harness_id,
        kind,
        relative,
        stages,
        seeded,
        target,
        installed=landed,
        removed=removed_cleanly,
    )


def _project_id(home: Path, python: str) -> str:
    envelope = cli(
        ["project", "passport", "--root", str(home / "project")],
        home=home,
        python=python,
        allow_failure=True,
    )
    held = envelope.get("data")
    return str(held.get("stable_id", "")) if isinstance(held, dict) else ""


def _landed(target: Path, relative: str, kind: str) -> bool:
    """Whether the native surface under the target holds the seeded component now."""
    place = target / relative
    if kind == "instruction":
        return place.is_file() and "Probe" in place.read_text(encoding="utf-8", errors="replace")
    if not place.is_dir():
        return False
    return any(item.name == "probe" for item in place.iterdir())


def _settle(
    harness_id: str,
    kind: str,
    relative: str,
    stages: list[dict[str, Any]],
    seeded: Path,
    target: Path,
    *,
    installed: bool = False,
    removed: bool = False,
) -> dict[str, Any]:
    if any(item["outcome"] == FAILED for item in stages):
        outcome = FAILED
    elif any(item["outcome"] == INCONCLUSIVE for item in stages):
        outcome = INCONCLUSIVE
    elif installed and removed:
        outcome = PASSED
    else:
        outcome = FAILED
    return {
        "harness_id": harness_id,
        "outcome": outcome,
        "component_kind": kind,
        "native_surface": relative,
        "seeded_from": seeded.name,
        "observed": {"installed_into_target": installed, "removed_from_target": removed},
        "stages": stages,
    }


def _isolation(home: Path, python: str) -> dict[str, Any]:
    """What this machine can enforce, asked once and recorded beside the rows.

    Every configuration apply runs the provider through the platform's
    network-denying launcher, so a machine that cannot isolate cannot produce a
    single row — and the first six-leg run said only
    `AI_STP_DEPENDENCY_UNAVAILABLE` seven times per leg. Recording the
    capability turns "nothing ran" into "nothing ran, and here is the launcher's
    own reason", which is the difference between a rerun and a diagnosis.
    """
    envelope = cli(["provider", "network"], home=home, python=python, allow_failure=True)
    if envelope.get("ok") is not True:
        return {"asked": True, "code": error_code(envelope)}
    return data(envelope, "provider network")


def verify_config_slice(
    harnesses: Sequence[str], *, tag: str, python: str, from_import: bool = False
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-config-slice-") as scratch:
        root = Path(scratch)
        probe_home = root / "home-isolation"
        (probe_home / "config").mkdir(parents=True)
        (probe_home / "data").mkdir(parents=True)
        isolation = _isolation(probe_home, python)
        for harness_id in harnesses:
            rows.append(
                _row(harness_id, root=root, tag=tag, python=python, from_import=from_import)
            )
    counts = {
        state: sum(1 for row in rows if row["outcome"] == state)
        for state in (PASSED, FAILED, INCONCLUSIVE)
    }
    missing = sorted(set(harnesses) - {row["harness_id"] for row in rows})
    return {
        "schema_version": 1,
        "slice": "config",
        "capture": "import" if from_import else "adopt",
        "tag": tag,
        "isolation": isolation,
        "rows": rows,
        "counts": counts,
        "missing": missing,
        # Every row passed, not "no row failed". A run whose rows are all
        # `inconclusive` has zero failures, and the first six-leg run of this
        # slice reported `clean` on four legs having proven nothing at all —
        # a control that cannot fail, written by copying the shape beside it.
        "clean": not missing and counts[PASSED] == len(rows) and len(rows) > 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Exact provider release tag to drive.")
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        help="Drive one harness alone. Repeat for several; empty means all seven.",
    )
    parser.add_argument("--python", default=sys.executable, help="Interpreter running the CLI.")
    parser.add_argument(
        "--from-import",
        action="store_true",
        help="Capture through `setup import` of the whole root instead of `component adopt`.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = _parser().parse_args(arguments)
    chosen = tuple(parsed.harness) or HARNESSES
    unknown = sorted(set(chosen) - set(HARNESSES))
    if unknown:
        raise SystemExit(f"unknown harness: {', '.join(unknown)}")
    report = verify_config_slice(
        chosen, tag=parsed.tag, python=parsed.python, from_import=parsed.from_import
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["clean"] else 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
