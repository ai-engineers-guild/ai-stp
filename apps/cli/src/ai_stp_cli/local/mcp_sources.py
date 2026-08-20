"""Bounded, manifest-led discovery of MCP server source packages.

An ``mcp`` substring is not evidence.  This adapter starts from a package
manifest, requires an MCP SDK dependency, resolves a declared entry point, and
then verifies that exact source file imports the SDK.  It never executes the
package and returns only allowlisted structural evidence.
"""

import ast
import json
import os
import re
import stat
import tomllib
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.local.component_sources import Diagnostic

MAX_MANIFEST_BYTES: Final[int] = 1024 * 1024
MAX_SOURCE_BYTES: Final[int] = 1024 * 1024
MAX_DIRECTORIES: Final[int] = 2000
MAX_DIRECTORY_ENTRIES: Final[int] = 1000
MAX_DEPTH: Final[int] = 6
EXCLUDED_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "cache",
        "coverage",
        "dist",
        "docs",
        "fixtures",
        "node_modules",
        "site-packages",
        "tests",
        "vendor",
    }
)
MCP_SOURCE: Final[str] = "modelcontextprotocol.io/docs/develop/build-server"
_PYTHON_DEPENDENCIES: Final[frozenset[str]] = frozenset({"mcp", "fastmcp"})
_TYPESCRIPT_DEPENDENCIES: Final[frozenset[str]] = frozenset(
    {"@modelcontextprotocol/sdk", "fastmcp"}
)
_PATH_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\s)([^\s'\"]+\.(?:js|mjs|cjs|ts|mts|cts))(?:\s|$)"
)


@dataclass(frozen=True)
class Candidate:
    """One source package whose declared entry point is an MCP server."""

    root: Path
    entry_points: tuple[str, ...]
    transports: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Report:
    candidates: tuple[Candidate, ...]
    diagnostics: tuple[Diagnostic, ...]


def discover(project: Path) -> Report:
    """Inspect bounded package roots below one explicitly selected project."""
    if _directory_mode(project) is None:
        return Report((), ())
    candidates: list[Candidate] = []
    diagnostics: list[Diagnostic] = []
    stack: list[tuple[Path, int]] = [(project, 0)]
    visited = 0
    while stack:
        root, depth = stack.pop()
        visited += 1
        if visited > MAX_DIRECTORIES:
            diagnostics.append(_limit("the MCP package search exceeded its directory limit"))
            break
        python = _python_candidate(root, diagnostics)
        node = _node_candidate(root, diagnostics)
        if python is not None:
            candidates.append(python)
        if node is not None:
            candidates.append(node)
        if depth >= MAX_DEPTH:
            continue
        try:
            entries = list(islice(root.iterdir(), MAX_DIRECTORY_ENTRIES + 1))
        except OSError:
            continue
        if len(entries) > MAX_DIRECTORY_ENTRIES:
            diagnostics.append(_limit("an MCP search directory exceeded its entry limit"))
            continue
        for entry in sorted(entries, key=lambda item: item.name, reverse=True):
            if entry.name in EXCLUDED_NAMES or _directory_mode(entry) is None:
                continue
            stack.append((entry, depth + 1))
    grouped: dict[Path, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.root, []).append(candidate)
    unique = {
        root: Candidate(
            root=root,
            entry_points=tuple(
                sorted({value for candidate in held for value in candidate.entry_points})
            ),
            transports=tuple(
                sorted({value for candidate in held for value in candidate.transports})
            ),
            evidence=tuple(sorted({value for candidate in held for value in candidate.evidence})),
        )
        for root, held in grouped.items()
    }
    return Report(
        tuple(unique[root] for root in sorted(unique, key=lambda item: item.as_posix())),
        tuple(diagnostics),
    )


def _python_candidate(root: Path, diagnostics: list[Diagnostic]) -> Candidate | None:
    manifest = root / "pyproject.toml"
    payload = _bounded(manifest, diagnostics, "python-mcp-package")
    if payload is None:
        return None
    try:
        document = cast(dict[str, object], tomllib.loads(payload.decode("utf-8")))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        diagnostics.append(_invalid("python-mcp-package"))
        return None
    project_value = document.get("project")
    if not isinstance(project_value, dict):
        return None
    project = cast(dict[str, object], project_value)
    dependencies_value = project.get("dependencies", [])
    if not isinstance(dependencies_value, list):
        return None
    dependencies = cast(list[object], dependencies_value)
    if not _has_python_sdk(dependencies):
        return None
    scripts_value = project.get("scripts", {})
    if not isinstance(scripts_value, dict):
        return None
    scripts = cast(dict[str, object], scripts_value)
    verified: list[tuple[str, Path, tuple[str, ...]]] = []
    for target in scripts.values():
        if not isinstance(target, str):
            continue
        module = target.split(":", 1)[0].strip()
        source = _python_module(root, module)
        if source is None:
            continue
        transports = _python_server(source, diagnostics)
        if transports is not None:
            verified.append((target, source, transports))
    return _candidate(root, manifest, verified) if verified else None


def _node_candidate(root: Path, diagnostics: list[Diagnostic]) -> Candidate | None:
    manifest = root / "package.json"
    payload = _bounded(manifest, diagnostics, "typescript-mcp-package")
    if payload is None:
        return None
    try:
        parsed = cast(object, json.loads(payload))
    except (UnicodeDecodeError, json.JSONDecodeError):
        diagnostics.append(_invalid("typescript-mcp-package"))
        return None
    if not isinstance(parsed, dict):
        return None
    document = cast(dict[str, object], parsed)
    if not _has_node_sdk(document):
        return None
    declared: list[str] = []
    binary = document.get("bin")
    if isinstance(binary, str):
        declared.append(binary)
    elif isinstance(binary, dict):
        held_binary = cast(dict[str, object], binary)
        declared.extend(value for value in held_binary.values() if isinstance(value, str))
    scripts = document.get("scripts")
    if isinstance(scripts, dict):
        held_scripts = cast(dict[str, object], scripts)
        for command in held_scripts.values():
            if not isinstance(command, str):
                continue
            match = _PATH_TOKEN.search(f" {command} ")
            if match is not None:
                declared.append(match.group(1))
    verified: list[tuple[str, Path, tuple[str, ...]]] = []
    for target in sorted(set(declared)):
        source = _safe_child(root, target)
        if source is None:
            continue
        transports = _typescript_server(source, diagnostics)
        if transports is not None:
            verified.append((target, source, transports))
    return _candidate(root, manifest, verified) if verified else None


def _candidate(
    root: Path,
    manifest: Path,
    verified: list[tuple[str, Path, tuple[str, ...]]],
) -> Candidate:
    entry_points = tuple(sorted({entry for entry, _source, _transports in verified}))
    transports = tuple(
        sorted({transport for _entry, _source, held in verified for transport in held})
    )
    evidence = {manifest.relative_to(root).as_posix()}
    evidence.update(source.relative_to(root).as_posix() for _entry, source, _held in verified)
    evidence.update(_launchers(root, entry_points))
    return Candidate(root, entry_points, transports, tuple(sorted(evidence)))


def _has_python_sdk(dependencies: list[object]) -> bool:
    for dependency in dependencies:
        if not isinstance(dependency, str):
            continue
        name = re.split(r"[<>=!~\[; ]", dependency.strip().lower(), maxsplit=1)[0]
        if name in _PYTHON_DEPENDENCIES:
            return True
    return False


def _has_node_sdk(document: dict[str, object]) -> bool:
    names: set[str] = set()
    for field in ("dependencies", "optionalDependencies", "peerDependencies"):
        dependencies = document.get(field)
        if isinstance(dependencies, dict):
            held = cast(dict[str, object], dependencies)
            names.update(name.lower() for name in held)
    return bool(names & _TYPESCRIPT_DEPENDENCIES)


def _python_module(root: Path, module: str) -> Path | None:
    if not module or any(part in {"", ".", ".."} for part in module.split(".")):
        return None
    relative = Path(*module.split(".")).with_suffix(".py")
    for base in (root, root / "src"):
        candidate = _safe_child(base, relative.as_posix())
        if candidate is not None:
            return candidate
    return None


def _python_server(source: Path, diagnostics: list[Diagnostic]) -> tuple[str, ...] | None:
    payload = _bounded(source, diagnostics, "python-mcp-entry-point", MAX_SOURCE_BYTES)
    if payload is None:
        return None
    try:
        tree = ast.parse(payload)
    except (SyntaxError, UnicodeDecodeError):
        diagnostics.append(_invalid("python-mcp-entry-point"))
        return None
    imports: set[str] = set()
    names: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if (
                    keyword.arg == "transport"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    strings.add(keyword.value.value.lower().replace("_", "-"))
    if not any(name == "mcp" or name.startswith("mcp.") or name == "fastmcp" for name in imports):
        return None
    return _transports(names, strings)


def _typescript_server(source: Path, diagnostics: list[Diagnostic]) -> tuple[str, ...] | None:
    payload = _bounded(source, diagnostics, "typescript-mcp-entry-point", MAX_SOURCE_BYTES)
    if payload is None:
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        diagnostics.append(_invalid("typescript-mcp-entry-point"))
        return None
    if "@modelcontextprotocol/sdk" not in text and "fastmcp" not in text.lower():
        return None
    names = set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]+\b", text))
    strings = {
        item.lower().replace("_", "-")
        for item in re.findall(r"\btransport\s*[:=]\s*['\"]([^'\"]+)['\"]", text)
    }
    return _transports(names, strings)


def _transports(names: set[str], strings: set[str]) -> tuple[str, ...]:
    found: set[str] = set()
    if "StdioServerTransport" in names or "stdio" in strings:
        found.add("stdio")
    if {"StreamableHTTPServerTransport", "SSEServerTransport"} & names or {
        "http",
        "sse",
        "streamable-http",
    } & strings:
        found.add("http")
    return tuple(sorted(found))


def _launchers(root: Path, entry_points: tuple[str, ...]) -> set[str]:
    places = [root / "Dockerfile", root / "docker-compose.yml", root / "docker-compose.yaml"]
    places.extend(sorted((root / "deploy").glob("*.service")))
    places.extend(sorted((root / "deploy" / "mcp").glob("*.service")))
    needles = {value.split(":", 1)[0] for value in entry_points}
    needles.update(Path(value).name for value in entry_points)
    evidence: set[str] = set()
    for place in places:
        payload = _bounded(place, [], "mcp-launcher")
        if payload is None:
            continue
        text = payload.decode("utf-8", errors="ignore")
        if any(needle and needle in text for needle in needles):
            evidence.add(place.relative_to(root).as_posix())
    return evidence


def _safe_child(root: Path, raw: str) -> Path | None:
    relative = Path(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    candidate = root / relative
    try:
        held = candidate.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(held.st_mode) or not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
        return None
    return candidate


def _bounded(
    place: Path,
    diagnostics: list[Diagnostic],
    source: str,
    limit: int | None = None,
) -> bytes | None:
    held_limit = MAX_MANIFEST_BYTES if limit is None else limit
    try:
        held = place.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(held.st_mode) or not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
        return None
    if held.st_size > held_limit:
        diagnostics.append(_limit(f"{source} exceeded its byte limit", source))
        return None
    descriptor = os.open(
        place,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (held.st_dev, held.st_ino):
            return None
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(held_limit + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > held_limit:
        diagnostics.append(_limit(f"{source} exceeded its byte limit", source))
        return None
    return payload


def _directory_mode(place: Path) -> int | None:
    try:
        mode = place.lstat().st_mode
    except OSError:
        return None
    return mode if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode) else None


def _limit(reason: str, source: str = "mcp-package-search") -> Diagnostic:
    return Diagnostic(code="bounded_limit", source=source, reason=reason)


def _invalid(source: str) -> Diagnostic:
    return Diagnostic(
        code="invalid_manifest", source=source, reason="bounded MCP metadata is invalid"
    )
