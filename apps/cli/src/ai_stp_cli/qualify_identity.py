"""Content identities for qualification inputs; no model or release claims."""

from __future__ import annotations

import importlib.util
import json
import re
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import cast

from ai_stp_cli.application.qualify import content_digest
from ai_stp_cli.runtime import cli_version, installation
from ai_stp_contracts.cli_copy import INITIALIZE_PROMPT

NAMESPACES = (
    "ai_stp_cli",
    "ai_stp_foundation",
    "ai_stp_contracts",
    "ai_stp_passports",
    "ai_stp_sources",
    "ai_stp_assurance",
)


def source_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def payload_digest(roots: dict[str, Path]) -> str:
    entries = [
        (f"{name}/{path.relative_to(root).as_posix()}", content_digest(path.read_bytes()))
        for name, root in sorted(roots.items())
        for path in source_files(root)
    ]
    return content_digest(json.dumps(entries, separators=(",", ":")).encode("utf-8"))


def loaded_roots() -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for name in NAMESPACES:
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            raise ValueError(f"qualification cannot identify {name}")
        roots[name] = Path(spec.origin).parent
    return roots


def canonical_skill(repo: Path) -> Path:
    if installation() == "distribution":
        return Path(__file__).parent / "skills" / "canonical"
    return repo / "skills" / "canonical" / "ai-stp"


def installed_archive_digest() -> str | None:
    """PEP 610 records the installed archive, separately from loaded payload bytes."""
    try:
        raw = distribution("ai-stp-cli").read_text("direct_url.json")
    except PackageNotFoundError:
        return None
    if raw is None:
        return None
    try:
        body: object = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    origin = cast(dict[str, object], body)
    archive = origin.get("archive_info")
    if not isinstance(archive, dict):
        return None
    info = cast(dict[str, object], archive)
    hashes = info.get("hashes")
    if isinstance(hashes, dict):
        digest = cast(dict[str, object], hashes).get("sha256")
        if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
            return f"sha256:{digest}"
    legacy = info.get("hash")
    if isinstance(legacy, str) and re.fullmatch(r"sha256=[0-9a-f]{64}", legacy):
        return legacy.replace("=", ":", 1)
    return None


def execution_identity(repo: Path, *, docker_image: str | None = None) -> dict[str, object]:
    """Bind loaded host modules or the mounted checkout and the actual copied Skill."""
    roots = loaded_roots()
    if docker_image is not None:
        for name in roots:
            package = name.removeprefix("ai_stp_")
            parent = "apps" if package == "cli" else "packages"
            roots[name] = repo / parent / package / "src" / name
        if not all(root.is_dir() for root in roots.values()):
            raise ValueError("Docker qualification requires the complete source checkout")
    skill = canonical_skill(repo)
    if not (skill / "SKILL.md").is_file():
        raise ValueError("qualification cannot identify the copied control Skill")
    return {
        "schema_version": 1,
        "execution": "docker_checkout" if docker_image else "host",
        "docker_image": docker_image,
        "installation": "source" if docker_image else installation(),
        "cli_version": cli_version(),
        "installed_archive_digest": None if docker_image else installed_archive_digest(),
        "payload_digest": payload_digest(roots),
        "skill_digest": payload_digest({"skill": skill}),
        "initialize_prompt_digest": content_digest(INITIALIZE_PROMPT.encode("utf-8")),
    }
