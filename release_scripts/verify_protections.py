"""Verify GitHub release protections without mutating repository settings.

The policy is repository-owned. Live evidence is collected through read-only
GitHub REST requests made by ``gh api``; callers may instead supply a normalized
snapshot for a deterministic audit or regression test.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_POLICY: Final[Path] = ROOT / ".github" / "release-protection-policy.json"
REPOSITORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ProtectionError(RuntimeError):
    """Protection evidence cannot be read or normalized safely."""


def _read_document(path: Path) -> dict[str, Any]:
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProtectionError(f"cannot read {path}: {error}") from error
    if not isinstance(held, dict):
        raise ProtectionError(f"{path} must contain a JSON object")
    return cast(dict[str, Any], held)


def _api(path: str) -> object:
    result = subprocess.run(
        ("gh", "api", path),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        raise ProtectionError(detail[-1] if detail else f"gh api {path} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ProtectionError(f"gh api {path} returned invalid JSON") from error


def _optional_api(path: str, errors: list[str]) -> object | None:
    try:
        return _api(path)
    except ProtectionError as error:
        errors.append(f"{path}: {error}")
        return None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else ()


def _enabled(parent: Mapping[str, object], field: str) -> bool:
    return _mapping(parent.get(field)).get("enabled") is True


def _branch_evidence(repository: str, branch: str, errors: list[str]) -> dict[str, object]:
    path = f"repos/{repository}/branches/{branch}/protection"
    raw = _optional_api(path, errors)
    protection = _mapping(raw)
    if not protection:
        return {"available": False}

    checks = _mapping(protection.get("required_status_checks"))
    contexts = {value for value in _sequence(checks.get("contexts")) if isinstance(value, str)}
    for check in _sequence(checks.get("checks")):
        context = _mapping(check).get("context")
        if isinstance(context, str):
            contexts.add(context)
    reviews = _mapping(protection.get("required_pull_request_reviews"))
    return {
        "available": True,
        "required_status_checks": sorted(contexts),
        "strict_status_checks": checks.get("strict") is True,
        "minimum_approvals": reviews.get("required_approving_review_count", 0),
        "dismiss_stale_reviews": reviews.get("dismiss_stale_reviews") is True,
        "require_last_push_approval": reviews.get("require_last_push_approval") is True,
        "require_conversation_resolution": _enabled(protection, "required_conversation_resolution"),
        "enforce_admins": _enabled(protection, "enforce_admins"),
        "allow_force_pushes": _enabled(protection, "allow_force_pushes"),
        "allow_deletions": _enabled(protection, "allow_deletions"),
    }


def _environment_evidence(repository: str, name: str, errors: list[str]) -> dict[str, object]:
    path = f"repos/{repository}/environments/{name}"
    raw = _optional_api(path, errors)
    environment = _mapping(raw)
    if not environment:
        return {"available": False}
    reviewers = 0
    for rule in _sequence(environment.get("protection_rules")):
        held = _mapping(rule)
        if held.get("type") == "required_reviewers":
            listed = held.get("reviewers", [])
            if isinstance(listed, list):
                reviewers = len(listed)
    deployment = _mapping(environment.get("deployment_branch_policy"))
    policies_raw = _optional_api(f"{path}/deployment-branch-policies", errors)
    policies = []
    for policy in _sequence(_mapping(policies_raw).get("branch_policies")):
        held = _mapping(policy)
        policy_name = held.get("name")
        policy_type = held.get("type")
        if isinstance(policy_name, str):
            policies.append(
                {
                    "name": policy_name,
                    "type": policy_type if isinstance(policy_type, str) else "unknown",
                }
            )
    return {
        "available": True,
        "minimum_reviewers": reviewers,
        "protected_branches": deployment.get("protected_branches") is True,
        "custom_branch_policies": deployment.get("custom_branch_policies") is True,
        "deployment_policies": policies,
    }


def _tag_evidence(repository: str, pattern: str, errors: list[str]) -> dict[str, object]:
    raw = _optional_api(f"repos/{repository}/rulesets", errors)
    summaries = _sequence(raw)
    deletion = False
    force_update = False
    matching_rulesets: list[int] = []
    for summary in summaries:
        held = _mapping(summary)
        identifier = held.get("id")
        if not isinstance(identifier, int):
            continue
        detail_raw = _optional_api(f"repos/{repository}/rulesets/{identifier}", errors)
        detail = _mapping(detail_raw)
        if detail.get("enforcement") != "active":
            continue
        ref_names = _mapping(_mapping(detail.get("conditions")).get("ref_name"))
        includes = _sequence(ref_names.get("include"))
        if pattern not in includes:
            continue
        matching_rulesets.append(identifier)
        types = {
            rule_type
            for rule in _sequence(detail.get("rules"))
            if isinstance((rule_type := _mapping(rule).get("type")), str)
        }
        deletion = deletion or "deletion" in types
        force_update = force_update or "non_fast_forward" in types
    return {
        "pattern": pattern,
        "block_deletion": deletion,
        "block_force_update": force_update,
        "matching_rulesets": matching_rulesets,
    }


def collect_live(repository: str, policy: Mapping[str, object]) -> dict[str, object]:
    """Collect a normalized read-only snapshot from GitHub."""
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ProtectionError("repository must have the form owner/name")
    errors: list[str] = []
    repository_raw = _optional_api(f"repos/{repository}", errors)
    workflow_raw = _optional_api(f"repos/{repository}/actions/permissions/workflow", errors)
    repository_data = _mapping(repository_raw)
    workflow = _mapping(workflow_raw)

    branches_policy = _mapping(policy.get("branches"))
    branches = {
        name: _branch_evidence(repository, name, errors)
        for name in branches_policy
        if isinstance(name, str)
    }
    environments_policy = _mapping(policy.get("environments"))
    environments = {
        name: _environment_evidence(repository, name, errors)
        for name in environments_policy
        if isinstance(name, str)
    }
    tag_policy = _mapping(policy.get("tag_rules"))
    pattern = tag_policy.get("pattern")
    tag_rules = (
        _tag_evidence(repository, pattern, errors)
        if isinstance(pattern, str)
        else {"pattern": "", "block_deletion": False, "block_force_update": False}
    )
    return {
        "schema_version": 1,
        "repository": {
            "visibility": repository_data.get("visibility"),
            "default_workflow_permissions": workflow.get("default_workflow_permissions"),
            "can_approve_pull_request_reviews": workflow.get("can_approve_pull_request_reviews"),
        },
        "branches": branches,
        "environments": environments,
        "tag_rules": tag_rules,
        "collection_errors": errors,
    }


def verify(policy: Mapping[str, object], evidence: Mapping[str, object]) -> list[str]:
    """Return every policy mismatch; an empty list is a complete pass."""
    violations: list[str] = []
    for field, expected in _mapping(policy.get("repository")).items():
        actual = _mapping(evidence.get("repository")).get(field)
        if actual != expected:
            violations.append(f"repository.{field}: expected {expected!r}, got {actual!r}")

    actual_branches = _mapping(evidence.get("branches"))
    for branch, expected_raw in _mapping(policy.get("branches")).items():
        expected = _mapping(expected_raw)
        actual = _mapping(actual_branches.get(branch))
        if actual.get("available") is not True:
            violations.append(f"branches.{branch}: protection is unavailable")
            continue
        required = set(cast(Sequence[str], expected.get("required_status_checks", [])))
        observed = set(cast(Sequence[str], actual.get("required_status_checks", [])))
        missing = sorted(required - observed)
        if missing:
            violations.append(f"branches.{branch}: missing status checks {missing}")
        for field, expected_value in expected.items():
            if field == "required_status_checks":
                continue
            actual_value = actual.get(field)
            if field == "minimum_approvals":
                if not isinstance(actual_value, int) or actual_value < cast(int, expected_value):
                    violations.append(
                        f"branches.{branch}.{field}: expected at least {expected_value}, "
                        f"got {actual_value!r}"
                    )
            elif actual_value != expected_value:
                violations.append(
                    f"branches.{branch}.{field}: expected {expected_value!r}, got {actual_value!r}"
                )

    actual_environments = _mapping(evidence.get("environments"))
    for name, expected_raw in _mapping(policy.get("environments")).items():
        expected = _mapping(expected_raw)
        actual = _mapping(actual_environments.get(name))
        if actual.get("available") is not True:
            violations.append(f"environments.{name}: environment is unavailable")
            continue
        reviewers = actual.get("minimum_reviewers")
        minimum = expected.get("minimum_reviewers")
        if not isinstance(reviewers, int) or not isinstance(minimum, int) or reviewers < minimum:
            violations.append(
                f"environments.{name}.minimum_reviewers: expected at least {minimum}, "
                f"got {reviewers!r}"
            )
        for field in ("protected_branches", "custom_branch_policies"):
            if actual.get(field) != expected.get(field):
                violations.append(
                    f"environments.{name}.{field}: expected {expected.get(field)!r}, "
                    f"got {actual.get(field)!r}"
                )
        tag = expected.get("required_tag_policy")
        if isinstance(tag, str):
            policies = _sequence(actual.get("deployment_policies"))
            matches = any(
                _mapping(item).get("name") == tag and _mapping(item).get("type") == "tag"
                for item in policies
            )
            if not matches:
                violations.append(f"environments.{name}: missing tag deployment policy {tag!r}")

    expected_tag = _mapping(policy.get("tag_rules"))
    actual_tag = _mapping(evidence.get("tag_rules"))
    for field, expected in expected_tag.items():
        if actual_tag.get(field) != expected:
            violations.append(
                f"tag_rules.{field}: expected {expected!r}, got {actual_tag.get(field)!r}"
            )
    errors = evidence.get("collection_errors", [])
    if isinstance(errors, list):
        violations.extend(f"collection: {error}" for error in errors if isinstance(error, str))
    return violations


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="ai-engineers-guild/ai_stp")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--write-snapshot", type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        policy = _read_document(options.policy)
        evidence = (
            _read_document(options.snapshot)
            if options.snapshot is not None
            else collect_live(options.repository, policy)
        )
        if options.write_snapshot is not None:
            options.write_snapshot.write_text(
                json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        violations = verify(policy, evidence)
    except ProtectionError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2
    report = {"ok": not violations, "violations": violations}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
