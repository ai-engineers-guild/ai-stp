"""Detect languages and security-relevant flags in an unpacked artifact."""

from __future__ import annotations

from pathlib import Path

from ai_stp_platform.safety.types import ArtifactManifest

_IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}

_SHELL_SUFFIX = {".sh", ".bash", ".zsh", ".ksh"}
_PY_SUFFIX = {".py"}
_JS_SUFFIX = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
_GO_SUFFIX = {".go"}
_RS_SUFFIX = {".rs"}
_BIN_SUFFIX = {".exe", ".dll", ".so", ".dylib", ".bin", ".wasm"}
_PDF_SUFFIX = {".pdf"}
_HTML_SUFFIX = {".html", ".htm"}
_TEXT_SUFFIX = {
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".py",
    ".js",
    ".ts",
    ".sh",
    ".bash",
    ".go",
    ".rs",
    ".env.example",
}


def _component_type(passport: dict[str, object]) -> str:
    raw = passport.get("component_type")
    if isinstance(raw, str) and raw:
        return raw
    # Fallback heuristics from path conventions
    return "unknown"


def detect_manifest(root: Path, *, passport: dict[str, object]) -> ArtifactManifest:
    """Walk ``root`` and return language/flags manifest."""
    languages: set[str] = set()
    flags: set[str] = set()
    text_files: list[str] = []
    shell_files: list[str] = []
    python_files: list[str] = []
    file_count = 0
    total_bytes = 0
    ctype = _component_type(passport)

    if ctype in {"skill", "agent"}:
        flags.add("skill_md" if ctype == "skill" else "agent")
    if ctype == "agent":
        flags.add("agent")
    if ctype == "mcp":
        flags.add("mcp")
    if ctype == "hook":
        flags.add("hooks")

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _IGNORE_DIRS for part in path.parts):
            continue
        file_count += 1
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        total_bytes += size
        rel = path.relative_to(root).as_posix()
        name = path.name.lower()
        suffix = path.suffix.lower()

        if name in {".mcp.json", "claude_desktop_config.json"} or "mcp" in rel.lower():
            flags.add("mcp")
        if name == "skill.md" or rel.endswith("/skill.md"):
            flags.add("skill_md")
        # Claude Code hooks live in settings; mark known hook config files.
        if name in {"settings.json", "hooks.json", "hooks.yaml", "hooks.yml"} or (
            "hooks" in rel.lower() and name.endswith((".json", ".yaml", ".yml"))
        ):
            flags.add("hooks")
        if suffix in _SHELL_SUFFIX or (suffix == "" and _looks_like_shell(path)):
            languages.add("shell")
            shell_files.append(rel)
        if suffix in _PY_SUFFIX:
            languages.add("python")
            python_files.append(rel)
        if suffix in _JS_SUFFIX or name in {
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
        }:
            languages.add("js")
        if suffix in _GO_SUFFIX or name == "go.mod":
            languages.add("go")
        if suffix in _RS_SUFFIX or name == "cargo.toml":
            languages.add("rust")
        if name in {
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "requirements.txt",
            "pyproject.toml",
            "poetry.lock",
            "go.mod",
            "go.sum",
            "cargo.lock",
            "cargo.toml",
        }:
            flags.add("manifests")
        if suffix in _BIN_SUFFIX or (size > 0 and _looks_binary(path)):
            flags.add("binary")
        if suffix in _PDF_SUFFIX:
            flags.add("pdf")
        if suffix in _HTML_SUFFIX:
            flags.add("html")
        if size <= 1_000_000 and (
            suffix in _TEXT_SUFFIX or name in {"skill.md", "agents.md", "claude.md"}
        ):
            text_files.append(rel)

    # Passport-declared type forces skill/agent scanners
    if ctype == "skill":
        flags.add("skill_md")
    if ctype == "agent":
        flags.add("agent")
        flags.add("skill_md")
    if ctype == "hook":
        flags.add("hooks")
    if ctype == "mcp":
        flags.add("mcp")

    return ArtifactManifest(
        component_type=ctype,
        languages=languages,
        flags=flags,
        file_count=file_count,
        total_bytes=total_bytes,
        text_files=text_files,
        shell_files=shell_files,
        python_files=python_files,
    )


def _looks_like_shell(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(64)
    except OSError:
        return False
    return head.startswith(b"#!") and (b"sh" in head or b"bash" in head)


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(512)
    except OSError:
        return False
    return b"\x00" in chunk
