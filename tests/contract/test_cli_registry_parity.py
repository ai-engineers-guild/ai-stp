"""Machine help must describe an invocation the handler actually accepts.

`registry.py` is the one structural command list, so the parser and machine
help can never drift apart in *shape*. What it does not settle is *semantics*:
a descriptor says `required=False` while its handler refuses the call without
that option, and every existing check stays green — the golden fixture pins the
registry as reviewed, which is exactly as good at pinning a wrong value as a
right one.

`SPEC-011` REQ-1102 says machine help describes each option as the agent must
supply it. An agent that reads `required=false` and omits the option is
following the contract; being refused afterwards means the contract was wrong.

So this reads the handlers rather than the descriptors: it walks each handler's
body with `ast` and collects the options it demands before it can do anything.
Only unconditional demands count — an option required inside an `if` is a
conditional requirement, which `parameter_rules` exists to express, and calling
it `required` would make the descriptor wrong in the other direction.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Final

from ai_stp_cli.registry import COMMANDS

#: Helpers that mean "this option must be present or the command fails". Every
#: command module spells the same idea with its own copy; the name is the
#: contract because the bodies all raise before returning.
_DEMAND_HELPERS: Final[frozenset[str]] = frozenset({"_required", "_required_env"})

#: What a handler raises when a missing option makes the call impossible.
_REFUSAL: Final[str] = "CliFailure"

#: Consent flags, which the descriptor already describes through its own
#: `confirmation` field rather than through `required`. The two say different
#: things and the CLI keeps them apart on purpose: `required` is the shape of a
#: valid call, so omitting it is the agent's mistake; `confirmation` is a human
#: decision, and refusing it is not a mistake at all — it has its own exit
#: class. Marking `--confirm` required would merge them and turn a withheld
#: decision into a parse error.
_CONSENT: Final[frozenset[str]] = frozenset({"confirm"})


def _string(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Demands(ast.NodeVisitor):
    """Options a handler demands on every path through its own body.

    Two shapes carry the same meaning and both appear in the tree:

        stable_id = _required(parameters, "id", "a stable id is required")

        given = parameters.get("root")
        if given is None:
            raise CliFailure(...)

    Nested function bodies are skipped: a closure runs later, under whatever
    conditions its caller applies, so a demand inside one is not unconditional.
    """

    def __init__(self) -> None:
        self.names: set[str] = set()
        #: Local variable -> the option it was read from, for the second shape.
        self._read_from: dict[str, str] = {}
        self._depth = 0

    # A nested definition is not part of this handler's unconditional body.
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._depth:
            return
        self._depth += 1
        for statement in node.body:
            self.visit(statement)
        self._depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        del node

    def visit_Lambda(self, node: ast.Lambda) -> None:
        del node

    # Anything conditional is a `parameter_rules` matter, not a `required` one.
    def visit_If(self, node: ast.If) -> None:
        self._conditional_refusal(node)

    def visit_Try(self, node: ast.Try) -> None:
        del node

    def visit_For(self, node: ast.For) -> None:
        del node

    def visit_While(self, node: ast.While) -> None:
        del node

    def visit_Assign(self, node: ast.Assign) -> None:
        option = _read_option(node.value)
        if option is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._read_from[target.id] = option
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        function = node.func
        name = function.id if isinstance(function, ast.Name) else None
        if name in _DEMAND_HELPERS and len(node.args) >= 2:
            demanded = _string(node.args[1])
            if demanded is not None:
                self.names.add(demanded)
        self.generic_visit(node)

    def _conditional_refusal(self, node: ast.If) -> None:
        """`if <read option> is None: raise CliFailure(...)` is a demand."""
        test = node.test
        subject: str | None = None
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            if isinstance(test.ops[0], ast.Is) and _is_none(test.comparators[0]):
                subject = _subject(test.left, self._read_from)
        elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            subject = _subject(test.operand, self._read_from)
        if subject is not None and _raises_refusal(node.body):
            self.names.add(subject)


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _read_option(node: ast.expr) -> str | None:
    """`parameters.get("name")` — the option this expression reads."""
    if not isinstance(node, ast.Call):
        return None
    function = node.func
    if not isinstance(function, ast.Attribute) or function.attr != "get":
        return None
    if not isinstance(function.value, ast.Name) or function.value.id != "parameters":
        return None
    return _string(node.args[0]) if node.args else None


#: Coercions a handler wraps a read in before testing it. `component passport
#: validate` writes `if not bool(parameters.get("for-publication"))`, and an
#: analyser that stops at the outer call misses the demand — which is how that
#: option stayed optional in machine help while the handler refused without it.
_TRANSPARENT: Final[frozenset[str]] = frozenset({"bool", "str", "len", "int"})


def _subject(node: ast.expr, read_from: dict[str, str]) -> str | None:
    """The option a test is about, however it was spelled."""
    inline = _read_option(node)
    if inline is not None:
        return inline
    if isinstance(node, ast.Name):
        return read_from.get(node.id)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _TRANSPARENT
        and node.args
    ):
        return _subject(node.args[0], read_from)
    return None


def _raises_refusal(body: list[ast.stmt]) -> bool:
    for statement in body:
        if not isinstance(statement, ast.Raise) or statement.exc is None:
            continue
        raised = statement.exc
        called = raised.func if isinstance(raised, ast.Call) else raised
        if isinstance(called, ast.Name) and called.id == _REFUSAL:
            return True
    return False


def _demanded(command: object) -> set[str]:
    handler = getattr(command, "handler")  # noqa: B009 — attribute, not a key
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):  # pragma: no cover — every handler has a file
        return set()
    tree = ast.parse(textwrap.dedent(source))
    visitor = _Demands()
    for node in tree.body:
        visitor.visit(node)
    return visitor.names


def test_every_option_a_handler_demands_is_declared_required() -> None:
    """The defect this exists for, stated as a property over all 123 commands.

    Found by review as six examples — `component version list --id`,
    `component version release --id`, `component fork --id --version`, and
    `--root` on four `project` commands. Fixing six strings would leave the
    seventh to be found the same way; the sweep is the fix.
    """
    wrong: list[str] = []
    for command in COMMANDS:
        declared = {parameter.name: parameter for parameter in command.descriptor.parameters}
        for name in sorted(_demanded(command)):
            if name in _CONSENT and command.descriptor.confirmation != "none":
                continue
            parameter = declared.get(name)
            if parameter is None:
                wrong.append(f"{command.name}: handler demands --{name}, descriptor omits it")
            elif not parameter.required:
                wrong.append(f"{command.name}: handler demands --{name}, descriptor says optional")
    assert not wrong, "machine help understates what these commands need:\n" + "\n".join(wrong)


def test_the_sweep_reads_handlers_rather_than_trusting_the_registry() -> None:
    """Guard the oracle itself: an analyser that finds nothing proves nothing.

    If a refactor renames `_required` or moves the refusal into a helper, the
    test above starts passing for the wrong reason — it would compare an empty
    set against every descriptor and agree. This fails first, and says why.
    """
    seen = sum(len(_demanded(command)) for command in COMMANDS)
    assert seen >= 100, (
        f"the handler sweep found only {seen} demanded options across {len(COMMANDS)} commands; "
        "the analyser has stopped recognising how handlers refuse a missing option"
    )


def test_a_repeatable_option_says_so_where_the_parser_reads_it() -> None:
    """Prose in a summary is not a parameter the parser can act on.

    `component find --tag` reads "Repeat to require several", the handler
    normalises a list, and the search layer takes a tuple — but the descriptor
    said `repeatable=False`, so `_option_for` built Click with
    `multiple=False`. Repeating the option then silently kept the last value:
    `--tag a --tag b` searched for `b` alone and answered as if that were the
    question. A wrong answer, not an error.
    """
    hinted = ("repeat", "повтор", "several", "multiple", "each")
    wrong = [
        f"{command.name} --{parameter.name}: {parameter.summary!r}"
        for command in COMMANDS
        for parameter in command.descriptor.parameters
        if not parameter.repeatable and any(word in parameter.summary.lower() for word in hinted)
    ]
    assert not wrong, (
        "these summaries promise repetition the parser will not deliver:\n" + "\n".join(wrong)
    )


def test_this_check_lives_where_the_registry_lives() -> None:
    """The sweep is worthless in a tree whose handlers it cannot read."""
    module = Path(inspect.getfile(COMMANDS[0].handler))
    assert module.is_file(), f"handler source unavailable at {module}"


def test_every_command_group_says_what_it_is_for() -> None:
    """A group name spelled back is not a description of the group.

    `--help` answered "Commands for component." for thirty-six of thirty-seven
    groups. Each leaf underneath is described precisely in `help --agent`, but
    a caller reaches the group first, and someone who does not already know
    what `select` or `target` covers learned nothing from the one place built
    to tell them.

    This fails on a new group before anyone notices the placeholder, which is
    how the placeholder lasted: it reads like an answer.
    """
    from ai_stp_cli import app

    groups = {
        tuple(command.descriptor.path[:index])
        for command in COMMANDS
        for index in range(1, len(command.descriptor.path))
    }
    described = {
        path: app._group_content(path)[0]  # pyright: ignore[reportPrivateUsage]
        for path in groups
    }
    unnamed = sorted(
        " ".join(path) for path, line in described.items() if line.startswith("Commands for ")
    )
    assert not unnamed, "these groups have no description of their own: " + ", ".join(unnamed)
