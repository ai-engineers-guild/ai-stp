"""Exercise authenticated native component lifecycles in disposable CI fixtures.

This proves configuration component behavior, not harness loading, corporate
binding or interrupted publication. Reports never authorize a later operation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "provider_release_inspection", Path(__file__).with_name("inspect-provider-release.py")
)
assert SPEC is not None and SPEC.loader is not None
INSPECTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTION)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def payload(path: Path) -> tuple[bytes, dict[str, tuple[bytes, int]]]:
    content = path.read_bytes()
    files: dict[str, tuple[bytes, int]] = {}
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("bundle.json"))
        for item in manifest["files"]:
            relative = item["path"]
            parts = PurePosixPath(relative)
            require(
                not parts.is_absolute()
                and ".." not in parts.parts
                and str(parts) == relative
                and "\\" not in relative,
                "unsafe fixture path",
            )
            require(not item.get("contribution"), "this whole-file fixture has a contribution")
            member = archive.getinfo("files/" + relative)
            mode = member.external_attr >> 16
            require(stat.S_ISREG(mode), "fixture member is not a regular file")
            data = archive.read(member)
            require(
                item["digest"] == "sha256:" + hashlib.sha256(data).hexdigest()
                and item["byte_length"] == len(data)
                and item["mode"] == stat.S_IMODE(mode),
                "fixture manifest and bytes differ",
            )
            require(relative not in files, "duplicate fixture path")
            files[relative] = (data, item["mode"])
    require(bool(files), "fixture contains no managed files")
    return content, files


def verify_files(root: Path, expected: dict[str, tuple[bytes, int]]) -> None:
    for relative, (content, mode) in expected.items():
        path = root / relative
        require(path.is_file() and not path.is_symlink(), "expected regular file is missing")
        require(path.read_bytes() == content, "independent file bytes differ")
        require(stat.S_IMODE(path.stat().st_mode) == mode, "independent file mode differs")


def exercise(
    binary: Path,
    home: Path,
    state: Path,
    bundles: Path,
    harness: str,
    scope: str,
    version: str,
    observed: dict[str, Any],
    kind: str | None = None,
) -> dict[str, Any]:
    name = f"{harness}-{scope}" + (f"-{kind}" if kind else "")
    case = home / name
    case.mkdir()
    target = case / "checkout with spaces"
    target.mkdir()
    original_bytes, original = payload(bundles / f"{name}.zip")
    replacement_bytes, replacement = payload(bundles / f"{name}-replacement.zip")
    require(original != replacement, "replacement fixture has identical effects")
    canaries = {
        "owner-credentials.json": (b'{"private":"fixture-only-credential"}\n', 0o600),
        "owner-trust.json": (b'{"trusted":false}\n', 0o600),
        "sessions/preserved.json": (b'{"session":"fixture-only"}\n', 0o600),
        "src/preserved.txt": (b"unrelated source content\n", 0o644),
    }
    if scope == "project":
        private_paths = {
            "claude-code": [".claude/settings.local.json"],
            "codex": [".codex/auth.json"],
            "pi": [".pi/auth.json", ".pi/trust.json", ".pi/sessions/session.jsonl"],
            "opencode": [".opencode/auth.json", ".opencode/package.json", "opencode.jsonc"],
            "grok-build": [
                ".grok/auth.json",
                ".grok/trusted_folders.toml",
                ".grok/sessions/session.jsonl",
                ".grok/plugins/known_marketplaces.json",
            ],
            "cursor": [".cursor/owner-credentials.json"],
            "antigravity": [".agents/owner-credentials.json"],
        }
        for relative in private_paths[harness]:
            canaries[relative] = (b"unowned-private-fixture-canary\n", 0o600)
    first = next(iter(original))
    parent = PurePosixPath(first).parent
    if str(parent) != ".":
        canaries[str(parent / "owner-resource.txt")] = (b"unowned sibling\n", 0o640)
    require(
        not (canaries.keys() & (original.keys() | replacement.keys())), "canary overlaps payload"
    )
    for relative, (content, mode) in canaries.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)

    def invoke(arguments: list[str]) -> dict[str, Any]:
        return dict(INSPECTION.invoke(binary, home, arguments))

    def plan(operation: str, bundle: Path | None) -> tuple[Path, dict[str, Any], str]:
        arguments = [
            "configuration",
            "plan",
            "--state-dir",
            str(state),
            "--harness",
            harness,
            "--target",
            str(target),
            "--scope",
            scope,
            "--operation",
            operation,
        ]
        if bundle is not None:
            arguments.extend(["--bundle", str(bundle)])
        result = invoke(arguments)
        require(result["mutation_performed"] is False, "planning claimed a mutation")
        document = result["plan"]
        require(
            document["harness_id"] == harness
            and document["provider_version"] == version
            and document["target_path"] == str(target)
            and document["target_scope"] == scope,
            "plan coordinates differ",
        )
        require(
            document["archive_digest"] == observed["artifact"]["archive_digest"]
            and document["executable_digest"] == observed["artifact"]["executable_digest"]
            and document["info_digest"] == observed["provider_info_digest"],
            "plan selected bytes differ from the authenticated release observation",
        )
        path = case / f"{operation}-plan.json"
        path.write_text(json.dumps(document) + "\n")
        return path, document, str(result["plan_digest"])

    def apply(planned: tuple[Path, dict[str, Any], str], bundle: Path | None) -> dict[str, Any]:
        path, document, digest = planned
        arguments = [
            "configuration",
            "apply",
            "--state-dir",
            str(state),
            "--plan",
            str(path),
            "--plan-digest",
            digest,
        ]
        if bundle is not None:
            arguments.extend(["--bundle", str(bundle)])
        result = invoke(arguments)
        require(
            result["state"] == "verified"
            and result["plan_digest"] == digest
            and result["operation_id"] == document["operation_id"]
            and result["provider_version"] == version
            and result["harness_id"] == harness
            and result["scope"] == scope
            and result["target"] == str(target)
            and result["action"] == document["action"]
            and result["mutation_performed"] is True,
            "native receipt differs from the original plan",
        )
        return result

    install_source = case / "install.zip"
    install_source.write_bytes(original_bytes)
    installed = plan("install", install_source)
    verify_files(target, canaries)
    require(all(not (target / name).exists() for name in original), "planning wrote managed files")
    first_receipt = apply(installed, install_source)
    verify_files(target, original | canaries)
    install_source.unlink()
    require(apply(installed, None) == first_receipt, "completed installation replay differs")

    replacement_source = case / "replacement.zip"
    replacement_source.write_bytes(replacement_bytes)
    replaced = plan("replace", replacement_source)
    verify_files(target, original | canaries)
    second_receipt = apply(replaced, replacement_source)
    replacement_source.unlink()
    verify_files(target, replacement | canaries)
    require(apply(installed, None) == first_receipt, "old installation receipt changed")
    verify_files(target, replacement | canaries)
    require(apply(replaced, None) == second_receipt, "completed replacement replay differs")

    removed = plan("remove", None)
    verify_files(target, replacement | canaries)
    removal_receipt = apply(removed, None)
    require(
        all(not (target / name).exists() for name in original | replacement), "owned file remains"
    )
    verify_files(target, canaries)
    require(apply(replaced, None) == second_receipt, "old replacement receipt changed")
    require(all(not (target / name).exists() for name in replacement), "replay resurrected files")
    target.rename(case / "retired checkout")
    for planned, receipt in (
        (installed, first_receipt),
        (replaced, second_receipt),
        (removed, removal_receipt),
    ):
        require(apply(planned, None) == receipt, "receipt replay requires the old physical target")
        require(not target.exists(), "receipt replay recreated the target")
    return {
        "harness_id": harness,
        "target_scope": scope,
        "component_kind": kind,
        "install": True,
        "replace": True,
        "remove": True,
        "completed_receipt_replay_after_source_and_target_loss": True,
        "foreign_bytes_and_modes_preserved": True,
    }


def retained_plan(
    binary: Path,
    baseline: Path,
    home: Path,
    state: Path,
    bundles: Path,
    harness: str,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Apply an unadmitted old-default plan, without rewriting its serialized bytes."""
    case = home / f"retained-{harness}"
    case.mkdir()
    target = case / "original checkout"
    target.mkdir()
    source = case / "original.zip"
    content, files = payload(bundles / f"{harness}-project.zip")
    source.write_bytes(content)
    canary = {"owner-source.txt": (b"unrelated retained source\n", 0o640)}
    for name, (data, mode) in canary.items():
        (target / name).write_bytes(data)
        (target / name).chmod(mode)
    observed = INSPECTION.invoke(
        baseline,
        home,
        [
            "provider",
            "inspect",
            "--state-dir",
            str(state),
            "--harness",
            harness,
            "--version",
            "0.0.94",
        ],
    )
    require(observed["artifact"]["trust_level"] == "verified_publisher", "old publisher unverified")
    require(observed["provider_info"]["provider_version"] == "0.0.94", "old declaration differs")
    previous_profile = next(
        p
        for p in observed["provider_info"]["scoped_projection_profiles"]
        if p["target_scope"] == "project"
    )
    current_profile = next(
        p
        for p in current["provider_info"]["scoped_projection_profiles"]
        if p["target_scope"] == "project"
    )
    require(previous_profile["digest"] != current_profile["digest"], "profile change not exercised")
    result = INSPECTION.invoke(
        baseline,
        home,
        [
            "configuration",
            "plan",
            "--state-dir",
            str(state),
            "--harness",
            harness,
            "--target",
            str(target),
            "--scope",
            "project",
            "--operation",
            "install",
            "--bundle",
            str(source),
        ],
    )
    plan = result["plan"]
    require(result["mutation_performed"] is False, "old planning mutated configuration")
    require(
        plan["provider_version"] == "0.0.94"
        and plan["harness_id"] == harness
        and plan["target_path"] == str(target)
        and plan["target_scope"] == "project"
        and plan["archive_digest"] == observed["artifact"]["archive_digest"]
        and plan["executable_digest"] == observed["artifact"]["executable_digest"]
        and plan["info_digest"] == observed["provider_info_digest"],
        "old-default plan did not retain its authenticated coordinates",
    )
    path = case / "original-plan.json"
    original_plan = json.dumps(plan).encode() + b"\n"
    path.write_bytes(original_plan)
    verify_files(target, canary)
    require(all(not (target / name).exists() for name in files), "old planning wrote files")
    arguments = [
        "configuration",
        "apply",
        "--state-dir",
        str(state),
        "--plan",
        str(path),
        "--plan-digest",
        result["plan_digest"],
    ]
    receipt = INSPECTION.invoke(binary, home, [*arguments, "--bundle", str(source)])
    require(
        receipt["state"] == "verified"
        and receipt["provider_version"] == "0.0.94"
        and receipt["harness_id"] == harness
        and receipt["scope"] == "project"
        and receipt["target"] == str(target)
        and receipt["action"] == plan["action"]
        and receipt["mutation_performed"] is True
        and receipt["operation_id"] == plan["operation_id"]
        and receipt["plan_digest"] == result["plan_digest"],
        "candidate retargeted the original plan",
    )
    verify_files(target, files | canary)
    source.unlink()
    target.rename(case / "retired checkout")
    require(INSPECTION.invoke(binary, home, arguments) == receipt, "old terminal receipt changed")
    require(not target.exists(), "old replay recreated the target")
    require(path.read_bytes() == original_plan, "original serialized plan was rewritten")
    return {
        "harness_id": harness,
        "target_scope": "project",
        "original_provider_version": "0.0.94",
        "original_profile_digest": previous_profile["digest"],
        "current_profile_digest": current_profile["digest"],
        "old_default_plan_applied_by_candidate": True,
        "original_plan_bytes_preserved": True,
        "completed_receipt_replayed_without_source_or_target": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "binary",
        "bundles",
        "state",
        "observations",
        "out",
        "baseline-binary",
        "baseline-bundles",
        "baseline-state",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    observation = json.loads(args.observations.read_text())
    version = observation["component_version"]
    require(
        isinstance(version, str)
        and re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version)
        is not None,
        "an exact canonical fixture version is required",
    )
    declarations = json.loads(
        (ROOT / f"apps/cli/tests/fixtures/provider-declarations-{version}.json").read_text()
    )
    observed = {
        r["provider_info"]["harness_id"]: r["provider_info"] for r in observation["reports"]
    }
    reports = {r["provider_info"]["harness_id"]: r for r in observation["reports"]}
    declared = {d["harness_id"]: d for d in declarations}
    require(
        len(observed) == len(declared) == 7 and observed == declared,
        "fixture declarations differ from authenticated observations",
    )
    require(observation["installation_qualified"] is False, "inspection was presented as a permit")
    binary = args.binary.resolve(strict=True)
    state = args.state.resolve(strict=True)
    bundles = args.bundles.resolve(strict=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="ai-stp-authenticated-lifecycles-") as temporary:
        home = Path(temporary).resolve(strict=True)
        require(
            INSPECTION.invoke(binary, home, ["capabilities"])["managed_provider_version"]
            == version,
            "the lifecycle binary is not the candidate",
        )
        require(
            INSPECTION.invoke(args.baseline_binary.resolve(strict=True), home, ["capabilities"])[
                "managed_provider_version"
            ]
            == "0.0.94",
            "the baseline binary does not have the original managed default",
        )
        compatibility = []
        for harness in ("claude-code", "codex"):
            compatibility.append(
                retained_plan(
                    binary,
                    args.baseline_binary.resolve(strict=True),
                    home,
                    args.baseline_state.resolve(strict=True),
                    args.baseline_bundles.resolve(strict=True),
                    harness,
                    reports[harness],
                )
            )
            print(f"Original 0.0.94 plan applied by candidate: {harness} project", flush=True)
        for harness, info in sorted(observed.items()):
            scopes = ["global", *[p["target_scope"] for p in info["scoped_projection_profiles"]]]
            for scope in scopes:
                results.append(
                    exercise(
                        binary, home, state, bundles, harness, scope, version, reports[harness]
                    )
                )
                print(f"Authenticated component lifecycle: {harness} {scope}", flush=True)
            project = next(
                p for p in info["scoped_projection_profiles"] if p["target_scope"] == "project"
            )
            for kind in sorted(project["component_kinds"]):
                require(re.fullmatch(r"[a-z]+", kind) is not None, "invalid project fixture kind")
                results.append(
                    exercise(
                        binary,
                        home,
                        state,
                        bundles,
                        harness,
                        "project",
                        version,
                        reports[harness],
                        kind,
                    )
                )
                print(f"Authenticated project-kind lifecycle: {harness} {kind}", flush=True)
        require(len(results) == 54, "the complete profile/project-kind proof matrix differs")
    args.out.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "evidence_type": "authenticated_provider_profile_lifecycles",
                "component_version": version,
                "consumer_commit": observation["consumer_commit"],
                "harness_activation_qualified": False,
                "corporate_binding_qualified": False,
                "interrupted_publication_qualified": False,
                "retained_plan_compatibility": compatibility,
                "cases": results,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
