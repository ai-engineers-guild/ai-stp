"""Symbol adapters: what they find, and what they refuse to claim."""

from pathlib import Path

import pytest

from ai_stp_cli.local import symbols

PYTHON = '''
"""A module docstring mentioning __main__ and def main, neither of which count."""

CONSTANT: int = 4
lowercase = "not a constant"

from . import neighbour
from .deep import thing
import os


class Public:
    def method(self) -> None: ...


class _Private: ...


def visible() -> None: ...


async def also_visible() -> None: ...


def _hidden() -> None: ...
'''

TYPESCRIPT = """
// export function commented() {}
export function visible(a: number) {}
export default class Widget {}
export interface Shape {}
export const LIMIT = 4;
function notExported() {}
  export function indented() {}
"""

RUST = """
pub fn visible() {}
pub(crate) struct Held;
pub const LIMIT: u8 = 4;
pub mod inner;
fn private() {}
"""

GO = """
func Exported() {}
func unexported() {}
func (r *Receiver) Method() {}
type Shape struct{}
type hidden struct{}
const Limit = 4
"""

DART = """
class Widget {}
abstract class Base {}
mixin Helpful {}
void main() {
}
"""


def _write(place: Path, name: str, text: str) -> Path:
    target = place / name
    target.write_text(text, encoding="utf-8")
    return target


def test_python_is_read_with_a_real_parser_and_says_so(tmp_path: Path) -> None:
    found = symbols.outline(_write(tmp_path, "m.py", PYTHON), "m.py", "python")
    assert found.state == "available"
    assert found.method == symbols.METHOD_SYNTAX_TREE

    named = {item.name: item.kind for item in found.symbols}
    assert named == {
        "CONSTANT": "constant",
        "Public": "class",
        "visible": "function",
        "also_visible": "function",
    }
    # Underscore-prefixed names, methods inside a class and a lowercase
    # module-level assignment are all out: `REQ-411` asks for a table of
    # contents, not an inventory.
    assert "_Private" not in named
    assert "_hidden" not in named
    assert "method" not in named
    assert "lowercase" not in named


def test_only_relative_imports_are_reported_as_local(tmp_path: Path) -> None:
    found = symbols.outline(_write(tmp_path, "m.py", PYTHON), "m.py", "python")
    # `import os` is absolute, and whether an absolute import is local depends on
    # a project layout one file cannot see. Guessing would file the standard
    # library under the project's own modules.
    assert found.local_imports == (".deep", ".neighbour")


def test_a_module_that_merely_mentions_main_is_not_an_entry_point(tmp_path: Path) -> None:
    """The first version of this searched the text and found itself.

    `__main__` appears in this module's own docstring, inside a string, and in
    the source of the check that looks for it. A substring search matches all
    three; the guard is a statement in the tree or it is not there.
    """
    assert symbols.outline(_write(tmp_path, "m.py", PYTHON), "m.py", "python").entry_point is False

    quoted = 'GUARD = "if __name__ == \\"__main__\\":"\n'
    assert symbols.outline(_write(tmp_path, "q.py", quoted), "q.py", "python").entry_point is False


@pytest.mark.parametrize(
    "text",
    [
        'if __name__ == "__main__":\n    pass\n',
        # Written the other way round, which means the same thing.
        'if "__main__" == __name__:\n    pass\n',
        # Or no guard at all, just the conventional function.
        "def main() -> None: ...\n",
    ],
)
def test_a_real_entry_point_is_recognised(text: str, tmp_path: Path) -> None:
    assert symbols.outline(_write(tmp_path, "e.py", text), "e.py", "python").entry_point is True


@pytest.mark.parametrize(
    ("name", "language", "text", "expected"),
    [
        ("a.ts", "typescript", TYPESCRIPT, {"visible", "Widget", "Shape", "LIMIT"}),
        ("a.js", "javascript", TYPESCRIPT, {"visible", "Widget", "LIMIT"}),
        ("a.rs", "rust", RUST, {"visible", "Held", "LIMIT", "inner"}),
        ("a.go", "go", GO, {"Exported", "Method", "Shape", "Limit"}),
        ("a.dart", "dart", DART, {"Widget", "Base", "Helpful", "main"}),
    ],
)
def test_the_four_scanned_languages_find_top_level_public_declarations(
    name: str, language: str, text: str, expected: set[str], tmp_path: Path
) -> None:
    found = symbols.outline(_write(tmp_path, name, text), name, language)
    assert found.state == "available"
    assert {item.name for item in found.symbols} == expected

    # And the answer never claims more strength than it has. A line scan cannot
    # tell a declaration from the same words inside a string, and the caller is
    # told that rather than left to assume otherwise.
    assert found.method == symbols.METHOD_LINE_SCAN
    assert found.reason


def test_a_scan_skips_comments_and_anything_nested(tmp_path: Path) -> None:
    found = symbols.outline(_write(tmp_path, "a.ts", TYPESCRIPT), "a.ts", "typescript")
    assert "commented" not in {item.name for item in found.symbols}
    assert "indented" not in {item.name for item in found.symbols}
    assert "notExported" not in {item.name for item in found.symbols}


def test_every_symbol_carries_the_line_it_was_found_on(tmp_path: Path) -> None:
    found = symbols.outline(_write(tmp_path, "a.rs", RUST), "a.rs", "rust")
    lines = [item.line for item in found.symbols]
    assert lines == sorted(lines)
    assert all(line > 0 for line in lines)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_thing.py", True),
        ("src/thing_test.go", True),
        ("web/widget.test.ts", True),
        ("web/widget.spec.ts", True),
        ("test/helper.rs", True),
        ("src/latest.py", False),
        ("src/contest.py", False),
        ("src/protest/thing.py", False),
    ],
)
def test_a_test_file_is_recognised_by_a_declared_marker(path: str, expected: bool) -> None:
    # `latest`, `contest` and `protest` all contain `test`. Matching the bare
    # word would file three ordinary modules under tests.
    assert symbols.is_test_path(path) is expected


def test_an_unsupported_language_says_so_and_indexes_nothing(tmp_path: Path) -> None:
    # `REQ-412` exactly: a reason, not a partial invented index.
    found = symbols.outline(_write(tmp_path, "a.cob", "IDENTIFICATION DIVISION."), "a.cob", "cobol")
    assert found.state == "not_available"
    assert found.method is None
    assert found.symbols == ()
    assert "no adapter" in (found.reason or "")


def test_a_file_that_cannot_be_parsed_or_read_says_which(tmp_path: Path) -> None:
    broken = symbols.outline(_write(tmp_path, "b.py", "def ("), "b.py", "python")
    assert broken.state == "not_available"
    assert "cannot be parsed" in (broken.reason or "")

    missing = symbols.outline(tmp_path / "gone.py", "gone.py", "python")
    assert missing.state == "not_available"
    assert "cannot be read" in (missing.reason or "")

    # Bytes that are not UTF-8 are a read failure, not a parse failure: nothing
    # was ever decoded to parse.
    (tmp_path / "raw.py").write_bytes(b"\xff\xfe\x00def x")
    undecodable = symbols.outline(tmp_path / "raw.py", "raw.py", "python")
    assert undecodable.state == "not_available"
    assert "cannot be read" in (undecodable.reason or "")


def test_a_file_over_the_budget_is_named_but_not_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(symbols, "MAX_SOURCE_BYTES", 16)
    found = symbols.outline(_write(tmp_path, "big.py", "x = 1\n" * 100), "big.py", "python")
    assert found.state == "not_available"
    assert "budget" in (found.reason or "")


def test_a_survey_summarises_each_language_once_in_a_stable_order(tmp_path: Path) -> None:
    _write(tmp_path, "m.py", PYTHON)
    _write(tmp_path, "a.ts", TYPESCRIPT)
    _write(tmp_path, "b.rs", RUST)
    sources = [("m.py", "python"), ("a.ts", "typescript"), ("b.rs", "rust")]

    first = symbols.survey(tmp_path, sources)
    second = symbols.survey(tmp_path, list(reversed(sources)))

    assert first.state == "complete"
    assert [item.language for item in first.languages] == ["python", "rust", "typescript"]
    # Two runs over the same tree in a different order answer identically, or an
    # index would depend on the order a walk happened to return.
    assert first.languages == second.languages


def test_a_survey_that_hits_its_file_budget_says_where_it_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(symbols, "MAX_OUTLINED_FILES", 1)
    for name in ("a.py", "b.py", "c.py"):
        _write(tmp_path, name, "def visible() -> None: ...\n")
    found = symbols.survey(tmp_path, [(name, "python") for name in ("a.py", "b.py", "c.py")])
    assert found.state == "partial"
    assert found.stopped_by == "file budget"
    assert len(found.outlines) == 1


def test_a_language_whose_files_all_failed_is_reported_not_available(tmp_path: Path) -> None:
    _write(tmp_path, "b.py", "def (")
    found = symbols.survey(tmp_path, [("b.py", "python")])
    summary = found.languages[0]
    assert summary.state == "not_available"
    assert summary.symbols == 0
    assert summary.reason


def test_the_command_reads_the_index_rather_than_walking_again(tmp_path: Path) -> None:
    from ai_stp_cli.commands import project

    (tmp_path / ".git").mkdir()
    _write(tmp_path, "m.py", PYTHON)
    _write(tmp_path, "test_m.py", "def test_thing() -> None: ...\n")
    _write(tmp_path, "notes.md", "# not source")

    answer = project.symbol_index({"root": str(tmp_path)}).payload
    assert answer.state == "complete"
    python = next(item for item in answer.languages if item.language == "python")
    assert python.method == "syntax_tree"
    assert python.files == 2
    assert python.tests == 1
    # The Markdown file is in the index and is not a language, so it never
    # reaches the adapters.
    assert [item.language for item in answer.languages] == ["python"]


def test_the_command_refuses_without_a_root() -> None:
    from ai_stp_cli.commands import project
    from ai_stp_cli.errors import CliFailure

    with pytest.raises(CliFailure, match="project root is required"):
        project.symbol_index({})
