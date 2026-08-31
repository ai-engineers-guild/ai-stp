"""Load the small, reviewed legal-policy source set bundled with the service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class BuiltinPolicy:
    slug: str
    kind: str
    locale: str
    title: str
    policy_version: str
    effective_at: date
    markdown_source: str
    source_path: str


_PATHS = (
    "en/service-rules/1.0/document.md",
    "en/privacy/1.0/document.md",
    "en/personal-data-consent/1.0/document.md",
    "en/cookies/1.0/document.md",
    "en/licensing/1.0/document.md",
    "ru/service-rules/1.0/document.md",
    "ru/privacy/1.0/document.md",
    "ru/personal-data-consent/1.0/document.md",
    "ru/cookies/1.0/document.md",
    "ru/licensing/1.0/document.md",
)


def _source_root() -> Path:
    configured = os.environ.get("AI_STP_LEGAL_SOURCE_DIR")
    if configured:
        root = Path(configured)
        if root.is_dir():
            return root
        raise FileNotFoundError(f"legal source directory is missing: {root}")
    for parent in (Path.cwd(), *Path(__file__).resolve().parents):
        candidate = parent / "docs-user-facing" / "legal"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("docs-user-facing/legal is missing")


def _parse(path: str, *, root: Path) -> BuiltinPolicy:
    raw = (root / path).read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"legal policy {path} has no frontmatter")
    _, header, body = raw.split("---\n", 2)
    fields: dict[str, str] = {}
    for line in header.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"legal policy {path} has invalid frontmatter")
        fields[key.strip()] = value.strip().strip('"')
    required = ("slug", "kind", "locale", "title", "policy_version", "effective_at")
    if any(not fields.get(key) for key in required):
        raise ValueError(f"legal policy {path} has incomplete frontmatter")
    return BuiltinPolicy(
        slug=fields["slug"],
        kind=fields["kind"],
        locale=fields["locale"],
        title=fields["title"],
        policy_version=fields["policy_version"],
        effective_at=date.fromisoformat(fields["effective_at"]),
        markdown_source=body.lstrip(),
        source_path=f"docs-user-facing/legal/{path}",
    )


def builtin_policies() -> tuple[BuiltinPolicy, ...]:
    """Return the fixed repository-backed policy set in deterministic order."""
    root = _source_root()
    return tuple(_parse(path, root=root) for path in _PATHS)
