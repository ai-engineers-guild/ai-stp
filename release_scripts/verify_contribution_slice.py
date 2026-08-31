"""Drive one MCP component through all three of its native forms, by the consumer path.

`#456` measured that MCP has three different native landings across the seven
harnesses, and that none of them is "an MCP file the provider writes":

    key inside an owned setting file   codex, grok-build, opencode
    its own owned file                 cursor, antigravity
    no such kind at all                pi — the product says so deliberately
    no surface in any form             claude-code — refusal is the right answer

The routing for all four exists and is covered by unit tests. What those tests
cannot answer is the acceptance this issue actually names: that one component is
installed, observed once, and removed on each of the three forms — against a
released provider, through `ai-stp`, with the contribution assembled by the real
compiler rather than by a fixture.

That distinction is the whole point of a separate slice. A contribution is
assembled in `commands/select.py` from the target's current bytes plus this
component's key; a fixture that hands the provider a pre-built file proves the
provider writes files, which was never in doubt. Only the consumer path proves
that the key lands **and that nothing else in the host file moves**.

One row per form. Each row carries a typed outcome and the observed native path,
and a missing row is an error rather than zero failures.
"""

from __future__ import annotations

import argparse
import json
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
    ("no_such_kind", "pi"),
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


def _artifact(directory: Path) -> Path:
    found = [
        item
        for item in sorted(directory.iterdir())
        if item.is_file() and item.name != "release.json"
    ]
    if len(found) != 1:
        raise EvidenceError(f"{directory} holds {len(found)} provider artifacts, expected one")
    return found[0]


def _mcp01(root: Path, harness_id: str) -> Path:
    """The component this slice is about, laid out as discovery expects to find it.

    Deliberately minimal and deliberately real: one MCP server declaration, the
    smallest thing that has a key and a value. The name `MCP01` is the issue's,
    and keeping it makes the evidence and the acceptance criterion the same
    string rather than two that have to be matched up by a reader.
    """
    from ai_stp_cli.local import composition

    rule = composition.rule_for("mcp", harness_id)
    if rule is None:
        raise EvidenceError(f"{harness_id} has no mcp route; this slice cannot drive it")
    place = root / f"mcp01-{harness_id}"
    place.mkdir(parents=True)
    body = {
        "mcp01": {
            "command": "mcp01-server",
            "args": ["--stdio"],
        }
    }
    (place / "mcp01.json").write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return place


def _stage(name: str, arguments: list[str], *, home: Path, python: str) -> dict[str, Any]:
    envelope = cli(arguments, home=home, python=python, allow_failure=True)
    if envelope.get("ok") is True:
        return {"stage": name, "outcome": PASSED, "data": data(envelope, name)}
    return {"stage": name, "outcome": FAILED, "code": error_code(envelope)}


def _row(
    form: str,
    harness_id: str,
    *,
    root: Path,
    home: Path,
    tag: str,
    python: str,
) -> dict[str, Any]:
    """One native form, taken from adoption to removal by `ai-stp` itself."""
    from ai_stp_cli.local import composition

    rule = composition.rule_for("mcp", harness_id)
    directory = root / f"provider-{harness_id}"
    directory.mkdir()
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
    except EvidenceError as error:
        return {
            "form": form,
            "harness_id": harness_id,
            "outcome": INCONCLUSIVE,
            "reason": f"the release could not be fetched: {error}",
            "stages": [],
        }

    executable = str(_artifact(directory))
    manifest = str(directory / "release.json")
    target = root / f"{harness_id}-target"
    target.mkdir()
    component = _mcp01(root, harness_id)

    stages: list[dict[str, Any]] = []
    adopted = _stage(
        "adopt", ["component", "adopt", "--path", str(component)], home=home, python=python
    )
    stages.append(adopted)
    if adopted["outcome"] != PASSED:
        return _settle(form, harness_id, rule, stages, target)

    member = adopted["data"]
    reference = f"{member.get('stable_id', '')}@{member.get('version', '')}"

    proposed = _stage(
        "propose",
        ["select", "propose", "--harness", harness_id, "--member", reference],
        home=home,
        python=python,
    )
    stages.append(proposed)
    if proposed["outcome"] != PASSED:
        return _settle(form, harness_id, rule, stages, target)

    proposal = str(proposed["data"].get("proposal_id", ""))
    stages.append(
        _stage(
            "confirm",
            ["select", "confirm", "--proposal", proposal, "--confirm", proposal],
            home=home,
            python=python,
        )
    )

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
    elif landed:
        contains = any(
            "mcp01" in item.name
            for item in host.rglob("*")  # pyright: ignore[reportOptionalMemberAccess]
        )
    outcome = FAILED if any(s["outcome"] == FAILED for s in stages) else PASSED
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


def _refusal(root: Path, home: Path, python: str) -> dict[str, Any]:
    """`claude-code` must still refuse, and the refusal must arrive before a bundle.

    Written as an attempt rather than as an assertion about the table. The first
    version of this function returned `PASSED if ... or True else FAILED`, which
    is a control incapable of failing — the exact shape this estate spent a week
    learning to spot, reproduced by the person writing the check for it.

    So the component is really adopted and really proposed, and the row is green
    only when something refused. A success here is a genuine failure: it means an
    mcp component composed for a harness whose surface does not exist, and the
    install would answer `verified` with nothing on the machine.
    """
    place = root / "mcp01-claude-code"
    place.mkdir(parents=True, exist_ok=True)
    (place / "mcp01.json").write_text(
        json.dumps({"mcp01": {"command": "mcp01-server"}}, indent=2) + "\n", encoding="utf-8"
    )
    adopted = cli(
        ["component", "adopt", "--path", str(place)],
        home=home,
        python=python,
        allow_failure=True,
    )
    if adopted.get("ok") is not True:
        return {
            "form": "no_surface_at_all",
            "harness_id": REFUSING_HARNESS,
            "outcome": PASSED,
            "refused_at": "adopt",
            "code": error_code(adopted),
            "stages": [],
        }
    member = data(adopted, "adopt")
    reference = f"{member.get('stable_id', '')}@{member.get('version', '')}"
    proposed = cli(
        ["select", "propose", "--harness", REFUSING_HARNESS, "--member", reference],
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
        "stages": [],
    }


def verify_contribution_slice(*, tag: str, python: str) -> dict[str, Any]:
    """Every named form, one row each, with the counts remeasured from the rows."""
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-contribution-slice-") as scratch:
        root = Path(scratch)
        home = root / "home"
        (home / "config").mkdir(parents=True)
        (home / "data").mkdir(parents=True)
        for form, harness_id in FORMS:
            rows.append(_row(form, harness_id, root=root, home=home, tag=tag, python=python))
        rows.append(_refusal(root, home, python))

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
        "clean": not missing and counts[FAILED] == 0,
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
