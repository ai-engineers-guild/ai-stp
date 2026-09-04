"""Drive the program lifecycle of every released provider through `ai-stp` itself.

`evidence-providers` proves the contract and the bytes: it fetches each release,
reads its own `provider-info` and runs `provider conformance`. What it never
does is put a provider through the path a user takes — `harness install`,
`harness status`, `harness update`, `harness remove` — so a defect that lives
between the consumer and the provider is invisible to it. Every integration
defect this estate has had lived exactly there: argv the provider did not
expect, a status the consumer read differently, a write that did not survive the
sandbox, a postcondition read off the wrong subject.

So this is the other half, and it is deliberately a separate slice rather than a
few more cases inside the first. The two answer different questions and fail for
different reasons, and a run that could not reach GitHub must not be reported as
a provider that does not work.

One row per harness. Each row carries a typed outcome and never a bare boolean:

- `passed` — every stage ran and its postcondition held;
- `failed` — a stage ran and did not do what it said;
- `not_applicable` — the provider does not declare this operation on this
  platform, which is an answer rather than a gap;
- `not_exercised` — the conditions for asking were not there;
- `inconclusive` — the release source or the vendor could not be reached, which
  is a fact about the network and not about the provider.

A missing row is an error. Absence has to be visible, because the whole class of
mistake this replaces is a green summary over a set nobody counted.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from release_scripts._evidence import (
    EvidenceError,
    cli,
    data,
    error_code,
    error_details,
    error_message,
)

#: The seven harnesses, in the order the estate names them.
HARNESSES: Final[tuple[str, ...]] = (
    "claude-code",
    "codex",
    "cursor",
    "opencode",
    "antigravity",
    "pi",
    "grok-build",
)

#: Outcomes. `passed` is one of five, not the default with four excuses.
PASSED: Final[str] = "passed"
FAILED: Final[str] = "failed"
NOT_APPLICABLE: Final[str] = "not_applicable"
NOT_EXERCISED: Final[str] = "not_exercised"
INCONCLUSIVE: Final[str] = "inconclusive"

#: Refusals that describe the platform rather than a defect. A provider that
#: does not ship a build for this OS and architecture has answered the question.
_CAPABILITY_CODES: Final[frozenset[str]] = frozenset(
    {"AI_STP_UNSUPPORTED_PLATFORM", "AI_STP_UNSUPPORTED_APPLY"}
)


#: Codes that describe **this machine**, not the provider that was asked. Named
#: one by one rather than matched by a pattern: a rule like "anything ending in
#: UNAVAILABLE" would silently swallow a future code that describes a provider,
#: and the whole point of separating them is that the wrong one changes what a
#: row means.
#:
#: A row that hits one of these is `inconclusive`. It is not a provider that
#: failed and not a provider that passed — the question was never put. The
#: setup-systems session reached this the hard way: its scheduled run filed
#: "seven harnesses stopped conforming" when none had, because a refusal about
#: the environment arrived in the same `ok:false` envelope as a real one.
_ENVIRONMENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "AI_STP_DEPENDENCY_UNAVAILABLE",
        "AI_STP_TIMEOUT_UNCONFIRMED",
        "AI_STP_RATE_LIMITED",
        "AI_STP_AUTH_REQUIRED",
    }
)


def _artifact(directory: Path) -> Path:
    """The one executable `provider fetch` wrote, and its manifest beside it."""
    found = [
        item
        for item in sorted(directory.iterdir())
        if item.is_file() and item.name != "release.json"
    ]
    if len(found) != 1:
        raise EvidenceError(f"{directory} holds {len(found)} provider artifacts, expected one")
    return found[0]


def _acquired_artifact(home: Path, harness_id: str, tag: str) -> Path:
    """The exact managed release a provider-free lifecycle acquired."""
    directory = home / "data" / "ai-stp" / "providers" / harness_id / tag
    manifest = directory / "release.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise EvidenceError(f"{harness_id} did not retain release.json for acquired tag {tag}")
    return _artifact(directory)


def _stage(
    name: str,
    arguments: list[str],
    *,
    home: Path,
    python: str,
) -> dict[str, Any]:
    """One consumer call, with its typed outcome rather than an exception."""
    envelope = cli(arguments, home=home, python=python, allow_failure=True)
    if envelope.get("ok") is True:
        return {"stage": name, "outcome": PASSED, "data": data(envelope, name)}
    code = error_code(envelope)
    if code in _ENVIRONMENT_CODES:
        outcome = INCONCLUSIVE
    elif code in _CAPABILITY_CODES:
        outcome = NOT_APPLICABLE
    else:
        outcome = FAILED
    # The code names the class; the message names the instance; the details
    # name the evidence. The cursor-on-windows row proved each layer earns its
    # keep: the code has over twenty sources, the message was one generic
    # sentence shared by all postcondition misses, and the observed reason —
    # which half of the settlement failed — travels only in the details.
    row: dict[str, Any] = {"stage": name, "outcome": outcome, "code": code}
    message = error_message(envelope)
    if message:
        row["message"] = message
    details = error_details(envelope)
    if details:
        row["details"] = details
    return row


def _row(
    harness_id: str,
    *,
    root: Path,
    home: Path,
    tag: str,
    python: str,
    acquire: bool = False,
) -> dict[str, Any]:
    """One harness, taken through the whole program lifecycle by `ai-stp`."""
    directory = root / harness_id
    directory.mkdir()
    executable = ""
    manifest = ""
    if not acquire:
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
            # The release source, not the provider. Reported as its own outcome so
            # a GitHub outage never reads as seven broken releases.
            return {
                "harness_id": harness_id,
                "outcome": INCONCLUSIVE,
                "reason": f"the release could not be fetched: {error}",
                "stages": [],
            }
        executable = str(_artifact(directory))
        manifest = str(directory / "release.json")
    target = root / f"{harness_id}-target"
    prefix = root / f"{harness_id}-prefix"
    target.mkdir()
    prefix.mkdir()
    common = [
        "--harness",
        harness_id,
        "--prefix",
        str(prefix),
        "--target",
        str(target),
    ]
    if not acquire:
        common[2:2] = ["--provider", executable, "--provider-manifest", manifest]

    install = _stage("install", ["harness", "install", *common], home=home, python=python)
    stages: list[dict[str, Any]] = [install]
    if install["outcome"] != PASSED:
        # Status, update and remove are questions about an installation. If the
        # vendor bytes never arrived, asking them manufactures downstream
        # failures from the same environmental refusal (and can leave an
        # approved operation that update correctly refuses to cross). Keep the
        # causal outcome and make the unasked stages explicit instead.
        stages.extend(
            {
                "stage": name,
                "outcome": NOT_EXERCISED,
                "reason": "install did not pass",
            }
            for name in ("status", "update", "remove")
        )
        return {
            "harness_id": harness_id,
            "outcome": install["outcome"],
            "provider_artifact": Path(executable).name if executable else "",
            "acquisition": "transparent" if acquire else "explicit",
            "stages": stages,
        }
    if acquire:
        try:
            executable = str(_acquired_artifact(home, harness_id, tag))
        except EvidenceError as error:
            stages.append(
                {
                    "stage": "acquisition",
                    "outcome": FAILED,
                    "reason": str(error),
                }
            )
            return {
                "harness_id": harness_id,
                "outcome": FAILED,
                "provider_artifact": "",
                "acquisition": "transparent",
                "stages": stages,
            }
        stages.append(
            {
                "stage": "acquisition",
                "outcome": PASSED,
                "tag": tag,
                "provider_artifact": Path(executable).name,
            }
        )

    stages.extend(
        [
            # Reads the prefix and nothing else, so it is the independent view
            # of what install actually left behind.
            _stage(
                "status",
                ["harness", "status", "--harness", harness_id, "--prefix", str(prefix)],
                home=home,
                python=python,
            ),
            _stage("update", ["harness", "update", *common], home=home, python=python),
            _stage(
                "remove",
                ["harness", "remove", "--confirm", *common],
                home=home,
                python=python,
            ),
        ]
    )

    outcomes = {item["outcome"] for item in stages}
    if FAILED in outcomes:
        outcome = FAILED
    elif outcomes == {NOT_APPLICABLE}:
        outcome = NOT_APPLICABLE
    else:
        outcome = PASSED
    return {
        "harness_id": harness_id,
        "outcome": outcome,
        "provider_artifact": Path(executable).name,
        "acquisition": "transparent" if acquire else "explicit",
        "stages": stages,
    }


def verify_software_slice(
    harnesses: Sequence[str],
    *,
    tag: str,
    python: str,
    acquire: bool = False,
) -> dict[str, Any]:
    """Every named harness, one row each, with the counts remeasured from the rows."""
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-software-slice-") as scratch:
        root = Path(scratch)
        home = root / "home"
        (home / "config").mkdir(parents=True)
        (home / "data").mkdir(parents=True)
        for harness_id in harnesses:
            rows.append(
                _row(
                    harness_id,
                    root=root,
                    home=home,
                    tag=tag,
                    python=python,
                    acquire=acquire,
                )
            )

    # Counted from what is here, never carried from what was asked for. A row
    # that was never produced has to change these numbers.
    counts = {
        state: sum(1 for row in rows if row["outcome"] == state)
        for state in (PASSED, FAILED, NOT_APPLICABLE, NOT_EXERCISED, INCONCLUSIVE)
    }
    missing = [name for name in harnesses if not any(row["harness_id"] == name for row in rows)]
    return {
        "schema_version": 1,
        "slice": "software",
        "tag": tag,
        "acquisition": "transparent" if acquire else "explicit",
        "asked": list(harnesses),
        "rows": rows,
        "counts": counts,
        "missing": missing,
        # Every asked row passed. "No row failed" is satisfied by a run where
        # every row is `inconclusive`, which is a green that examined nothing;
        # the config slice beside this one produced exactly that on four legs
        # before the rule was tightened here too.
        "clean": not missing and counts[PASSED] == len(rows) and len(rows) > 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Exact provider release tag to drive.")
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        choices=HARNESSES,
        help="Harness to include. Repeatable. Omit for all seven.",
    )
    parser.add_argument(
        "--acquire",
        action="store_true",
        help=(
            "Omit provider paths so harness install transparently acquires "
            "and remembers each release."
        ),
    )
    parser.add_argument("--python", default=sys.executable, help="Interpreter running the CLI.")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = _parser().parse_args(arguments)
    harnesses = tuple(parsed.harness) or HARNESSES
    report = verify_software_slice(
        harnesses,
        tag=parsed.tag,
        python=parsed.python,
        acquire=parsed.acquire,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["clean"] else 1


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
