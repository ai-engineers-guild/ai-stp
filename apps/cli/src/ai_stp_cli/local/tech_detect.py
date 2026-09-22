"""Local technology detection over one project index (issue #222).

The detector is a pure function of the bounded index `project_index.build`
already produced: it walks nothing itself, reads only the files the index
described, and re-verifies each digest before parsing so a file that changed
between indexing and reading contributes nothing to this scan.

Two separations make the result honest rather than convenient. A *detection*
is a coordinate in an ecosystem's own vocabulary — `package:django`,
`image:postgres`, `configuration:manage.py` — with the evidence that named it.
A *technology* is a canonical identity, and the detector does not mint those:
a versioned mapping snapshot resolves coordinates to identifiers, and a
coordinate the mapping does not cover stays unmapped rather than borrowing an
identity it cannot prove.

`context` answers "where is this used" — production dependencies, development
tooling, test-only tooling — because the answer changes what an installation
should carry. `version_kind` keeps `>=3.11` (a declared range) and `3.11.4`
read from a lock file (an observed version) from ever being spelled the same.
"""

import hashlib
import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal, cast

import yaml

from ai_stp_cli.local import project_index, projects

#: Bumped when the rule set changes in a way that makes two scans incomparable.
#: Evidence carries it, so a finding always says which detector saw it.
DETECTOR_VERSION: Final[str] = "1"

#: The version of the bundled coordinate→identity table. Organization snapshots
#: fetched from the platform carry their own version; this one ships with the
#: CLI and resolves only identities the canonical seed already owns.
BUNDLED_MAPPING_VERSION: Final[str] = "bundled.1"

#: A dependency line longer than this is pathological, not a requirement.
MAX_LINE_CHARS: Final[int] = 512

EvidenceSource = Literal["declared", "configured", "observed"]
DetectionKind = Literal["package", "image", "executable", "configuration", "alias"]
UsageContext = Literal["production", "development", "testing", "browser_support"]
VersionKind = Literal["unknown", "declared_range", "observed_version"]


@dataclass(frozen=True)
class Trace:
    """One piece of evidence for one detection: where it was seen and how."""

    source: EvidenceSource
    path: str
    reference: str | None
    confidence: float


@dataclass(frozen=True)
class Detection:
    """One coordinate observed in the project, with everything that saw it."""

    kind: DetectionKind
    coordinate: str
    context: UsageContext
    version: str | None
    version_kind: VersionKind
    traces: tuple[Trace, ...]

    @property
    def finding_key(self) -> str:
        """The stable identity review decisions attach to.

        Version is deliberately absent: `package:django` at `>=5` and at `5.2.1`
        is the same finding with two claims, and a confirm or reject must still
        apply after a rescan moves the version. Reviews name this key.
        """
        return f"{self.kind}:{self.coordinate}:{self.context}"


@dataclass(frozen=True)
class DetectedScan:
    """What one detection pass found, and whether it saw the whole project."""

    complete: bool
    stopped_by: str | None
    detections: tuple[Detection, ...]


class _Reader:
    """Reads the exact file the index described, or refuses.

    The index hashed the content it inventoried. Re-checking that digest here
    is the difference between reading what the index saw and reading whatever
    happens to sit at that path now — a file rewritten between the two passes
    would otherwise produce evidence for content nobody indexed.
    """

    def __init__(self, index: project_index.Index):
        self._root = index.root

    def text(self, entry: project_index.Entry) -> str | None:
        place = self._root / entry.path
        try:
            if not projects.contains(self._root, place):
                return None
            content = place.read_bytes()
        except OSError:
            return None
        if (
            entry.digest is not None
            and f"sha256:{hashlib.sha256(content).hexdigest()}" != entry.digest
        ):
            return None
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return None


@dataclass
class _Builder:
    """Accumulates detections keyed by their full identity."""

    found: dict[tuple[str, str, str, str | None, str], list[Trace]]

    def add(
        self,
        kind: DetectionKind,
        coordinate: str,
        context: UsageContext,
        *,
        version: str | None = None,
        version_kind: VersionKind = "unknown",
        source: EvidenceSource,
        path: str,
        reference: str | None = None,
        confidence: float = 0.9,
    ) -> None:
        coordinate = coordinate.strip()
        if not coordinate or not _COORDINATE.match(coordinate):
            return
        if version is not None:
            version = version.strip() or None
        if version is None:
            version_kind = "unknown"
        key = (
            kind,
            coordinate,
            context,
            version if version_kind != "unknown" else None,
            version_kind,
        )
        trace = Trace(source, path, _safe_reference(reference), confidence)
        existing = self.found.setdefault(key, [])
        if trace not in existing:
            existing.append(trace)

    def detections(self) -> tuple[Detection, ...]:
        items = [
            Detection(
                kind=cast(DetectionKind, kind),
                coordinate=coordinate,
                context=cast(UsageContext, context),
                version=version,
                version_kind=cast(VersionKind, version_kind),
                traces=tuple(sorted(traces, key=lambda item: (item.path, item.reference or ""))),
            )
            for (kind, coordinate, context, version, version_kind), traces in self.found.items()
        ]
        return tuple(
            sorted(
                items,
                key=lambda item: (item.kind, item.coordinate, item.context, item.version or ""),
            )
        )


#: The mapping-entry coordinate pattern from the wire contract: a detection that
#: cannot be spelled in it can never resolve, so it is refused at creation.
_COORDINATE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._:/@+*-]{1,512}$")

#: The wire pattern for `TechnologyEvidence.reference`. A reference that cannot
#: travel is dropped rather than escaping into evidence that fails validation.
_REFERENCE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._:/+-]{1,256}$")


def _safe_reference(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()[:256]
    return trimmed if trimmed and _REFERENCE.match(trimmed) else None


def _table(value: object) -> dict[str, object]:
    """A parsed manifest section as a typed table, or empty when it is not a mapping.

    `isinstance(x, dict)` alone narrows to `dict[Unknown, Unknown]`; callers
    need `.get`/`.items` that return `object`, not Unknown.
    """
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _seq(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


#: Basenames that always name the same file regardless of directory.
_FROM_LINE: Final[re.Pattern[str]] = re.compile(r"^\s*FROM\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_REQUIREMENT: Final[re.Pattern[str]] = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[.*?\])?\s*([<>=!~^].*)?$"
)
_GO_MODULE: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z0-9._~:/?#@+-]+)\s+v([^\s]+)")

#: How many paths one detection cites for a presence-based signature. A
#: monorepo may hold thousands of `.py` files; the signature says the language
#: exists, and eight cited paths prove it without a payload that scales with
#: repository size.
MAX_TRACE_PATHS: Final[int] = 8


def _image_name(reference: str) -> tuple[str, str | None]:
    """Split `postgres:16-alpine` into (`postgres`, `16-alpine`), keeping digests out."""
    cleaned = reference.strip().strip("\"'")
    if "@" in cleaned:
        cleaned, _sep, _digest = cleaned.partition("@")
    name, sep, tag = cleaned.rpartition(":")
    if sep and "/" not in tag:
        return name, tag
    return cleaned, None


def _requirement_name(line: str) -> tuple[str, str | None] | None:
    """One `requirements.txt`-style line → (name, range) or nothing."""
    stripped = line.split("#", 1)[0].strip().split(";", 1)[0].strip()
    if not stripped or stripped.startswith(("-", ".", "/")) or "://" in stripped:
        return None
    if len(stripped) > MAX_LINE_CHARS:
        return None
    matched = _REQUIREMENT.match(stripped)
    if matched is None:
        return None
    name, specifier = matched.group(1), matched.group(2)
    return name.lower(), specifier.strip() if specifier else None


def _dependency(
    builder: _Builder,
    name: str,
    specifier: str | None,
    *,
    context: UsageContext,
    source: EvidenceSource,
    path: str,
    reference: str,
    version_kind: VersionKind = "declared_range",
) -> None:
    builder.add(
        "package",
        name,
        context,
        version=specifier,
        version_kind=version_kind,
        source=source,
        path=path,
        reference=reference,
        confidence=1.0,
    )


# --------------------------------------------------------------------------
# Manifest extractors — one per ecosystem the index can classify.
# --------------------------------------------------------------------------


def _pyproject(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        return
    project = _table(document.get("project"))
    if project:
        requires = _text(project.get("requires-python"))
        if requires is not None:
            builder.add(
                "alias",
                "python",
                "production",
                version=requires,
                version_kind="declared_range",
                source="declared",
                path=path,
                reference="project.requires-python",
                confidence=1.0,
            )
        for parsed in _requirements_list(project.get("dependencies")):
            _dependency(
                builder,
                parsed[0],
                parsed[1],
                context="production",
                source="declared",
                path=path,
                reference="project.dependencies",
            )
        for group, values in _table(project.get("optional-dependencies")).items():
            group_context: UsageContext = (
                "testing" if group.lower() in {"test", "tests", "testing"} else "development"
            )
            for parsed in _requirements_list(values):
                _dependency(
                    builder,
                    parsed[0],
                    parsed[1],
                    context=group_context,
                    source="declared",
                    path=path,
                    reference=f"project.optional-dependencies.{group}",
                )
    poetry = _table(_table(document.get("tool")).get("poetry"))
    sections: tuple[tuple[str, UsageContext], ...] = (
        ("dependencies", "production"),
        ("dev-dependencies", "development"),
    )
    for section, context in sections:
        for name, spec in _table(poetry.get(section)).items():
            if name.lower() == "python" and section == "dependencies":
                builder.add(
                    "alias",
                    "python",
                    "production",
                    version=_poetry_spec(spec),
                    version_kind="declared_range",
                    source="declared",
                    path=path,
                    reference="tool.poetry.dependencies.python",
                    confidence=1.0,
                )
                continue
            _dependency(
                builder,
                name,
                _poetry_spec(spec),
                context=context,
                source="declared",
                path=path,
                reference=f"tool.poetry.{section}",
            )
    for group_values in _table(poetry.get("group")).values():
        for name, spec in _table(_table(group_values).get("dependencies")).items():
            _dependency(
                builder,
                name,
                _poetry_spec(spec),
                context="development",
                source="declared",
                path=path,
                reference="tool.poetry.group",
            )


def _requirements_list(entries: object) -> list[tuple[str, str | None]]:
    """(name, declared range) pairs out of a PEP 508 dependency list."""
    found: list[tuple[str, str | None]] = []
    for entry in _seq(entries):
        if not isinstance(entry, str):
            continue
        parsed = _requirement_name(entry)
        if parsed is not None:
            found.append(parsed)
    return found


def _poetry_spec(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    table = _table(value)
    if table:
        return _text(table.get("version"))
    items = _seq(value)
    if items:
        return _text(_table(items[0]).get("version"))
    return None


def _requirements(text: str, builder: _Builder, path: str, context: UsageContext) -> None:
    for line in text.splitlines():
        parsed = _requirement_name(line)
        if parsed is None:
            continue
        name, specifier = parsed
        version = specifier
        # `==8.2` is a declared pin, not an observed version: a requirements
        # file states intent; only a lock records what resolution produced.
        if specifier is not None and specifier.startswith("=="):
            version = specifier.removeprefix("==").strip()
        _dependency(
            builder,
            name,
            version,
            context=context,
            source="declared",
            path=path,
            reference=name,
            version_kind="declared_range",
        )


def _package_json(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(json.loads(text))
    except json.JSONDecodeError:
        return
    sections: tuple[tuple[str, UsageContext], ...] = (
        ("dependencies", "production"),
        ("devDependencies", "development"),
        ("peerDependencies", "production"),
        ("optionalDependencies", "production"),
    )
    for section, context in sections:
        for name, spec in _table(document.get(section)).items():
            _dependency(
                builder,
                name,
                _text(spec),
                context=context,
                source="declared",
                path=path,
                reference=section,
            )
    for name, spec in _table(document.get("engines")).items():
        builder.add(
            "alias",
            name.lower(),
            "production",
            version=_text(spec),
            version_kind="declared_range",
            source="declared",
            path=path,
            reference="engines",
            confidence=1.0,
        )
    manager = _text(document.get("packageManager"))
    if manager is not None and "@" in manager:
        tool, _sep, version = manager.partition("@")
        builder.add(
            "alias",
            tool.strip().lower(),
            "development",
            version=version.strip() or None,
            version_kind="declared_range",
            source="declared",
            path=path,
            reference="packageManager",
            confidence=1.0,
        )


def _cargo_toml(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        return
    sections: tuple[tuple[str, UsageContext], ...] = (
        ("dependencies", "production"),
        ("dev-dependencies", "testing"),
        ("build-dependencies", "development"),
    )
    for section, context in sections:
        for name, spec in _table(document.get(section)).items():
            _dependency(
                builder,
                name,
                _poetry_spec(spec),
                context=context,
                source="declared",
                path=path,
                reference=section,
            )
    package = _table(document.get("package"))
    edition = _text(package.get("rust-version")) or _text(package.get("edition"))
    if edition is not None:
        builder.add(
            "alias",
            "rust",
            "production",
            version=edition,
            version_kind="declared_range",
            source="declared",
            path=path,
            reference="package.rust-version",
            confidence=1.0,
        )


def _go_mod(text: str, builder: _Builder, path: str) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("go "):
            builder.add(
                "alias",
                "go",
                "production",
                version=stripped.removeprefix("go").strip() or None,
                version_kind="declared_range",
                source="declared",
                path=path,
                reference="go",
                confidence=1.0,
            )
            continue
        for keyword in ("require ", "replace "):
            if stripped.startswith(keyword):
                stripped = stripped.removeprefix(keyword)
        matched = _GO_MODULE.match(stripped)
        if matched is not None and matched.group(1) not in {"(", "module"}:
            _dependency(
                builder,
                matched.group(1),
                matched.group(2),
                context="production",
                source="declared",
                path=path,
                reference="require",
                version_kind="declared_range",
            )


def _pubspec(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(yaml.safe_load(text))
    except yaml.YAMLError:
        return
    sections: tuple[tuple[str, UsageContext], ...] = (
        ("dependencies", "production"),
        ("dev_dependencies", "testing"),
    )
    for section, context in sections:
        for name in _table(document.get(section)):
            _dependency(
                builder,
                name,
                None,
                context=context,
                source="declared",
                path=path,
                reference=section,
            )
    sdk = _text(_table(document.get("environment")).get("sdk"))
    if sdk is not None:
        builder.add(
            "alias",
            "dart",
            "production",
            version=sdk,
            version_kind="declared_range",
            source="declared",
            path=path,
            reference="environment.sdk",
            confidence=1.0,
        )


def _setup_cfg(text: str, builder: _Builder, path: str) -> None:
    """`install_requires` lines inside `[options]` — continuation lines are indented."""
    in_requires = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_requires = False
            continue
        if line[:1] in {" ", "\t"} and in_requires:
            parsed = _requirement_name(stripped)
            if parsed is not None:
                _dependency(
                    builder,
                    parsed[0],
                    parsed[1],
                    context="production",
                    source="declared",
                    path=path,
                    reference="install_requires",
                )
            continue
        in_requires = stripped.startswith("install_requires")


def _pipfile(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        return
    sections: tuple[tuple[str, UsageContext], ...] = (
        ("packages", "production"),
        ("dev-packages", "development"),
    )
    for section, context in sections:
        for name, spec in _table(document.get(section)).items():
            _dependency(
                builder,
                name,
                _poetry_spec(spec),
                context=context,
                source="declared",
                path=path,
                reference=section,
            )


def _environment_yml(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(yaml.safe_load(text))
    except yaml.YAMLError:
        return
    for entry in _seq(document.get("dependencies")):
        if isinstance(entry, str):
            name, _sep, pinned = entry.partition("=")
            # Conda spells `pkg=1.2=build`; the build suffix is not the version.
            version = pinned.split("=")[0].strip() if pinned else None
            _dependency(
                builder,
                name.strip().lower(),
                version or None,
                context="production",
                source="declared",
                path=path,
                reference="dependencies",
            )
            continue
        for item in _seq(_table(entry).get("pip")):
            parsed = _requirement_name(str(item))
            if parsed is not None:
                _dependency(
                    builder,
                    parsed[0],
                    parsed[1],
                    context="production",
                    source="declared",
                    path=path,
                    reference="dependencies.pip",
                )


def _dockerfile(text: str, builder: _Builder, path: str) -> None:
    for matched in _FROM_LINE.finditer(text):
        # `FROM --platform=linux/amd64 image AS base`: flags and the stage alias
        # are not the image.
        tokens = [token for token in matched.group(1).split() if not token.startswith("--")]
        image_token = tokens[0].split(" ", 1)[0] if tokens else ""
        if " AS " in matched.group(1).upper():
            image_token = tokens[0] if tokens else ""
        image, tag = _image_name(image_token)
        if not image or image.lower() == "scratch":
            continue
        builder.add(
            "image",
            image,
            "production",
            version=tag,
            version_kind="declared_range" if tag else "unknown",
            source="configured",
            path=path,
            reference=f"FROM:{image_token}",
            confidence=0.95,
        )


def _compose(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(yaml.safe_load(text))
    except yaml.YAMLError:
        return
    for service, body in _table(document.get("services")).items():
        image = _text(_table(body).get("image"))
        if image is None:
            continue
        name, tag = _image_name(image)
        builder.add(
            "image",
            name,
            "production",
            version=tag,
            version_kind="declared_range" if tag else "unknown",
            source="configured",
            path=path,
            reference=f"services.{service}.image",
            confidence=0.95,
        )


def _gitlab_ci(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(yaml.safe_load(text))
    except yaml.YAMLError:
        return
    images: list[str] = []

    def collect(container: dict[str, object]) -> None:
        image = _text(container.get("image")) or _text(_table(container.get("image")).get("name"))
        if image is not None:
            images.append(image)
        for service in _seq(container.get("services")):
            service_image = _text(service) or _text(_table(service).get("name"))
            if service_image is not None:
                images.append(service_image)

    collect(document)
    for value in document.values():
        collect(_table(value))
    for reference in sorted({item for item in images if item}):
        name, tag = _image_name(reference)
        builder.add(
            "image",
            name,
            "testing",
            version=tag,
            version_kind="declared_range" if tag else "unknown",
            source="configured",
            path=path,
            reference=f"image:{reference}",
            confidence=0.9,
        )


def _lock_packages(text: str, builder: _Builder, path: str, flavor: str) -> None:
    """Installed packages out of a lock file — observed, not merely declared."""
    if flavor in {"toml-uv", "toml-poetry", "toml-cargo"}:
        try:
            document = _table(tomllib.loads(text))
        except tomllib.TOMLDecodeError:
            return
        for entry in _seq(document.get("package")):
            body = _table(entry)
            name, version = _text(body.get("name")), _text(body.get("version"))
            if name is not None:
                builder.add(
                    "package",
                    name.lower(),
                    "production",
                    version=version,
                    version_kind="observed_version" if version else "unknown",
                    source="observed",
                    path=path,
                    reference=name,
                    confidence=1.0,
                )
    elif flavor == "npm":
        try:
            document = _table(json.loads(text))
        except json.JSONDecodeError:
            return
        for place, body in _table(document.get("packages")).items():
            if "node_modules/" not in place:
                continue
            name = place.rsplit("node_modules/", 1)[-1]
            version = _text(_table(body).get("version"))
            if name:
                builder.add(
                    "package",
                    name,
                    "production",
                    version=version,
                    version_kind="observed_version" if version else "unknown",
                    source="observed",
                    path=path,
                    reference=name,
                    confidence=1.0,
                )
    elif flavor == "pubspec":
        try:
            document = _table(yaml.safe_load(text))
        except yaml.YAMLError:
            return
        for name, body in _table(document.get("packages")).items():
            version = _text(_table(body).get("version"))
            builder.add(
                "package",
                name,
                "production",
                version=version,
                version_kind="observed_version" if version else "unknown",
                source="observed",
                path=path,
                reference=name,
                confidence=1.0,
            )
    elif flavor == "go-sum":
        seen: set[str] = set()
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] not in seen:
                seen.add(parts[0])
                _module, _sep, version = parts[1].rpartition("/go.mod")
                builder.add(
                    "package",
                    parts[0],
                    "production",
                    version=version or parts[1],
                    version_kind="observed_version",
                    source="observed",
                    path=path,
                    reference=parts[0],
                    confidence=1.0,
                )
    elif flavor in {"pnpm", "yarn"}:
        for name in _yaml_lock_names(text, flavor):
            builder.add(
                "package",
                name,
                "production",
                source="observed",
                path=path,
                reference=name,
                confidence=1.0,
            )


def _yaml_lock_names(text: str, flavor: str) -> set[str]:
    """Package names out of pnpm/yarn locks without a full resolver."""
    found: set[str] = set()
    if flavor == "pnpm":
        try:
            document = _table(yaml.safe_load(text))
        except yaml.YAMLError:
            return found
        for section in ("packages", "snapshots"):
            for key in _table(document.get(section)):
                name = key.split("@", 1)[0].lstrip("/")
                if name:
                    found.add(name)
    else:
        for matched in re.finditer(r"^\"?((?:@[\w.-]+/)?[\w.-]+)@", text, re.MULTILINE):
            found.add(matched.group(1))
    return found


# --------------------------------------------------------------------------
# Name/shape signatures — presence alone is the evidence.
# --------------------------------------------------------------------------


#: Exact basenames → the configuration signature they carry. A rename of the
#: file is a rename of the signature: `angular.json` means Angular because the
#: ecosystem says it does, and that is a fact, not a heuristic.
_CONFIG_FILES: Final[dict[str, tuple[str, UsageContext, float]]] = {
    "angular.json": ("angular.json", "production", 0.95),
    "next.config.js": ("next.config.js", "production", 0.9),
    "next.config.mjs": ("next.config.mjs", "production", 0.9),
    "next.config.ts": ("next.config.ts", "production", 0.9),
    "nuxt.config.ts": ("nuxt.config.ts", "production", 0.9),
    "nuxt.config.js": ("nuxt.config.js", "production", 0.9),
    "vite.config.ts": ("vite.config.ts", "development", 0.85),
    "vite.config.js": ("vite.config.js", "development", 0.85),
    "svelte.config.js": ("svelte.config.js", "production", 0.9),
    "astro.config.mjs": ("astro.config.mjs", "production", 0.9),
    "gatsby-config.js": ("gatsby-config.js", "production", 0.9),
    "remix.config.js": ("remix.config.js", "production", 0.9),
    "manage.py": ("manage.py", "production", 0.9),
    "alembic.ini": ("alembic.ini", "production", 0.85),
    "pyrightconfig.json": ("pyrightconfig.json", "development", 0.85),
    "ruff.toml": ("ruff.toml", "development", 0.85),
    ".ruff.toml": (".ruff.toml", "development", 0.85),
    "mypy.ini": ("mypy.ini", "testing", 0.85),
    "pytest.ini": ("pytest.ini", "testing", 0.9),
    "conftest.py": ("conftest.py", "testing", 0.85),
    "tox.ini": ("tox.ini", "testing", 0.9),
    "noxfile.py": ("noxfile.py", "testing", 0.85),
    ".pre-commit-config.yaml": (".pre-commit-config.yaml", "development", 0.9),
    "jest.config.js": ("jest.config.js", "testing", 0.9),
    "jest.config.ts": ("jest.config.ts", "testing", 0.9),
    "vitest.config.ts": ("vitest.config.ts", "testing", 0.9),
    "vitest.config.js": ("vitest.config.js", "testing", 0.9),
    "playwright.config.ts": ("playwright.config.ts", "testing", 0.9),
    "playwright.config.js": ("playwright.config.js", "testing", 0.9),
    "cypress.config.ts": ("cypress.config.ts", "testing", 0.9),
    "cypress.config.js": ("cypress.config.js", "testing", 0.9),
    "eslint.config.js": ("eslint.config.js", "development", 0.85),
    "eslint.config.mjs": ("eslint.config.mjs", "development", 0.85),
    ".eslintrc.json": (".eslintrc.json", "development", 0.85),
    ".eslintrc.js": (".eslintrc.js", "development", 0.85),
    "biome.json": ("biome.json", "development", 0.85),
    ".prettierrc": (".prettierrc", "development", 0.85),
    ".prettierrc.json": (".prettierrc.json", "development", 0.85),
    "pom.xml": ("pom.xml", "production", 0.9),
    "build.gradle": ("build.gradle", "production", 0.9),
    "build.gradle.kts": ("build.gradle.kts", "production", 0.9),
    "composer.json": ("composer.json", "production", 0.9),
    "Gemfile": ("Gemfile", "production", 0.9),
    "mix.exs": ("mix.exs", "production", 0.9),
    "deno.json": ("deno.json", "production", 0.9),
    "deno.jsonc": ("deno.jsonc", "production", 0.9),
    "bun.lock": ("bun.lock", "production", 0.9),
    "bun.lockb": ("bun.lockb", "production", 0.9),
    "Chart.yaml": ("Chart.yaml", "production", 0.9),
    "kustomization.yaml": ("kustomization.yaml", "production", 0.9),
    "kustomization.yml": ("kustomization.yml", "production", 0.9),
    "helmfile.yaml": ("helmfile.yaml", "production", 0.9),
    "skaffold.yaml": ("skaffold.yaml", "production", 0.9),
    "ansible.cfg": ("ansible.cfg", "production", 0.85),
    "Vagrantfile": ("Vagrantfile", "development", 0.85),
    "Pulumi.yaml": ("Pulumi.yaml", "production", 0.9),
    "serverless.yml": ("serverless.yml", "production", 0.9),
    "serverless.yaml": ("serverless.yaml", "production", 0.9),
    "cdk.json": ("cdk.json", "production", 0.9),
    "firebase.json": ("firebase.json", "production", 0.9),
    "vercel.json": ("vercel.json", "production", 0.9),
    "netlify.toml": ("netlify.toml", "production", 0.9),
    "fly.toml": ("fly.toml", "production", 0.9),
    "render.yaml": ("render.yaml", "production", 0.9),
    "wrangler.toml": ("wrangler.toml", "production", 0.9),
    "railway.toml": ("railway.toml", "production", 0.9),
    "railway.json": ("railway.json", "production", 0.9),
    "nginx.conf": ("nginx.conf", "production", 0.85),
    "Caddyfile": ("Caddyfile", "production", 0.85),
    "redis.conf": ("redis.conf", "production", 0.9),
    "postgresql.conf": ("postgresql.conf", "production", 0.9),
    "pg_hba.conf": ("pg_hba.conf", "production", 0.9),
    "schema.prisma": ("schema.prisma", "production", 0.9),
    "drizzle.config.ts": ("drizzle.config.ts", "production", 0.85),
    "ionic.config.json": ("ionic.config.json", "production", 0.9),
    "capacitor.config.ts": ("capacitor.config.ts", "production", 0.85),
    "capacitor.config.json": ("capacitor.config.json", "production", 0.85),
    "tauri.conf.json": ("tauri.conf.json", "production", 0.9),
    ".gitlab-ci.yml": (".gitlab-ci.yml", "testing", 0.95),
    ".gitlab-ci.yaml": (".gitlab-ci.yaml", "testing", 0.95),
    "Jenkinsfile": ("Jenkinsfile", "testing", 0.9),
    ".drone.yml": (".drone.yml", "testing", 0.85),
    "azure-pipelines.yml": ("azure-pipelines.yml", "testing", 0.9),
    "bitbucket-pipelines.yml": ("bitbucket-pipelines.yml", "testing", 0.9),
    ".travis.yml": (".travis.yml", "testing", 0.85),
    "docker-compose.yml": ("docker-compose.yml", "production", 0.9),
    "docker-compose.yaml": ("docker-compose.yaml", "production", 0.9),
    "compose.yml": ("compose.yml", "production", 0.9),
    "compose.yaml": ("compose.yaml", "production", 0.9),
    "Dockerfile": ("Dockerfile", "production", 0.9),
    "Containerfile": ("Containerfile", "production", 0.9),
    ".python-version": (".python-version", "production", 0.85),
    ".nvmrc": (".nvmrc", "production", 0.85),
    ".node-version": (".node-version", "production", 0.85),
    ".tool-versions": (".tool-versions", "production", 0.85),
    "mise.toml": ("mise.toml", "production", 0.85),
    ".mise.toml": (".mise.toml", "production", 0.85),
    "runtime.txt": ("runtime.txt", "production", 0.85),
    "Pipfile": ("Pipfile", "production", 0.9),
    "environment.yml": ("environment.yml", "production", 0.9),
    "environment.yaml": ("environment.yaml", "production", 0.9),
}

#: The ecosystem each manifest name belongs to, so its mere presence names the
#: toolchain even when parsing finds no dependencies.
_MANIFEST_ALIAS: Final[dict[str, str]] = {
    "pyproject.toml": "python",
    "setup.cfg": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "Pipfile": "pipenv",
    "environment.yml": "conda",
    "environment.yaml": "conda",
    "package.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pubspec.yaml": "dart",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "composer.json": "php",
    "Gemfile": "ruby",
    "mix.exs": "elixir",
    "deno.json": "deno",
    "deno.jsonc": "deno",
}

_LOCK_ALIAS: Final[dict[str, str]] = {
    "uv.lock": "uv",
    "poetry.lock": "poetry",
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "Cargo.lock": "cargo",
    "go.sum": "go",
    "pubspec.lock": "pubspec",
    "bun.lock": "bun",
    "bun.lockb": "bun",
    "Pipfile.lock": "pipenv",
    "composer.lock": "composer",
    "Gemfile.lock": "bundler",
}

_RUNTIME_FILES: Final[dict[str, str]] = {
    ".python-version": "python",
    ".nvmrc": "node",
    ".node-version": "node",
    "runtime.txt": "python",
    ".ruby-version": "ruby",
    ".java-version": "java",
    ".go-version": "go",
}

#: Source-file language → alias. Presence of sources is observed evidence: the
#: files exist, which is more than a manifest claiming a toolchain.
_SOURCE_ALIAS: Final[dict[str, str]] = {
    "python": "python",
    "typescript": "typescript",
    "javascript": "javascript",
    "rust": "rust",
    "go": "go",
    "dart": "dart",
}

#: Suffix rules for kinds the index classifies as plain text.
_SUFFIX_CONFIG: Final[dict[str, tuple[str, UsageContext]]] = {
    ".tf": ("tf", "production"),
    ".proto": ("proto", "production"),
}

#: Directory-prefix signatures: a file under this path names the tool.
_PREFIX_CONFIG: Final[tuple[tuple[str, str, UsageContext], ...]] = (
    (".github/workflows/", "github-workflows", "testing"),
    (".storybook/", "storybook", "development"),
    ("supabase/", "supabase", "production"),
    (".circleci/", "circleci", "testing"),
    ("k8s/", "kubernetes-manifests", "production"),
    ("deploy/kubernetes/", "kubernetes-manifests", "production"),
)


def detect(index: project_index.Index) -> DetectedScan:
    """Detect technology coordinates over one bounded index.

    Pure: same index in, same detections out. Nothing is executed, installed or
    written, and the only files read are ones the index already opened and
    hashed — re-hashed here so the evidence names exactly what was seen.
    """
    reader = _Reader(index)
    builder = _Builder(found={})
    # Presence-based signatures cite at most MAX_TRACE_PATHS paths: collecting
    # first and emitting once keeps a 4,000-file source tree from producing
    # 4,000 evidence rows that all say the same thing.
    language_paths: dict[str, list[str]] = {}
    prefix_paths: dict[tuple[str, str], list[str]] = {}
    suffix_paths: dict[tuple[str, str], list[str]] = {}

    for entry in index.entries:
        basename = entry.path.rsplit("/", 1)[-1]
        if entry.language in _SOURCE_ALIAS:
            language_paths.setdefault(entry.language, []).append(entry.path)
        signature = _CONFIG_FILES.get(basename)
        if signature is not None:
            coordinate, context, confidence = signature
            builder.add(
                "configuration",
                coordinate,
                context,
                source="configured",
                path=entry.path,
                reference=basename,
                confidence=confidence,
            )
        for prefix, coordinate, context in _PREFIX_CONFIG:
            if entry.path.startswith(prefix):
                prefix_paths.setdefault((coordinate, context), []).append(entry.path)
                break
        suffix = basename.rpartition(".")[2].lower()
        if f".{suffix}" in _SUFFIX_CONFIG and "." in basename:
            coordinate, context = _SUFFIX_CONFIG[f".{suffix}"]
            suffix_paths.setdefault((coordinate, context), []).append(entry.path)
        if basename in _MANIFEST_ALIAS:
            builder.add(
                "alias",
                _MANIFEST_ALIAS[basename],
                "production",
                source="declared",
                path=entry.path,
                reference=basename,
                confidence=0.9,
            )
        if basename in _LOCK_ALIAS:
            builder.add(
                "alias",
                _LOCK_ALIAS[basename],
                "development",
                source="observed",
                path=entry.path,
                reference=basename,
                confidence=0.95,
            )
        if basename in _RUNTIME_FILES:
            text = reader.text(entry)
            if text is not None:
                _runtime_file(basename, text, builder, entry.path)

        # Content rules, bounded by the same digest the index computed.
        _content_rules(basename, entry, reader, builder)

    for language, paths in language_paths.items():
        for path in sorted(paths)[:MAX_TRACE_PATHS]:
            builder.add(
                "alias",
                _SOURCE_ALIAS[language],
                "production",
                source="observed",
                path=path,
                reference=language,
                confidence=0.8,
            )
    for (coordinate, context), paths in prefix_paths.items():
        for path in sorted(paths)[:MAX_TRACE_PATHS]:
            builder.add(
                "configuration",
                coordinate,
                cast(UsageContext, context),
                source="configured",
                path=path,
                reference=coordinate,
                confidence=0.85,
            )
    for (coordinate, context), paths in suffix_paths.items():
        for path in sorted(paths)[:MAX_TRACE_PATHS]:
            builder.add(
                "configuration",
                coordinate,
                cast(UsageContext, context),
                source="configured",
                path=path,
                reference=coordinate,
                confidence=0.8,
            )

    return DetectedScan(
        complete=index.state == "complete",
        stopped_by=index.stopped_by,
        detections=builder.detections(),
    )


#: Basenames with a content rule below. Files outside this set — and not
#: `*.dockerfile` — never reach `reader.text`, so detection reads and
#: re-hashes only what a rule can actually parse.
_CONTENT_FILES: Final[frozenset[str]] = frozenset(
    {
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements_dev.txt",
        "requirements-test.txt",
        "requirements_test.txt",
        "test-requirements.txt",
        "package.json",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "pubspec.yaml",
        "pubspec.lock",
        "setup.cfg",
        "Pipfile",
        "environment.yml",
        "environment.yaml",
        "Dockerfile",
        "Containerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        ".gitlab-ci.yml",
        ".gitlab-ci.yaml",
        "uv.lock",
        "poetry.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        ".tool-versions",
        "mise.toml",
        ".mise.toml",
    }
)


def _content_rules(
    basename: str, entry: project_index.Entry, reader: _Reader, builder: _Builder
) -> None:
    """Per-file content rules. `entry` is a parameter here, so the lambdas
    below close over a fixed file rather than the scan's loop variable."""
    if basename not in _CONTENT_FILES and not basename.endswith(".dockerfile"):
        return
    path = entry.path
    text = reader.text(entry)
    if basename == "pyproject.toml":
        _read(text=text, apply=lambda body: _pyproject(body, builder, path))
    elif basename == "requirements.txt":
        _read(text=text, apply=lambda body: _requirements(body, builder, path, "production"))
    elif basename in {"requirements-dev.txt", "requirements_dev.txt"}:
        _read(text=text, apply=lambda body: _requirements(body, builder, path, "development"))
    elif basename in {
        "requirements-test.txt",
        "requirements_test.txt",
        "test-requirements.txt",
    }:
        _read(text=text, apply=lambda body: _requirements(body, builder, path, "testing"))
    elif basename == "package.json":
        _read(text=text, apply=lambda body: _package_json(body, builder, path))
    elif basename == "Cargo.toml":
        _read(text=text, apply=lambda body: _cargo_toml(body, builder, path))
    elif basename == "go.mod":
        _read(text=text, apply=lambda body: _go_mod(body, builder, path))
    elif basename == "pubspec.yaml":
        _read(text=text, apply=lambda body: _pubspec(body, builder, path))
    elif basename == "setup.cfg":
        _read(text=text, apply=lambda body: _setup_cfg(body, builder, path))
    elif basename == "Pipfile":
        _read(text=text, apply=lambda body: _pipfile(body, builder, path))
    elif basename in {"environment.yml", "environment.yaml"}:
        _read(text=text, apply=lambda body: _environment_yml(body, builder, path))
    elif basename in {"Dockerfile", "Containerfile"} or basename.endswith(".dockerfile"):
        _read(text=text, apply=lambda body: _dockerfile(body, builder, path))
    elif basename in {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }:
        _read(text=text, apply=lambda body: _compose(body, builder, path))
    elif basename in {".gitlab-ci.yml", ".gitlab-ci.yaml"}:
        _read(text=text, apply=lambda body: _gitlab_ci(body, builder, path))
    elif basename == "uv.lock":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "toml-uv"))
    elif basename == "poetry.lock":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "toml-poetry"))
    elif basename == "Cargo.lock":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "toml-cargo"))
    elif basename == "package-lock.json":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "npm"))
    elif basename == "pubspec.lock":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "pubspec"))
    elif basename == "go.sum":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "go-sum"))
    elif basename == "pnpm-lock.yaml":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "pnpm"))
    elif basename == "yarn.lock":
        _read(text=text, apply=lambda body: _lock_packages(body, builder, path, "yarn"))
    elif basename == ".tool-versions":
        _read(text=text, apply=lambda body: _tool_versions(body, builder, path))
    elif basename in {"mise.toml", ".mise.toml"}:
        _read(text=text, apply=lambda body: _mise_toml(body, builder, path))


def _read(*, text: str | None, apply: Callable[[str], None]) -> None:
    if text is not None:
        apply(text)


def _runtime_file(basename: str, text: str, builder: _Builder, path: str) -> None:
    tool = _RUNTIME_FILES[basename]
    version = text.strip().splitlines()[0].strip() if text.strip() else ""
    if basename == "runtime.txt" and "-" in version:
        version = version.rsplit("-", 1)[-1]
    builder.add(
        "alias",
        tool,
        "production",
        version=version or None,
        version_kind="declared_range" if version else "unknown",
        source="configured",
        path=path,
        reference=basename,
        confidence=0.9,
    )


def _tool_versions(text: str, builder: _Builder, path: str) -> None:
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        tool, _sep, version = stripped.partition(" ")
        builder.add(
            "alias",
            tool.strip().lower(),
            "production",
            version=version.strip().split()[0] if version.strip() else None,
            version_kind="declared_range",
            source="configured",
            path=path,
            reference=tool.strip(),
            confidence=0.9,
        )


def _mise_toml(text: str, builder: _Builder, path: str) -> None:
    try:
        document = _table(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        return
    for name, spec in _table(document.get("tools")).items():
        version = _text(spec)
        builder.add(
            "alias",
            name.lower(),
            "production",
            version=version,
            version_kind="declared_range" if version else "unknown",
            source="configured",
            path=path,
            reference=f"tools.{name}",
            confidence=0.9,
        )


# --------------------------------------------------------------------------
# The bundled mapping: which coordinates name a canonical identity.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MappingSnapshot:
    """One immutable coordinate→identity table, named by its version."""

    version: str
    entries: tuple[tuple[str, str, str], ...]  # (kind, coordinate, technology_id)

    def resolve(self, kind: str, coordinate: str) -> str | None:
        lowered = coordinate.lower()
        for entry_kind, entry_coordinate, technology_id in self.entries:
            if entry_kind == kind and entry_coordinate.lower() == lowered:
                return technology_id
        return None

    def technology_ids(self) -> frozenset[str]:
        return frozenset(technology_id for _kind, _coordinate, technology_id in self.entries)


def bundled_mapping() -> MappingSnapshot:
    """The table the CLI ships: seed identities only, nothing invented.

    A coordinate absent here stays unmapped locally — that is a fact to report,
    not a gap to fill with an identity nobody issued. Canonical ids for
    technologies outside the seed resolve only through an organization's own
    published snapshot.
    """
    return MappingSnapshot(
        version=BUNDLED_MAPPING_VERSION,
        entries=(
            # Canonical identities come from `technology_seed.SEED_TECHNOLOGIES`
            # (SPEC-081 REQ-8202). Nothing outside that manifest is resolved.
            ("alias", "bun", "technology_00000000000000000000000001"),
            ("package", "bun", "technology_00000000000000000000000001"),
            ("configuration", "bun.lock", "technology_00000000000000000000000001"),
            ("configuration", "bun.lockb", "technology_00000000000000000000000001"),
            ("alias", "npm", "technology_00000000000000000000000002"),
            ("package", "npm", "technology_00000000000000000000000002"),
            ("configuration", ".gitlab-ci.yml", "technology_00000000000000000000000004"),
            ("configuration", ".gitlab-ci.yaml", "technology_00000000000000000000000004"),
            ("image", "gitlab/gitlab-runner", "technology_00000000000000000000000005"),
            ("package", "react", "technology_00000000000000000000000006"),
            ("package", "react-dom", "technology_00000000000000000000000006"),
            ("image", "postgres", "technology_00000000000000000000000007"),
            ("image", "postgresql", "technology_00000000000000000000000007"),
            ("package", "psycopg", "technology_00000000000000000000000007"),
            ("package", "psycopg2", "technology_00000000000000000000000007"),
            ("package", "psycopg2-binary", "technology_00000000000000000000000007"),
            ("package", "asyncpg", "technology_00000000000000000000000007"),
            ("package", "pg", "technology_00000000000000000000000007"),
            ("package", "postgres", "technology_00000000000000000000000007"),
            ("configuration", "postgresql.conf", "technology_00000000000000000000000007"),
            ("configuration", "pg_hba.conf", "technology_00000000000000000000000007"),
        ),
    )
