"""Prove this CLI against the provider releases people can actually download.

The three older slices prove things against the deployed environment. This one
proves something the gate structurally cannot: that the projection table in this
repository still agrees with the seven providers as *released*, on the bytes a
`provider fetch` hands somebody.

Why it is a slice and not a test. `just check` may not depend on another
repository's tags — an unreachable release would read as a red gate here, and a
gate that goes red for somebody else's outage stops being read. So this is run
deliberately, like `evidence-live`, and its report is meant to be pasted.

Why it exists at all. On 2026-08-27 two of our tables named a cursor surface no
product reads, and the unit guard comparing them passed, because they were wrong
together. Only the provider's own declaration settled it, and nothing ran that
comparison against a *release* — the equivalent check in the suite reads a local
build tree, which is whatever the person last compiled.

What it does not prove. Conformance answers whether a provider satisfies the
protocol; it does not install anything. The full lifecycle — install, update,
backup, remove, rollback — lives in the cross-repository tests, which need the
five `AI_STP_*_PROVIDER_V3` pairs pointed at a fetched artifact and manifest.
Those tests are named in the report so nobody reads this slice as covering them.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from release_scripts._evidence import EvidenceError, cli, data, without_credentials

#: Every harness whose provider is released, in catalogue order. `undefined` is
#: a shared convention rather than a product and has no provider to fetch.
HARNESSES: tuple[str, ...] = (
    "claude-code",
    "codex",
    "pi",
    "opencode",
    "grok-build",
    "cursor",
    "antigravity",
)


def _artifact(directory: Path) -> Path:
    """The single executable a fetch left behind, beside its manifest."""
    found = [item for item in sorted(directory.iterdir()) if item.name != "release.json"]
    if len(found) != 1:
        raise EvidenceError(
            f"expected one artifact in {directory.name}, found {[item.name for item in found]}"
        )
    return found[0]


def _declaration(executable: Path) -> dict[str, Any]:
    """Read `provider-info` from the fetched binary itself.

    Deliberately the artifact rather than our record of it. A slice that read the
    declaration from anywhere else would be proving our bookkeeping.
    """
    result = subprocess.run(
        [str(executable), "provider-info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise EvidenceError(f"{executable.name} provider-info exited {result.returncode}")
    try:
        answer = json.loads(result.stdout)
    except ValueError as error:
        raise EvidenceError(f"{executable.name} provider-info emitted no JSON") from error
    if not isinstance(answer, dict):
        raise EvidenceError(f"{executable.name} provider-info is not an object")
    return answer


def _disagreements(harness_id: str, declared: dict[str, Any]) -> list[str]:
    """Projection rules the released provider will not accept.

    Imported here rather than at module scope: this script is part of the
    release tooling, and importing the CLI's internals at load time would make
    every other release script depend on them.
    """
    from ai_stp_cli.local import composition

    # One profile per scope, because a rule is only answerable against the
    # profile whose target it is relative to. Comparing a `user_root` rule with
    # the global profile reports its kind as undeclared and its path as
    # unsupported — both correctly, for a profile that does not describe it.
    profiles: dict[str, dict[str, Any]] = {}
    globally = declared.get("projection_profile") or {}
    profiles[str(globally.get("target_scope") or "global")] = globally
    for scoped in declared.get("scoped_projection_profiles") or []:
        profiles[str(scoped.get("target_scope") or "")] = scoped

    found: list[str] = []
    for rule in composition.PROVIDER_RULES:
        if rule.harness_id != harness_id:
            continue
        profile = profiles.get(rule.target_scope)
        if profile is None:
            found.append(
                f"{rule.component_type} -> {rule.relative}: no {rule.target_scope} profile declared"
            )
            continue
        kinds = {str(item) for item in profile.get("component_kinds", [])}
        namespaces = {str(item) for item in profile.get("native_namespaces", [])}
        if rule.component_type not in kinds:
            found.append(f"{rule.component_type} -> {rule.relative}: kind not declared")
        elif rule.relative not in namespaces:
            found.append(f"{rule.component_type} -> {rule.relative}: path not a native namespace")
    return found


def verify_provider_slice(
    harnesses: Sequence[str],
    *,
    tag: str,
    python: str,
) -> dict[str, Any]:
    """Fetch each release, then compare its own declaration with our table."""
    reports: dict[str, Any] = {}
    disagreeing: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-provider-slice-") as scratch:
        root = Path(scratch)
        home = root / "home"
        (home / "config").mkdir(parents=True)
        (home / "data").mkdir(parents=True)
        for harness_id in harnesses:
            directory = root / harness_id
            directory.mkdir()
            fetched = data(
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
                ),
                "provider fetch",
            )
            executable = _artifact(directory)
            declared = _declaration(executable)
            # `--protocol-version 3` and a target are both required, and the
            # first run of this slice omitted them. `provider conformance`
            # defaults to frozen v1, so a v3 provider gets checked against v1's
            # field set and answers `conforms: false` with
            # "announces None, which this build does not speak" — a report that
            # reads as seven broken releases. The same shape as every other
            # defect found this week: the instrument, not the subject.
            target = root / f"{harness_id}-target"
            target.mkdir()
            conformance = data(
                cli(
                    [
                        "provider",
                        "conformance",
                        "--harness",
                        harness_id,
                        "--executable",
                        str(executable),
                        "--protocol-version",
                        "3",
                        "--target",
                        str(target),
                    ],
                    home=home,
                    python=python,
                    allow_failure=True,
                ),
                "provider conformance",
            )
            # Split by whose obligation it is, the same way the report does.
            # A case failing under `consumer` means the provider is correct and
            # this compiler cannot reach something it offers — real, worth
            # naming, and not a reason to call a release red. Counting them
            # together turned three sound providers red the moment conformance
            # started reporting reach.
            cases = [item for item in conformance.get("cases", []) if isinstance(item, dict)]
            failing = [
                str(case.get("name"))
                for case in cases
                if case.get("passed") is not True
                and str(case.get("subject", "provider")) == "provider"
            ]
            unreachable = [
                str(case.get("name"))
                for case in cases
                if case.get("passed") is not True
                and str(case.get("subject", "provider")) == "consumer"
            ]
            mismatched = _disagreements(harness_id, declared)
            if mismatched or failing:
                disagreeing.append(harness_id)
            reports[harness_id] = {
                "tag": fetched.get("tag"),
                "sequence": fetched.get("sequence"),
                "trust_level": fetched.get("trust_level"),
                "artifact_digest": fetched.get("artifact_digest"),
                "provider_version": declared.get("provider_version"),
                "conforms": conformance.get("conforms"),
                "conformance_cases": len(conformance.get("cases", [])),
                "conformance_failing": failing,
                "capability_unreachable": unreachable,
                "declared_component_kinds": (declared.get("projection_profile") or {}).get(
                    "component_kinds"
                ),
                "declared_native_namespaces": (declared.get("projection_profile") or {}).get(
                    "native_namespaces"
                ),
                "projection_disagreements": mismatched,
            }
    return without_credentials(
        {
            "schema_version": 1,
            "slice": "provider-releases",
            "tag": tag,
            "harnesses": reports,
            "harnesses_with_projection_disagreements": sorted(disagreeing),
            # Named so nobody reads a green slice as covering the lifecycle.
            "not_verified": {
                "install_update_backup_remove_rollback": (
                    "the cross-repository tests in tests/unit/test_cli_install_commands.py; "
                    "they need AI_STP_<HARNESS>_PROVIDER_V3 and _MANIFEST pointed at a "
                    "fetched artifact and its release.json"
                ),
            },
        }
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Exact provider release tag, e.g. 0.0.8.")
    parser.add_argument(
        "--harness",
        action="append",
        choices=HARNESSES,
        help="Restrict to one harness; repeatable. Default is all seven.",
    )
    parser.add_argument("--python", default=sys.executable)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    if "GH_CONFIG_DIR" not in os.environ:
        # `_evidence.cli` isolates HOME, and `provider fetch` shells out to `gh`,
        # which then finds no configuration and reports the release metadata as
        # unavailable. Measured: without this the slice refuses every harness
        # and the message names `gh` rather than the isolation that hid it.
        print(
            "provider-slice: set GH_CONFIG_DIR to your gh configuration directory; "
            "the isolated home this slice runs in has none",
            file=sys.stderr,
        )
        return 1
    try:
        report = verify_provider_slice(
            options.harness or list(HARNESSES),
            tag=options.tag,
            python=options.python,
        )
    except (EvidenceError, OSError, subprocess.SubprocessError) as error:
        print(f"provider-slice: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    # Red while any released provider refuses a rule we still carry. No
    # expectation list: an evidence slice that excuses its own known failure is
    # the allowlist pattern that hid a real gap in this repository once already.
    return 1 if report["harnesses_with_projection_disagreements"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
