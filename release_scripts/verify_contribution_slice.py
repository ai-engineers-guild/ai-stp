"""Drive one MCP component through all three of its native forms, by the consumer path.

`#456` measured that MCP has three different native landings across the seven
harnesses, and that none of them is "an MCP file the provider writes":

    key inside an owned setting file   codex, grok-build, opencode
    its own owned file                 cursor, antigravity
    no such kind at all                pi — the product says so deliberately,
                                       and the route lands it as an extension
    no surface in any form             claude-code — refusal is the right answer

The routing for all four exists and is covered by unit tests. What those tests
cannot answer is the acceptance this issue actually names: that one component is
installed, observed once, and removed on each form — against a released
provider, through `ai-stp`, with the contribution assembled by the real compiler
rather than by a fixture.

That distinction is the whole point of a separate slice. A contribution is
assembled in `commands/select.py` from the target's current bytes plus this
component's key; a fixture that hands the provider a pre-built file proves the
provider writes files, which was never in doubt. Only the consumer path proves
that the key lands **and that nothing else in the host file moves**.

One row per form. Each row carries a typed outcome and the observed native path,
and a missing row is an error rather than zero failures.

**What the first real run of this slice found, on 2026-09-01.** It had never
been run: no recipe, no workflow, no document named it. Three defects lived in
it, each invisible from reading:

- it planted the component in an arbitrary temporary directory and adopted from
  there, and `adopt` answers `no discovered component sits at that path` — a
  component is adopted from a **declared native surface**, never from a loose
  file;
- it built the member reference from `adopt`'s reply, which carries no version:
  a draft has none until `component version release` mints one;
- and its `claude-code` row went green on that same `AI_STP_NOT_FOUND`, so the
  control that exists to prove a refusal was passing on an unrelated failure.
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

#: One harness per native form, named by the form rather than by the harness so
#: a substitution stays honest about what it covers.
FORMS: Final[tuple[tuple[str, str], ...]] = (
    ("key_in_owned_setting", "codex"),
    ("own_owned_file", "cursor"),
    ("extension_package", "pi"),
)

#: The refusal that is also an answer. `claude-code` has no owned host to
#: contribute to: `.mcp.json` is a project file at a repository root and the
#: user scope lives in `~/.claude.json`, which the provider holds in
#: `never_touch`. A run that stopped reporting this would stop covering it.
REFUSING_HARNESS: Final[str] = "claude-code"

PASSED: Final[str] = "passed"
FAILED: Final[str] = "failed"
NOT_APPLICABLE: Final[str] = "not_applicable"
INCONCLUSIVE: Final[str] = "inconclusive"


#: Codes that describe **this machine**, not the provider that was asked. Named
#: one by one rather than matched by a pattern: a rule like "anything ending in
#: UNAVAILABLE" would silently swallow a future code that describes a provider,
#: and the whole point of separating them is that the wrong one changes what a
#: row means.
_ENVIRONMENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "AI_STP_DEPENDENCY_UNAVAILABLE",
        "AI_STP_TIMEOUT_UNCONFIRMED",
        "AI_STP_RATE_LIMITED",
        "AI_STP_AUTH_REQUIRED",
    }
)


def _environment(home: Path) -> dict[str, str]:
    held = dict(os.environ)
    held["HOME"] = str(home)
    held["USERPROFILE"] = str(home)
    held["XDG_CONFIG_HOME"] = str(home / "config")
    held["XDG_DATA_HOME"] = str(home / "data")
    for name in ("CODEX_HOME", "PI_CODING_AGENT_DIR", "OPENCODE_CONFIG_DIR", "GROK_HOME"):
        held.pop(name, None)
    return held


def _artifact(directory: Path) -> Path:
    found = [
        item
        for item in sorted(directory.iterdir())
        if item.is_file() and item.name != "release.json"
    ]
    if len(found) != 1:
        raise EvidenceError(f"{directory} holds {len(found)} provider artifacts, expected one")
    return found[0]


def _seed(home: Path, harness_id: str) -> tuple[Path, str]:
    """Plant `mcp01` where **this** harness declares it lives, and say which kind.

    Deliberately minimal and deliberately real: one MCP server declaration, the
    smallest thing that has a key and a value. The name `MCP01` is the issue's,
    and keeping it makes the evidence and the acceptance criterion the same
    string rather than two that have to be matched up by a reader.

    The place is read from the catalog through the same resolver discovery uses,
    because a path written here would be a second copy of a normative fact.
    """
    from ai_stp_cli.local import components, harnesses

    detector = next(item for item in harnesses.DETECTORS if item.harness_id == harness_id)
    base = harnesses.config_root(detector, _environment(home))
    rules = [rule for rule in components.GLOBAL_RULES if rule.harness_id == harness_id]

    owned = [rule for rule in rules if rule.component_type == "mcp"]
    if owned:
        rule = owned[0]
        place = base / rule.relative
        place.parent.mkdir(parents=True, exist_ok=True)
        if rule.declared_key:
            place.write_text(
                f'[{rule.declared_key}.mcp01]\ncommand = "mcp01-server"\nargs = ["--stdio"]\n',
                encoding="utf-8",
            )
        else:
            place.write_text(
                json.dumps(
                    {"mcpServers": {"mcp01": {"command": "mcp01-server", "args": ["--stdio"]}}},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return place, "mcp"

    # No `mcp` kind of its own. `composition.rule_for` still routes an MCP
    # server here, as the product's own packaging: pi ships one as an
    # extension. Driving that route is what the third form means.
    from ai_stp_cli.local import composition

    rule = composition.rule_for("mcp", harness_id)
    if rule is None:
        raise EvidenceError(f"{harness_id} has no mcp route; this slice cannot drive it")
    place = base / rule.relative / "mcp01"
    place.mkdir(parents=True, exist_ok=True)
    (place / "package.json").write_text(
        json.dumps({"name": "mcp01", "version": "1.0.0"}, indent=2) + "\n", encoding="utf-8"
    )
    (place / "README.md").write_text(
        "# mcp01\n\nAn MCP server, shipped as an extension.\n", encoding="utf-8"
    )
    return place, str(getattr(rule, "provider_kind", "") or "plugin")


def _stage(name: str, arguments: list[str], *, home: Path, python: str) -> dict[str, Any]:
    envelope = cli(arguments, home=home, python=python, allow_failure=True)
    if envelope.get("ok") is True:
        return {"stage": name, "outcome": PASSED, "data": data(envelope, name)}
    code = error_code(envelope)
    outcome = INCONCLUSIVE if code in _ENVIRONMENT_CODES else FAILED
    return {"stage": name, "outcome": outcome, "code": code}


def _anchor(home: Path, project: Path, python: str) -> dict[str, Any] | None:
    for name, arguments in (
        ("developer", ["passport", "developer", "init"]),
        ("device", ["passport", "device", "refresh"]),
        ("index", ["project", "index", "--root", str(project)]),
        ("project", ["project", "passport", "--root", str(project)]),
    ):
        anchored = _stage(f"anchor:{name}", arguments, home=home, python=python)
        if anchored["outcome"] != PASSED:
            return anchored
    return None


def _row(form: str, harness_id: str, *, root: Path, tag: str, python: str) -> dict[str, Any]:
    """One native form, taken from adoption to removal by `ai-stp` itself."""
    from ai_stp_cli.local import composition

    rule = composition.rule_for("mcp", harness_id)
    home = root / f"home-{harness_id}"
    (home / "config").mkdir(parents=True)
    (home / "data").mkdir(parents=True)
    project = home / "project"
    project.mkdir()
    (project / "README.md").write_text("# probe\n", encoding="utf-8")
    directory = root / f"provider-{harness_id}"
    directory.mkdir()
    target = root / f"target-{harness_id}"
    target.mkdir()

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
        seeded, kind = _seed(home, harness_id)
    except EvidenceError as error:
        return {
            "form": form,
            "harness_id": harness_id,
            "outcome": INCONCLUSIVE,
            "reason": str(error),
            "stages": stages,
        }
    executable = str(_artifact(directory))
    manifest = str(directory / "release.json")

    blocked = _anchor(home, project, python)
    if blocked is not None:
        stages.append(blocked)
        return _settle(form, harness_id, rule, stages, target)

    adopted = _stage(
        "adopt",
        ["component", "adopt", "--path", str(seeded), "--kind", kind, "--harness", harness_id],
        home=home,
        python=python,
    )
    stages.append(adopted)
    if adopted["outcome"] != PASSED:
        return _settle(form, harness_id, rule, stages, target)
    identifier = str(adopted["data"].get("stable_id", ""))

    released = _stage(
        "release",
        ["component", "version", "release", "--id", identifier, "--major", "--confirm"],
        home=home,
        python=python,
    )
    stages.append(released)
    if released["outcome"] != PASSED:
        return _settle(form, harness_id, rule, stages, target)
    versions = released["data"].get("versions") or [{}]
    reference = f"{identifier}@{versions[-1].get('version', '')}"

    proposed = _stage(
        "propose",
        [
            "select",
            "propose",
            "--harness",
            harness_id,
            "--project",
            str(project),
            "--member",
            reference,
        ],
        home=home,
        python=python,
    )
    stages.append(proposed)
    if proposed["outcome"] != PASSED:
        return _settle(form, harness_id, rule, stages, target)
    offers = proposed["data"].get("proposals") or [{}]
    proposal = str(offers[0].get("proposal_id", ""))

    stages.append(
        _stage(
            "confirm",
            ["select", "confirm", "--proposal", proposal, "--confirm"],
            home=home,
            python=python,
        )
    )
    if stages[-1]["outcome"] != PASSED:
        return _settle(form, harness_id, rule, stages, target)

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
    if planned["outcome"] == PASSED:
        held = planned["data"]
        operation = str(held.get("operation_id", ""))
        stages.append(
            _stage(
                "approve",
                [
                    "install",
                    "approve",
                    "--operation",
                    operation,
                    "--plan-digest",
                    str(held.get("plan_digest", "")),
                ],
                home=home,
                python=python,
            )
        )
        stages.append(
            _stage(
                "apply",
                ["install", "apply", "--operation", operation, "--provider", executable],
                home=home,
                python=python,
            )
        )
    return _settle(form, harness_id, rule, stages, target)


def _settle(
    form: str,
    harness_id: str,
    rule: Any,
    stages: list[dict[str, Any]],
    target: Path,
) -> dict[str, Any]:
    """The verdict, read from the target rather than from the last stage's reply.

    The same rule the program lifecycle learned this week: a provider's answer is
    testimony, and the native path either holds the key or it does not.
    """
    host = target / rule.relative if rule is not None else None
    landed = host is not None and host.exists()
    key = getattr(rule, "declared_key", "") if rule is not None else ""
    contains = False
    if landed and host is not None and host.is_file():
        contains = "mcp01" in host.read_text(encoding="utf-8", errors="replace")
    elif landed and host is not None:
        contains = any("mcp01" in item.name for item in host.rglob("*"))
    if any(item["outcome"] == FAILED for item in stages):
        outcome = FAILED
    elif any(item["outcome"] == INCONCLUSIVE for item in stages):
        outcome = INCONCLUSIVE
    elif not contains:
        outcome = FAILED
    else:
        outcome = PASSED
    return {
        "form": form,
        "harness_id": harness_id,
        "outcome": outcome,
        "native_surface": getattr(rule, "relative", ""),
        "declared_key": key,
        "provider_kind": getattr(rule, "provider_kind", "") or "mcp",
        "observed": {"path_present": landed, "carries_mcp01": contains},
        "stages": stages,
    }


def _refusal(root: Path, python: str) -> dict[str, Any]:
    """`claude-code` must still refuse, and the refusal must be about **its** surface.

    Written as an attempt rather than as an assertion about the table. The first
    version returned `PASSED if ... or True else FAILED`, a control incapable of
    failing; the second passed because `adopt` failed for an unrelated reason,
    which is the same defect wearing a different coat.

    So two independent facts have to hold, and either one turning false turns the
    row red: the composition table — the owner of the routing — must route no
    `mcp` component to claude-code, and a real component adopted from a real
    surface must be refused when proposed for it.
    """
    from ai_stp_cli.local import composition

    routed = composition.rule_for("mcp", REFUSING_HARNESS)
    if routed is not None:
        return {
            "form": "no_surface_at_all",
            "harness_id": REFUSING_HARNESS,
            "outcome": FAILED,
            "reason": f"an mcp route appeared at {routed.relative}; this slice is out of date",
            "stages": [],
        }

    home = root / "home-refusal"
    (home / "config").mkdir(parents=True)
    (home / "data").mkdir(parents=True)
    project = home / "project"
    project.mkdir()
    (project / "README.md").write_text("# probe\n", encoding="utf-8")
    blocked = _anchor(home, project, python)
    if blocked is not None:
        return {
            "form": "no_surface_at_all",
            "harness_id": REFUSING_HARNESS,
            "outcome": INCONCLUSIVE,
            "reason": f"the home could not be anchored: {blocked.get('code', '')}",
            "stages": [blocked],
        }

    seeded, kind = _seed(home, "codex")
    adopted = cli(
        ["component", "adopt", "--path", str(seeded), "--kind", kind, "--harness", "codex"],
        home=home,
        python=python,
        allow_failure=True,
    )
    if adopted.get("ok") is not True:
        return {
            "form": "no_surface_at_all",
            "harness_id": REFUSING_HARNESS,
            "outcome": INCONCLUSIVE,
            "reason": "the probe component could not be adopted; nothing was put to claude-code",
            "code": error_code(adopted),
            "stages": [],
        }
    member = data(adopted, "adopt")
    identifier = str(member.get("stable_id", ""))
    released = cli(
        ["component", "version", "release", "--id", identifier, "--major", "--confirm"],
        home=home,
        python=python,
        allow_failure=True,
    )
    if released.get("ok") is not True:
        return {
            "form": "no_surface_at_all",
            "harness_id": REFUSING_HARNESS,
            "outcome": INCONCLUSIVE,
            "reason": "the probe component could not be released",
            "code": error_code(released),
            "stages": [],
        }
    versions = data(released, "release").get("versions") or [{}]
    reference = f"{identifier}@{versions[-1].get('version', '')}"
    proposed = cli(
        [
            "select",
            "propose",
            "--harness",
            REFUSING_HARNESS,
            "--project",
            str(project),
            "--member",
            reference,
        ],
        home=home,
        python=python,
        allow_failure=True,
    )
    if proposed.get("ok") is True:
        return {
            "form": "no_surface_at_all",
            "harness_id": REFUSING_HARNESS,
            "outcome": FAILED,
            "reason": "an mcp component composed for a harness that has no mcp surface",
            "stages": [],
        }
    return {
        "form": "no_surface_at_all",
        "harness_id": REFUSING_HARNESS,
        "outcome": PASSED,
        "refused_at": "propose",
        "code": error_code(proposed),
        "routed": False,
        "stages": [],
    }


def verify_contribution_slice(*, tag: str, python: str) -> dict[str, Any]:
    """Every named form, one row each, with the counts remeasured from the rows."""
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-contribution-slice-") as scratch:
        root = Path(scratch)
        for form, harness_id in FORMS:
            rows.append(_row(form, harness_id, root=root, tag=tag, python=python))
        rows.append(_refusal(root, python))

    counts = {
        state: sum(1 for row in rows if row["outcome"] == state)
        for state in (PASSED, FAILED, NOT_APPLICABLE, INCONCLUSIVE)
    }
    expected = {form for form, _ in FORMS} | {"no_surface_at_all"}
    missing = sorted(expected - {row["form"] for row in rows})
    return {
        "schema_version": 1,
        "slice": "contribution",
        "tag": tag,
        "rows": rows,
        "counts": counts,
        "missing": missing,
        # Every row passed. Zero failures is not the same claim: a run whose
        # rows are all `inconclusive` satisfies it while proving nothing.
        "clean": not missing and counts[PASSED] == len(rows) and len(rows) > 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Exact provider release tag to drive.")
    parser.add_argument("--python", default=sys.executable, help="Interpreter running the CLI.")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = _parser().parse_args(arguments)
    report = verify_contribution_slice(tag=parsed.tag, python=parsed.python)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["clean"] else 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
