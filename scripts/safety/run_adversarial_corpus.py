#!/usr/bin/env python3
"""Run the filesystem safety corpus sequentially through the platform backend."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any, cast, get_args

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "safety-corpus"
sys.path[:0] = [
    str(ROOT / "apps" / "platform" / "src"),
    str(ROOT / "packages" / "foundation" / "src"),
]

from ai_stp_foundation.digests import digest_bytes  # noqa: E402
from ai_stp_passports.versions import ComponentType  # noqa: E402
from ai_stp_platform.safety.adapters import setup_aggregate  # noqa: E402
from ai_stp_platform.safety.orchestrator import clear_safety_cache, run_safety_suite  # noqa: E402
from ai_stp_platform.safety.policy import POLICY_VERSION  # noqa: E402
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN  # noqa: E402

EXPECTED_KINDS = frozenset(get_args(ComponentType.__value__)) | {"setup"}


def _payload(directory: Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(directory).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


async def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case["id"])
    kind = str(case["kind"])
    expected = cast(dict[str, Any], case["expected"])
    directory = CORPUS / str(case["path"])
    started = time.perf_counter()
    clear_safety_cache()
    if kind == "setup":
        document = json.loads((directory / "setup.json").read_text(encoding="utf-8"))
        setup_aggregate.set_pin_context(cast(list[dict[str, Any]], document["pins"]))
        try:
            raw = (directory / "setup.json").read_bytes()
            result = await run_safety_suite(
                passport={"kind": "setup", "components": []},
                content_digest=digest_bytes(ARTIFACT_DIGEST_DOMAIN, raw),
                object_kind="setup",
                use_cache=False,
            )
        finally:
            setup_aggregate.clear_pin_context()
    else:
        payload = _payload(directory)
        digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
        result = await run_safety_suite(
            passport={"component_type": kind, "artifact": {"digest": digest}},
            content_digest=digest,
            object_kind="component",
            artifact_bytes=payload,
            use_cache=False,
        )

    findings = [
        {"check_id": outcome.check_id, "rule_id": finding.rule_id, "severity": finding.severity}
        for outcome in result.outcomes
        for finding in outcome.findings
    ]
    expected_pair = (expected.get("check_id"), expected.get("rule_id"))
    detected = not expected or any(
        (finding["check_id"], finding["rule_id"]) == expected_pair for finding in findings
    )
    return {
        "id": case_id,
        "kind": kind,
        "class": case["class"],
        "expected": expected,
        "detected": detected,
        "findings": findings,
        "wall_ms": int((time.perf_counter() - started) * 1000),
    }


async def run_corpus() -> dict[str, Any]:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    cases = cast(list[dict[str, Any]], manifest["cases"])
    results = [await _run_case(case) for case in cases]
    malicious = [item for item in results if item["class"] == "malicious"]
    benign = [item for item in results if item["class"] == "benign"]
    counts = Counter(str(item["kind"]) for item in results)
    missed = [str(item["id"]) for item in malicious if not item["detected"]]
    false_positives = [str(item["id"]) for item in benign if item["findings"]]
    per_kind: dict[str, dict[str, Any]] = {}
    for kind in sorted(counts):
        kind_malicious = [item for item in malicious if item["kind"] == kind]
        kind_benign = [item for item in benign if item["kind"] == kind]
        per_kind[kind] = {
            "cases": counts[kind],
            "malicious": len(kind_malicious),
            "benign": len(kind_benign),
            "recall": sum(bool(item["detected"]) for item in kind_malicious) / len(kind_malicious),
            "false_positive_rate": sum(bool(item["findings"]) for item in kind_benign)
            / len(kind_benign),
        }
    rule_hits = Counter(
        f"{finding['check_id']}:{finding['rule_id']}"
        for item in results
        for finding in item["findings"]
    )
    shape_errors: list[str] = []
    if set(per_kind) != EXPECTED_KINDS:
        shape_errors.append("kind_set_mismatch")
    for kind, values in per_kind.items():
        if not 10 <= values["malicious"] <= 20:
            shape_errors.append(f"{kind}:malicious_count")
        if values["benign"] < 2:
            shape_errors.append(f"{kind}:benign_count")
    return {
        "schema_version": manifest["schema_version"],
        "policy_version": POLICY_VERSION,
        "profile": "standard",
        "execution": "sequential",
        "network": "disabled",
        "external_cli": "disabled",
        "case_count": len(results),
        "cases_by_kind": dict(sorted(counts.items())),
        "per_kind": per_kind,
        "rule_hits": dict(sorted(rule_hits.items())),
        "malicious_count": len(malicious),
        "benign_count": len(benign),
        "malicious_recall": (len(malicious) - len(missed)) / len(malicious),
        "benign_false_positive_rate": len(false_positives) / len(benign),
        "missed": missed,
        "false_positives": false_positives,
        "shape_errors": shape_errors,
        "ok": not missed and not false_positives and not shape_errors,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.environ["AI_STP_SAFETY_EXTERNAL_CLI"] = "0"
    os.environ["AI_STP_SAFETY_SANDBOX"] = "off"
    report = asyncio.run(run_corpus())
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
