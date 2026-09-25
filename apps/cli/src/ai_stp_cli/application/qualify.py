"""Qualify identities for the agent-first CLI. Missing cells stay not_run."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal, cast

from ai_stp_foundation.harnesses import HARNESS_ID_ORDER

type CellStatus = Literal["not_run", "pass", "fail"]
type MeasuredStatus = Literal["pass", "fail"]
type ArtifactClaim = Literal["not_built"]
type PromotionStage = Literal[
    "source_merged",
    "server_deployed",
    "cli_released",
    "cli_installed",
    "native_files_applied",
    "session_loaded",
]

PLATFORMS: Final[tuple[str, ...]] = ("linux-x86_64", "windows-x86_64", "macos-arm64")
AGENT_RUNS: Final[int] = 5
AGY_MODEL: Final[str] = "gpt-oss-120b-medium"
MEASURED_ENV: Final[str] = "AI_STP_QUALIFY_MEASURED"
PROMOTION_STAGES: Final[tuple[PromotionStage, ...]] = (
    "source_merged",
    "server_deployed",
    "cli_released",
    "cli_installed",
    "native_files_applied",
    "session_loaded",
)
AGENT_SCENARIOS: Final[tuple[str, ...]] = (
    "fresh-initialize-prompt",
    "no-reinit-on-coding",
    "install-exact-pin",
    "install-without-pin",
    "change-add-component",
    "switch-preserved-setup",
    "unsupported-project-local",
    "login-skipped",
    "login-idle-no-upload",
    "publish-private",
    "publish-public-filesystem",
    "author-directory",
    "compensated-install",
    "kill-after-apply",
    "concurrent-continue",
    "pending-reload-not-loaded",
    "auth-required-publish",
    "antigravity-limitation",
    "custom-home-section",
    "expert-recovery-no-dump",
)


def load_measured(path: Path | None = None) -> dict[str, object]:
    """Optional overlay of executed cells. Missing or unreadable is empty."""
    locator = path
    if locator is None:
        raw = os.environ.get(MEASURED_ENV, "")
        locator = Path(raw) if raw else None
    if locator is None or not locator.is_file():
        return {}
    try:
        parsed: object = json.loads(locator.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    items = cast(dict[object, object], parsed)
    return {str(key): value for key, value in items.items()}


def measured_status(value: object) -> MeasuredStatus | None:
    if value == "pass":
        return "pass"
    if value == "fail":
        return "fail"
    return None


def native_cells(
    *, measured: Mapping[tuple[str, str], MeasuredStatus] | None = None
) -> dict[tuple[str, str], CellStatus]:
    held: dict[tuple[str, str], CellStatus] = {
        (harness, platform): "not_run" for harness in HARNESS_ID_ORDER for platform in PLATFORMS
    }
    for key, status in (measured or {}).items():
        if key in held:
            held[key] = status
    return held


def agent_cells(
    *, measured: Mapping[tuple[str, int], MeasuredStatus] | None = None
) -> dict[tuple[str, int], CellStatus]:
    held: dict[tuple[str, int], CellStatus] = {
        (scenario, run): "not_run" for scenario in AGENT_SCENARIOS for run in range(AGENT_RUNS)
    }
    for key, status in (measured or {}).items():
        if key in held:
            held[key] = status
    return held


def promotion_status(
    *, measured: Mapping[PromotionStage, MeasuredStatus] | None = None
) -> dict[PromotionStage, CellStatus]:
    held: dict[PromotionStage, CellStatus] = dict.fromkeys(PROMOTION_STAGES, "not_run")
    for key, status in (measured or {}).items():
        if key in held:
            held[key] = status
    return held


def wheel_status() -> ArtifactClaim:
    return "not_built"


def extra_status() -> ArtifactClaim:
    return "not_built"


def content_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def tree_digest(root: Path) -> str:
    """Hash ordered, unambiguously framed paths and file content identities."""
    parts: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        parts.append((relative, content_digest(path.read_bytes())))
    framed = json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return content_digest(b"ai-stp-qualify-tree/2\0" + framed)


def native_platform(*, system: str | None = None, machine: str | None = None) -> str | None:
    """Overlay platform key for this process, or None when the cell is not in the matrix."""
    held_system = (system if system is not None else sys.platform).lower()
    held_machine = (machine if machine is not None else platform.machine()).lower()
    if held_system.startswith("linux") and held_machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    if held_system in {"win32", "windows"} and held_machine in {"amd64", "x86_64"}:
        return "windows-x86_64"
    if held_system in {"darwin", "macos"} and held_machine in {"arm64", "aarch64"}:
        return "macos-arm64"
    return None


def native_config_root(harness_id: str, environment: Mapping[str, str] | None = None) -> Path:
    """Catalogued user-config root for one harness in this environment."""
    if harness_id not in HARNESS_ID_ORDER:
        raise ValueError(harness_id)
    from ai_stp_cli.local.harnesses import DETECTORS, config_root

    held = None if environment is None else dict(environment)
    for detector in DETECTORS:
        if detector.harness_id == harness_id:
            return config_root(detector, held)
    raise ValueError(harness_id)


def native_marker_populated(root: Path) -> bool:
    return root.is_dir() and any(path.is_file() for path in root.rglob("*"))


def _object_map(value: object) -> dict[object, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[object, object], value)


def native_from_document(document: Mapping[str, object]) -> dict[tuple[str, str], MeasuredStatus]:
    raw = _object_map(document.get("native"))
    if raw is None:
        return {}
    held: dict[tuple[str, str], MeasuredStatus] = {}
    for key, value in raw.items():
        status = measured_status(value)
        if not isinstance(key, str) or status is None or ":" not in key:
            continue
        harness, _, platform = key.partition(":")
        held[(harness, platform)] = status
    return held


def agent_from_document(document: Mapping[str, object]) -> dict[tuple[str, int], MeasuredStatus]:
    raw = _object_map(document.get("agent"))
    if raw is None:
        return {}
    held: dict[tuple[str, int], MeasuredStatus] = {}
    for key, value in raw.items():
        status = measured_status(value)
        if not isinstance(key, str) or status is None or ":" not in key:
            continue
        scenario, _, index = key.rpartition(":")
        if scenario not in AGENT_SCENARIOS or not index.isdigit():
            continue
        run = int(index)
        if run >= AGENT_RUNS:
            continue
        held[(scenario, run)] = status
    return held


def promotion_from_document(document: Mapping[str, object]) -> dict[PromotionStage, MeasuredStatus]:
    raw = _object_map(document.get("promotion"))
    if raw is None:
        return {}
    held: dict[PromotionStage, MeasuredStatus] = {}
    for stage in PROMOTION_STAGES:
        status = measured_status(raw.get(stage))
        if status is not None:
            held[stage] = status
    return held


def isolation_from_document(document: Mapping[str, object]) -> dict[str, object]:
    """Optional isolation probe. Missing overlay is not_run, never a native pass."""
    raw = _object_map(document.get("isolation"))
    if raw is None:
        return {"status": "not_run"}
    status = raw.get("status")
    if status not in {"unavailable", "enforced"}:
        return {"status": "not_run"}
    held: dict[str, object] = {"status": status}
    os_name = raw.get("os_name")
    if isinstance(os_name, str) and os_name:
        held["os_name"] = os_name
    evidence = raw.get("evidence")
    if isinstance(evidence, list):
        items = cast(list[object], evidence)
        held["evidence"] = [str(item) for item in items]
    launcher_id = raw.get("launcher_id")
    if isinstance(launcher_id, str) and launcher_id:
        held["launcher_id"] = launcher_id
    return held


def report() -> dict[str, object]:
    """JSON-safe cells. Unmeasured stay not_run. Not a promotion claim."""
    document = load_measured()
    native = native_cells(measured=native_from_document(document))
    measured_agent = agent_from_document(document)
    agent = agent_cells(measured=measured_agent)
    promotion = promotion_status(measured=promotion_from_document(document))
    model = document.get("agy_model") if measured_agent else AGY_MODEL
    if not isinstance(model, str) or not model.strip():
        model = None if measured_agent else AGY_MODEL
    return {
        "native": {
            f"{harness}:{platform}": status for (harness, platform), status in native.items()
        },
        "agent": {f"{scenario}:{run}": status for (scenario, run), status in agent.items()},
        "promotion": dict(promotion),
        "isolation": isolation_from_document(document),
        "wheel": wheel_status(),
        "extra": extra_status(),
        "agy_model": model,
    }
