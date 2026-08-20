"""artifact_unpack check — tree already materialised by orchestrator."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    if not tree.is_dir():
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="failed",
            mandatory=spec.mandatory,
            tool_name="workdir",
            detail={"reason": "tree_missing"},
        )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="passed",
        mandatory=spec.mandatory,
        tool_name="workdir",
        detail={"file_count": manifest.file_count, "total_bytes": manifest.total_bytes},
    )
