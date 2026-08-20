"""Plan non-overlapping checks from kind + artifact manifest + profile."""

from __future__ import annotations

from ai_stp_platform.safety.policy import CheckSpec, SafetyProfile, registry_by_id
from ai_stp_platform.safety.types import ArtifactManifest


def plan_checks(
    *,
    object_kind: str,
    manifest: ArtifactManifest | None,
    profile: SafetyProfile,
) -> list[CheckSpec]:
    """Return ordered applicable checks. One primary engine per family.

    Setup never re-scans pin trees: only ``setup_pin_aggregate``.
    """
    registry = registry_by_id()
    if object_kind == "setup":
        return [
            spec for spec in registry.values() if "setup" in spec.kinds and profile in spec.profiles
        ]

    selected: list[CheckSpec] = []
    seen_families: set[str] = set()
    languages: set[str] = set(manifest.languages) if manifest else set()
    flags: set[str] = set(manifest.flags) if manifest else set()

    for spec in sorted(registry.values(), key=lambda s: (s.stage, s.check_id)):
        if "component" not in spec.kinds:
            continue
        if profile not in spec.profiles:
            continue
        if spec.languages and not (spec.languages & languages):
            continue
        if spec.requires_any_flag and not (spec.requires_any_flag & flags):
            # Always-run checks have empty requires_any_flag
            continue
        # Family ownership: first planned check wins as primary for that family
        # in this plan (registry order is the authority).
        # secrets_heuristic + secrets_gitleaks share family "secrets":
        # both run but normalizer merges findings; both remain for quorum.
        # shell_obfuscation and sast_shell stay as separate families.
        if spec.family in seen_families and spec.family not in {
            "shell_obfuscation",
            "sast_shell",
            "secrets",
        }:
            continue
        seen_families.add(spec.family)
        selected.append(spec)

    return selected
