"""Actual OSV offline-layout, finding and unavailable-data controls."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_stp_platform.safety.adapters import osv
from ai_stp_platform.safety.policy import CHECK_REGISTRY
from ai_stp_platform.safety.types import ArtifactManifest


def osv_cases(root: Path) -> dict[str, Any]:
    cache = Path("/var/lib/ai_stp/osv/qualification")
    database = cache / "osv-scalibr" / "PyPI"
    database.mkdir(parents=True)
    advisory: dict[str, Any] = {
        "schema_version": "1.6.0",
        "id": "AI-STP-QUALIFICATION-2026-0001",
        "modified": "2026-01-01T00:00:00Z",
        "published": "2026-01-01T00:00:00Z",
        "summary": "Controlled synthetic fixture",
        "affected": [
            {
                "package": {"ecosystem": "PyPI", "name": "qualification-probe"},
                "versions": ["1.0.0"],
                "ranges": [
                    {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.0.1"}]}
                ],
            }
        ],
    }
    archive = database / "all.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(advisory["id"] + ".json", json.dumps(advisory))
    marker = cache / ".ai_stp_osv_refreshed_at"
    marker.write_text(datetime.now(UTC).isoformat())
    os.environ["AI_STP_OSV_OFFLINE_DIR"] = str(cache)
    tree = root / "python"
    tree.mkdir()
    spec = next(item for item in CHECK_REGISTRY if item.check_id.endswith("osv"))
    manifest = ArtifactManifest(component_type="cli", flags={"manifests"}, languages={"python"})
    results: dict[str, Any] = {}
    for name, version in [("vulnerable", "1.0.0"), ("clean", "1.0.1")]:
        (tree / "requirements.txt").write_text("qualification-probe==" + version + "\n")
        result = osv.run(tree, manifest, spec)
        assert result.result == ("warning" if name == "vulnerable" else "passed"), (
            name,
            result.result,
            result.detail,
        )
        assert result.detail["offline"] is True
        assert bool(result.findings) == (name == "vulnerable")
        results[name] = {"result": result.result, "findings": len(result.findings)}
    os.utime(marker, (0, 0))
    stale = osv.run(tree, manifest, spec)
    assert stale.result == "not_run" and stale.detail["reason"] == "offline_db_stale"
    results["stale"] = {"result": stale.result, "reason": stale.detail["reason"]}
    marker.unlink()
    unstamped = osv.run(tree, manifest, spec)
    assert unstamped.result == "not_run" and not unstamped.findings
    results["unstamped"] = {"result": unstamped.result, "reason": unstamped.detail["reason"]}
    marker.write_text(datetime.now(UTC).isoformat())
    archive.write_bytes(b"controlled corrupt archive")
    corrupt = osv.run(tree, manifest, spec)
    assert corrupt.result in {"not_run", "degraded"} and not corrupt.findings
    results["corrupt"] = {"result": corrupt.result, "reason": corrupt.detail["reason"]}
    os.environ["AI_STP_OSV_OFFLINE_DIR"] = str(root / "missing")
    missing = osv.run(tree, manifest, spec)
    assert missing.result == "not_run" and missing.detail["reason"] == "offline_db_missing"
    results["missing"] = {"result": missing.result, "reason": missing.detail["reason"]}
    return results
