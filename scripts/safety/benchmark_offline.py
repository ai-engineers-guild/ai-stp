#!/usr/bin/env python3
"""Deterministic, network-free safety-scan performance evidence.

The corpus and execution order are fixed; wall-clock values are measurements of
the current machine and are not treated as a cross-machine pass/fail gate.
External scanner CLIs are forcibly disabled so this command cannot download or
contact a service.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "platform" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "foundation" / "src"))

from ai_stp_foundation.digests import digest_bytes  # noqa: E402
from ai_stp_platform.safety.metrics import snapshot  # noqa: E402
from ai_stp_platform.safety.orchestrator import (  # noqa: E402
    clear_safety_cache,
    run_safety_suite,
)
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN  # noqa: E402

DEFAULT_ITERATIONS = 3
DEFAULT_CONCURRENCY = 1
BENCHMARK_SCHEMA = "safety-offline-benchmark-v1"


@dataclass(frozen=True, slots=True)
class OfflineCase:
    name: str
    component_type: str
    files: tuple[tuple[str, bytes], ...]


CASES = (
    OfflineCase(
        name="clean_instruction",
        component_type="instruction",
        files=(("INSTRUCTIONS.md", b"# Instructions\n\nUse the safe path.\n"),),
    ),
    OfflineCase(
        name="clean_skill",
        component_type="skill",
        files=(("SKILL.md", b"---\nname: clean\ndescription: clean\n---\n# Clean\n"),),
    ),
    OfflineCase(
        name="clean_mcp",
        component_type="mcp",
        files=(
            (
                ".mcp.json",
                b'{"mcpServers":{"demo":{"command":"node","args":["./server.js"]}}}',
            ),
            ("server.js", b"console.log('offline');\n"),
        ),
    ),
)


def build_payload(files: tuple[tuple[str, bytes], ...]) -> bytes:
    """Build the same ZIP bytes on every run, independent of wall clock."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in files:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, content)
    return buffer.getvalue()


def _quantile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def _commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


async def _run_case(
    case: OfflineCase, iterations: int, semaphore: asyncio.Semaphore
) -> dict[str, object]:
    payload = build_payload(case.files)
    digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
    wall_values: list[int] = []
    failed: list[str] = []
    async with semaphore:
        for _ in range(iterations):
            clear_safety_cache()
            started = time.perf_counter()
            result = await run_safety_suite(
                passport={"component_type": case.component_type, "artifact": {"digest": digest}},
                content_digest=digest,
                object_kind="component",
                profile="standard",
                artifact_bytes=payload,
                use_cache=False,
            )
            wall_values.append(int((time.perf_counter() - started) * 1000))
            failed.extend(
                outcome.check_id
                for outcome in result.outcomes
                if outcome.mandatory and outcome.result == "failed"
            )
    return {
        "name": case.name,
        "component_type": case.component_type,
        "artifact_digest": digest,
        "iterations": iterations,
        "failed_mandatory_checks": sorted(set(failed)),
        "wall_ms": {
            "min": min(wall_values),
            "p50": _quantile(wall_values, 0.50),
            "p95": _quantile(wall_values, 0.95),
            "max": max(wall_values),
        },
    }


async def _run(iterations: int, concurrency: int) -> dict[str, object]:
    # This is deliberately stronger than relying on the caller's environment.
    os.environ["AI_STP_SAFETY_EXTERNAL_CLI"] = "0"
    os.environ["AI_STP_SAFETY_SANDBOX"] = "off"
    semaphore = asyncio.Semaphore(concurrency)
    cases = await asyncio.gather(*(_run_case(case, iterations, semaphore) for case in CASES))
    metrics = snapshot()
    metrics.pop("safety_last_scan_at", None)
    return {
        "schema_version": BENCHMARK_SCHEMA,
        "commit": _commit(),
        "network": "disabled",
        "external_cli": "disabled",
        "iterations": iterations,
        "concurrency": concurrency,
        "case_order": [case.name for case in CASES],
        "cases": cases,
        "ok": all(not case["failed_mandatory_checks"] for case in cases),
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args()
    if args.iterations < 1 or args.concurrency < 1:
        parser.error("--iterations and --concurrency must be positive")
    evidence = asyncio.run(_run(args.iterations, args.concurrency))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
