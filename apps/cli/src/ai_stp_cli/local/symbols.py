"""Limited symbol adapters for five language groups (`SPEC-004` REQ-404, REQ-412).

`REQ-411` fixes the ceiling and it is low on purpose: no call graph, no vector
representations, no private symbol bodies, no global semantic graph, no data-flow
analysis. What is wanted is a table of contents — modules, public symbols, entry
points, test files and local imports — and everything here is shaped by staying
under that ceiling rather than reaching for it.

Two methods of different strength, kept apart in the answer. Python is read with
the standard library's own parser, so its result is exact. The other four are
read line by line, which is bounded and honest but cannot tell a declaration
from the same words inside a string. Reporting both as simply "symbols" would
hide the difference at the moment a caller decides how much to trust them, which
is the same reason the toolchain manifest separates a vendor-published checksum
from one we computed ourselves.

A line scan is not a parser and does not pretend to be. It reads top-level lines
only, skips what looks like a comment, and never enters a block. When the real
adapters arrive with the managed toolchain of `SPEC-014`, they replace the method
rather than the contract.
"""

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: How a result was obtained. `syntax_tree` is exact; `line_scan` is bounded and
#: approximate, and a caller that cares about the difference can see it.
METHOD_SYNTAX_TREE: Final[str] = "syntax_tree"
METHOD_LINE_SCAN: Final[str] = "line_scan"

#: Files larger than this are not read for symbols. The index already records
#: that they exist; a generated bundle is not a table of contents.
MAX_SOURCE_BYTES: Final[int] = 512 * 1024

#: How many files one survey may read. The index is already bounded; this bounds
#: the second, more expensive pass separately, because parsing costs more than
#: listing and a project can be large in files without being large on disk.
MAX_OUTLINED_FILES: Final[int] = 2000

#: Path fragments that make a file a test. Declared rather than inferred: every
#: ecosystem spells this differently, and guessing would file a helper named
#: `latest.py` under tests.
TEST_MARKERS: Final[tuple[str, ...]] = (
    "test_",
    "_test.",
    ".test.",
    ".spec.",
    "/tests/",
    "/test/",
    "/spec/",
)

#: Top-level declarations per language, as line-anchored patterns. Anchored to
#: the start of the line on purpose: a nested declaration is indented, and
#: `REQ-411` does not ask for it.
LINE_PATTERNS: Final[dict[str, tuple[tuple[str, re.Pattern[str]], ...]]] = {
    "typescript": (
        ("function", re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)")),
        ("class", re.compile(r"^export\s+(?:default\s+)?(?:abstract\s+)?class\s+(\w+)")),
        ("type", re.compile(r"^export\s+(?:type|interface|enum)\s+(\w+)")),
        ("constant", re.compile(r"^export\s+(?:const|let|var)\s+(\w+)")),
    ),
    "javascript": (
        ("function", re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)")),
        ("class", re.compile(r"^export\s+(?:default\s+)?class\s+(\w+)")),
        ("constant", re.compile(r"^export\s+(?:const|let|var)\s+(\w+)")),
    ),
    "rust": (
        ("function", re.compile(r"^pub(?:\([^)]*\))?\s+(?:async\s+)?fn\s+(\w+)")),
        ("type", re.compile(r"^pub(?:\([^)]*\))?\s+(?:struct|enum|trait|type|union)\s+(\w+)")),
        ("constant", re.compile(r"^pub(?:\([^)]*\))?\s+(?:const|static)\s+(\w+)")),
        ("module", re.compile(r"^pub(?:\([^)]*\))?\s+mod\s+(\w+)")),
    ),
    "go": (
        ("function", re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)")),
        ("type", re.compile(r"^type\s+([A-Z]\w*)")),
        ("constant", re.compile(r"^(?:const|var)\s+([A-Z]\w*)")),
    ),
    "dart": (
        ("class", re.compile(r"^(?:abstract\s+)?class\s+(\w+)")),
        ("type", re.compile(r"^(?:mixin|enum|extension|typedef)\s+(\w+)")),
        ("function", re.compile(r"^(?:[\w<>,\s\[\]?]+\s+)?(\w+)\s*\([^)]*\)\s*(?:async\s*)?\{")),
    ),
}

#: What each language calls its entry point.
ENTRY_POINTS: Final[dict[str, frozenset[str]]] = {
    "python": frozenset({"main"}),
    "typescript": frozenset({"main"}),
    "javascript": frozenset({"main"}),
    "rust": frozenset({"main"}),
    "go": frozenset({"main", "Main"}),
    "dart": frozenset({"main"}),
}

#: Line prefixes treated as comments by the scan. Not a parser: a `//` inside a
#: string is still a comment to this, which is exactly the imprecision the
#: method name warns about.
COMMENT_PREFIXES: Final[tuple[str, ...]] = ("//", "#", "/*", "*", "--")


@dataclass(frozen=True)
class Symbol:
    """One public declaration, named and located. Never its body."""

    name: str
    kind: str
    line: int


@dataclass(frozen=True)
class Outline:
    """The table of contents of one source file."""

    path: str
    language: str

    #: `available` or `not_available` (`REQ-412`): an unsupported language gets a
    #: reason, never a partial invented index.
    state: str

    #: `syntax_tree` or `line_scan`. Different strengths, named so the caller
    #: does not have to assume.
    method: str | None
    reason: str | None
    symbols: tuple[Symbol, ...]

    #: Imports of modules inside the project. An external dependency is the
    #: manifest's fact, not this one's.
    local_imports: tuple[str, ...]
    is_test: bool
    entry_point: bool


@dataclass(frozen=True)
class LanguageSummary:
    """What one language contributes to a project, in one line."""

    language: str
    state: str
    method: str | None
    reason: str | None
    files: int
    symbols: int
    tests: int
    entry_points: tuple[str, ...]


@dataclass(frozen=True)
class Survey:
    """Every language in one project, and what stopped the reading if anything."""

    state: str
    languages: tuple[LanguageSummary, ...]
    outlines: tuple[Outline, ...]
    stopped_by: str | None


def survey(root: Path, sources: Iterable[tuple[str, str]]) -> Survey:
    """Read the table of contents of a project already indexed.

    The index decides which files exist and what language they are; this reads
    only what it is handed. Two walks of the same tree would be two chances to
    disagree about it, and the disagreement would surface as a passport that
    contradicts itself.
    """
    outlines: list[Outline] = []
    stopped_by: str | None = None
    for relative, language in sources:
        if len(outlines) >= MAX_OUTLINED_FILES:
            stopped_by = "file budget"
            break
        outlines.append(outline(root / relative, relative, language))

    return Survey(
        state="partial" if stopped_by else "complete",
        languages=_summarised(outlines),
        outlines=tuple(outlines),
        stopped_by=stopped_by,
    )


def _summarised(outlines: list[Outline]) -> tuple[LanguageSummary, ...]:
    """One line per language, in a fixed order so two runs compare."""
    summaries: list[LanguageSummary] = []
    for language in sorted({item.language for item in outlines}):
        mine = [item for item in outlines if item.language == language]
        read = [item for item in mine if item.state == "available"]
        methods = {item.method for item in read if item.method}
        unread = [item for item in mine if item.state == "not_available"]
        summaries.append(
            LanguageSummary(
                language=language,
                state="available" if read else "not_available",
                # One method per language by construction; a set that somehow
                # holds two is reported as neither rather than as one of them.
                method=methods.pop() if len(methods) == 1 else None,
                reason=(read or unread)[0].reason,
                files=len(mine),
                symbols=sum(len(item.symbols) for item in read),
                tests=sum(1 for item in mine if item.is_test),
                entry_points=tuple(item.path for item in read if item.entry_point),
            )
        )
    return tuple(summaries)


def is_test_path(relative: str) -> bool:
    """Whether this path says it holds tests."""
    lowered = f"/{relative.lower()}"
    return any(marker in lowered for marker in TEST_MARKERS)


def outline(source: Path, relative: str, language: str) -> Outline:
    """Read one file's table of contents, or say honestly why it was not read."""
    if language not in ENTRY_POINTS:
        return _not_available(relative, language, "no adapter is declared for this language")
    try:
        if source.stat().st_size > MAX_SOURCE_BYTES:
            return _not_available(relative, language, "larger than the source budget")
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return _not_available(relative, language, f"cannot be read: {type(error).__name__}")

    if language == "python":
        return _python(text, relative)
    return _scanned(text, relative, language)


def _python(text: str, relative: str) -> Outline:
    """Python, read with the parser Python ships.

    Exact, and cheap for the same reason: the module is parsed once, only its
    top level is walked, and no body is entered. `REQ-411` rules out everything
    a deeper walk would be for.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return _not_available(relative, "python", f"cannot be parsed: line {error.lineno}")

    symbols: list[Symbol] = []
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            symbols.append(Symbol(node.name, "class", node.lineno))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith(
            "_"
        ):
            symbols.append(Symbol(node.name, "function", node.lineno))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append(Symbol(target.id, "constant", node.lineno))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                symbols.append(Symbol(node.target.id, "constant", node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.level:
            # A relative import is local by construction. An absolute one may or
            # may not be, and deciding needs the project layout — which belongs
            # to whoever assembles the index, not to one file's outline.
            dots = "." * node.level
            if node.module:
                # `from .deep import thing`: the module is `.deep`. Whether
                # `thing` is a submodule or a name inside it cannot be told from
                # here, so the module is the honest answer.
                imports.append(dots + node.module)
            else:
                # `from . import neighbour`: here the imported names *are* the
                # modules, and reporting the bare `.` would name the package the
                # file already belongs to and say nothing at all.
                imports.extend(dots + alias.name for alias in node.names)

    return Outline(
        path=relative,
        language="python",
        state="available",
        method=METHOD_SYNTAX_TREE,
        reason=None,
        symbols=tuple(symbols),
        local_imports=tuple(sorted(set(imports))),
        is_test=is_test_path(relative),
        entry_point=_has_entry_point(symbols, "python") or _has_main_guard(tree),
    )


def _scanned(text: str, relative: str, language: str) -> Outline:
    """The other four, read line by line.

    Bounded and approximate, and the answer says so. This cannot tell a
    declaration from the same words inside a string or a block comment, which is
    the honest cost of not depending on a language server that is not installed
    yet. When one arrives with `SPEC-014`, the method changes and the contract
    does not.
    """
    patterns = LINE_PATTERNS[language]
    symbols: list[Symbol] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line or line.startswith(" ") or line.startswith("\t"):
            # Indented means nested, and `REQ-411` does not ask for nested.
            continue
        if line.lstrip().startswith(COMMENT_PREFIXES):
            continue
        for kind, pattern in patterns:
            found = pattern.match(line)
            if found is not None:
                symbols.append(Symbol(found.group(1), kind, number))
                break

    return Outline(
        path=relative,
        language=language,
        state="available",
        method=METHOD_LINE_SCAN,
        reason="read line by line; a language server would be exact",
        symbols=tuple(symbols),
        local_imports=(),
        is_test=is_test_path(relative),
        entry_point=_has_entry_point(symbols, language),
    )


def _has_main_guard(tree: ast.Module) -> bool:
    """Whether the module body holds a real `if __name__ == "__main__":`.

    Read from the tree rather than searched for as text. A substring search
    matches the words wherever they appear — in a docstring, in a comment, or in
    the source of this very check — and the first version of this function found
    itself, which is as clear a demonstration as one could ask for that a
    grep is not a parse.
    """
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        # Either order: both `__name__ == "__main__"` and its mirror are written
        # in real code, and the comparison means the same thing both ways.
        parts = [node.test.left, *node.test.comparators]
        named = any(isinstance(part, ast.Name) and part.id == "__name__" for part in parts)
        valued = any(isinstance(part, ast.Constant) and part.value == "__main__" for part in parts)
        if named and valued:
            return True
    return False


def _has_entry_point(symbols: list[Symbol], language: str) -> bool:
    names = ENTRY_POINTS[language]
    return any(item.name in names and item.kind == "function" for item in symbols)


def _not_available(relative: str, language: str, reason: str) -> Outline:
    """`REQ-412`: a reason, never a partial invented index."""
    return Outline(
        path=relative,
        language=language,
        state="not_available",
        method=None,
        reason=reason,
        symbols=(),
        local_imports=(),
        is_test=is_test_path(relative),
        entry_point=False,
    )
