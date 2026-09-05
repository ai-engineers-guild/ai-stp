"""Structural sweeps over the whole CLI, starting with: nothing exists without a caller.

Each check here is one that coverage cannot see and review keeps missing, because
the two halves are correct in isolation and only their absence of a link is
wrong: a function nobody calls, an option nobody reads, a next action nobody can
run, an error code nobody registered.

The first and oldest (issues #72-#77):

Written after finding four safeguards that were implemented, documented and
unit-tested — and wired into nothing. `cache.verify` never ran, so a corrupted
passport would have been cached. `journal.unsettled` never surfaced, so the
operation journal was write-only. `secrets.promote` never ran, so a file-tier
secret survived the machine gaining a real credential store. And
`identity.retired_identities` recorded retirements nobody could read.

Each looked complete in review and each was fully covered. Coverage cannot see
this: a function reached only by its own test is 100% covered and completely
dead.

So the property is checked structurally, over module-level functions only.
Methods are reached through instances and this analysis cannot follow that;
claiming otherwise would make the gate noisy, and a noisy gate gets exemptions
until it means nothing.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).parents[2]
CLI_SOURCE = ROOT / "apps" / "cli" / "src" / "ai_stp_cli"
APP_SOURCES = (
    CLI_SOURCE,
    ROOT / "apps" / "api" / "src" / "ai_stp_api",
    ROOT / "apps" / "platform" / "src" / "ai_stp_platform",
    ROOT / "apps" / "worker" / "src" / "ai_stp_worker",
)
REFERENCE_ROOTS = (ROOT / "apps", ROOT / "packages", ROOT / "scripts")
SOURCE = CLI_SOURCE

_ROUTE_ATTRS = frozenset(
    {
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "api_route",
        "websocket",
        "on_event",
        "middleware",
    }
)
_MODEL_ATTRS = frozenset({"field_validator", "model_validator", "computed_field", "validator"})

#: Entry points the outside world reaches directly: the console script and the
#: module form.
ROOTS = frozenset({"run", "main", "create_app"})

#: Reachable by a mechanism the call graph cannot see, each for a stated reason.
#: An entry here is a claim, and the second test below keeps it honest.
EXEMPT: dict[str, str] = {
    # `#74` requires rollback "where declared". The mechanism is a maintenance
    # step rather than a command, and removing it would make every `down`
    # statement dead.
    "database.downgrade": "the migration reverse `#74` requires, invoked by a maintainer",
    # The rule is about what may be *declared*, not about what runs, so the
    # registry invariant test is its only caller by design.
    "registry.reserved_option_names": "the registry invariant a test enforces",
    # The device key's published purpose. `ai_stp_assurance` fixes the
    # attestation shape and defers key handling to `#73`; the consumer arrives
    # with validation evidence.
    "identity.verify": "the device key's published purpose, consumed by attestations",
    # `#161` took over two of the three exemptions this once held: local search
    # applies both the draft-and-tombstone filter and the revoking-event
    # comparison, so they are reached now. This one is the deliverable of `#159`
    # that is still waiting for its writer, and it is listed rather than deleted
    # because deleting it would ship the provenance table and drop the rule that
    # makes the table mean anything.
    "lifecycle.record_overlay": "overlay provenance `#159` delivers, written on materialisation "
    "when the setup compiler lands",
    # Publication writes CatalogMetadata itself and #312 binds bytes on confirm.
    # This outbox remains the transactional catalog+upload primitive SPEC-018
    # names when the next step is still an upload job.
    "catalog.create_catalog_metadata_and_enqueue_upload": (
        "catalog+upload outbox SPEC-018 requires; publication writes CatalogMetadata itself"
    ),
    # REQ-1808 is cooperative cancel of a not-yet-running job. The worker drain
    # path requeues held work instead of cancelling it; an operator invokes this
    # before claim.
    "engine.cancel": "cooperative cancel REQ-1808 requires, invoked by an operator before claim",
    # In-process counters and sandbox-mode cache. Production must not reset them
    # mid-run; tests isolate cases with these two functions.
    "metrics.reset_metrics": (
        "in-process counter reset tests use so one case cannot leak into the next"
    ),
    "metrics.reset_seo_metrics": (
        "in-process SEO counter reset tests use so one case cannot leak into the next"
    ),
    "sandbox.reset_sandbox_cache": (
        "sandbox mode cache reset tests use so one case cannot leak into the next"
    ),
    # Public document API is read-only. A published revision is written by the
    # repository-source import SPEC-031 names, not by a request handler.
    "service.publish_revision": (
        "staff policy publish SPEC-031 requires, invoked when a published revision "
        "is imported from the repository source"
    ),
    # ADR-0148 moved component scaffolding to source/projections; scaffold() is
    # the portable mustache authoring template generator preserved for SPEC-005 REQ-528.
    "authoring.scaffold": (
        "portable authoring template generator SPEC-005 REQ-528 and ADR-0148 preserve"
    ),
    # Public convenience helper from bindings for the formula #270 defines,
    # exported by ai_stp_platform.safety for consumers and tests.
    "percent.checks_passed_percent": (
        "public passed-share calculator from check bindings (#270) exported by safety"
    ),
    # Public read, maintenance and operator helpers are intentionally exposed
    # for routers, migration tooling, and tests; this AST sweep cannot follow
    # those framework/dynamic call boundaries.
    "catalog_projection.passport_matches_filters": (
        "public catalog filter helper consumed by query projections"
    ),
    "catalog_read.list_latest_public_objects": (
        "public catalog read helper consumed by API adapters"
    ),
    "catalog_search.rebuild_catalog_search_projection": (
        "operator rebuild command invoked by maintenance tooling"
    ),
    "catalog_support.support_matches_filters": (
        "public support filter helper consumed by catalog tests and adapters"
    ),
    "catalog_transfer.apply_author_verification": (
        "staff database decision helper invoked by operator workflows"
    ),
    "catalog_transfer.official_account_id": (
        "public Official identity constant exported for database workflows"
    ),
    "catalog_transfer.transfer_catalog_line": (
        "staff database transfer helper invoked by operator workflows"
    ),
    "enqueue.idempotency_key": (
        "official daily scheduler key helper used by worker job construction"
    ),
    "enqueue.manual_idempotency_key": (
        "official manual scheduler key helper used by operator job construction"
    ),
    "identity.collect_identity_conflicts": (
        "migration/reconciliation audit helper invoked by maintenance tooling"
    ),
    "identity.current_catalog_identity": "public catalog identity lookup consumed by API adapters",
    "identity.locale_names": "public localized identity lookup consumed by API adapters",
    "service.create_external_product": (
        "owner route service reached through the API router boundary"
    ),
    "service.list_tag_vocabulary": (
        "catalog route vocabulary helper reached through the API router boundary"
    ),
    "service.row_matches_updated_range": "catalog range filter helper consumed by query assembly",
    "service.sort_catalog_rows": "catalog ordering helper consumed by query assembly",
    "service.sort_relevant_catalog_rows": (
        "catalog relevance ordering helper consumed by query assembly"
    ),
    "source.delete_source": "operator cleanup helper invoked by source maintenance tooling",
}


def _iter_python(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(part in {"tests", "test", "__pycache__"} for part in path.parts):
            continue
        yield path


def _modules() -> Iterator[tuple[Path, ast.Module]]:
    for source in APP_SOURCES:
        for path in _iter_python(source):
            yield path, ast.parse(path.read_text(encoding="utf-8"))


def _is_decorator_entry(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """FastAPI routes and pydantic constructors are reached without a name call."""
    for decorator in node.decorator_list:
        func = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(func, ast.Attribute) and func.attr in _ROUTE_ATTRS | _MODEL_ATTRS:
            return True
        if isinstance(func, ast.Name) and func.id in _ROUTE_ATTRS | _MODEL_ATTRS:
            return True
    return False


def _module_level_functions() -> dict[tuple[str, str], Path]:
    """Public functions defined at module level, keyed by module and name.

    Keyed by both because two modules may define the same name: `identity.verify`
    and `cache.verify` are different functions, and folding them together would
    let one vouch for the other.
    """
    found: dict[tuple[str, str], Path] = {}
    for path, tree in _modules():
        for node in tree.body:
            if isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef
            ) and not node.name.startswith("_"):
                found[(_module_name(path), node.name)] = path
    return found


def _module_name(path: Path) -> str:
    """What a caller writes before the dot.

    A package is named by its directory, not by `__init__`. Keying on the file
    stem made every public function in an `__init__.py` unmatchable — a caller
    writes `toolchain.current_platform`, never `__init__.current_platform` — so
    the first package added to this codebase was reported as entirely dead.
    """
    return path.parent.name if path.name == "__init__.py" else path.stem


def _aliases(tree: ast.Module) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve module aliases and from-imported symbols independently."""
    modules: dict[str, str] = {}
    symbols: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                modules[item.asname or item.name.split(".")[0]] = item.name.split(".")[-1]
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            module = node.module.split(".")[-1]
            for item in node.names:
                symbols[item.asname or item.name] = f"{module}.{item.name}"
    return modules, symbols


def _references() -> set[str]:
    """Return module-qualified references, including callback registrations."""
    references: set[str] = set()
    for root in REFERENCE_ROOTS:
        for path in _iter_python(root):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            module_aliases, imported_symbols = _aliases(tree)
            current_module = _module_name(path)
            parent_map = {
                child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    parent = parent_map.get(node)
                    if isinstance(parent, ast.Attribute) and parent.value is node:
                        continue
                    references.add(imported_symbols.get(node.id, f"{current_module}.{node.id}"))
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    imported_receiver = imported_symbols.get(node.value.id)
                    receiver = module_aliases.get(
                        node.value.id,
                        imported_receiver.rsplit(".", 1)[-1]
                        if imported_receiver is not None
                        else node.value.id,
                    )
                    references.add(f"{receiver}.{node.attr}")
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # A command handler is declared by name rather than by
                    # reference: `handler="version:run"` in `registry.py`. The
                    # registry is still the caller — the import simply happens
                    # at dispatch, so thirty command modules stop loading to
                    # answer one command — but an attribute reference was what
                    # proved these functions were reached, and removing it made
                    # 113 of them read as orphans here.
                    #
                    # Read the declaration instead. `test_every_declared_handler
                    # _resolves` proves every one of these strings names a real
                    # callable, so this is a reference the gate can trust rather
                    # than an exemption that hides one.
                    module, separator, attribute = node.value.partition(":")
                    if separator and module.isidentifier() and attribute.isidentifier():
                        references.add(f"{module}.{attribute}")
    return references


def test_every_module_level_function_has_a_caller() -> None:
    references = _references()
    orphans: list[str] = []

    defined = _module_level_functions()
    trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in set(defined.values())}
    for (module, name), path in sorted(defined.items()):
        if name in ROOTS or f"{module}.{name}" in EXEMPT:
            continue
        tree = trees[path]
        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name == name
                and _is_decorator_entry(node)
            ):
                break
        else:
            if f"{module}.{name}" in references:
                continue
            try:
                rel = path.relative_to(ROOT / "apps")
            except ValueError:
                rel = path
            orphans.append(f"{rel}::{name}")

    assert not orphans, (
        "these exist and nothing calls them; wire them in or remove them: " + ", ".join(orphans)
    )


def test_every_exemption_still_names_something_real() -> None:
    # An exemption for a function that no longer exists is a licence nobody
    # needs, and the next reader would take it as precedent.
    keys = {f"{module}.{name}" for module, name in _module_level_functions()}
    for name in EXEMPT:
        assert name in keys, name


def test_every_next_action_names_a_command_that_exists() -> None:
    """`next_actions` is read by an agent that runs what it finds there.

    A value that is advice rather than a command — "run the provider's backup
    command first" — leaves an agent with nothing to do and no way to say so.
    A value naming a command that does not exist is worse: it looks runnable
    and fails on invocation.

    Both surfaces are swept. The descriptors are the easy half; the 188 literals
    inside `CliFailure(...)` are the ones an agent actually meets, because they
    are what a refusal carries. Two of them were prose when this was written.
    """
    import ast

    from ai_stp_cli.registry import COMMANDS

    declared = {" ".join(command.descriptor.path) for command in COMMANDS}

    def _runnable(action: str) -> bool:
        return any(action == name or action.startswith(f"{name} ") for name in declared)

    unrunnable = [
        action
        for command in COMMANDS
        for action in command.descriptor.next_actions
        if not _runnable(action)
    ]

    for place in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(place.read_text("utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "next_actions":
                    continue
                for element in getattr(keyword.value, "elts", []):
                    if not isinstance(element, ast.Constant):
                        continue
                    written = element.value
                    if isinstance(written, str) and not _runnable(written):
                        unrunnable.append(f"{place.name}: {written}")

    assert not unrunnable, f"next actions that name no command: {sorted(unrunnable)}"


def test_every_error_code_the_cli_raises_is_registered() -> None:
    """An unregistered code does not fail where it is written; it fails at the exit.

    `CliFailure` accepts any string, and `exit_class_for` raises `KeyError` on an
    unknown one — at the moment the process is deciding its exit status, where
    the top-level handler turns it into `AI_STP_INTERNAL`. So a typo in a code
    does not produce a wrong code: it replaces the whole failure with an
    internal error, and the real reason never reaches the caller.

    Checked statically, because catching it at runtime means having already lost
    the failure it was hiding.
    """
    import ast

    from ai_stp_foundation.errors import ERROR_CODES

    unregistered: list[str] = []
    for place in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(place.read_text("utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if called != "CliFailure":
                continue
            first = node.args[0]
            if not isinstance(first, ast.Constant):
                continue
            written = first.value
            if isinstance(written, str) and written not in ERROR_CODES:
                unregistered.append(f"{place.name}: {written}")

    assert not unregistered, f"unregistered error codes: {sorted(unregistered)}"


def test_every_command_returns_the_model_its_declared_schema_names() -> None:
    """A declared schema is a promise to whoever validates the answer.

    The published file existing is not the promise: a command can declare
    `cli-installation` and hand back a recovery report, and every check passes
    while an agent validating the envelope against the schema it was told to
    expect fails on real output. The link is the handler's own return type,
    which is `Answer[Model]` for all sixty-eight.
    """
    import typing

    from ai_stp_cli.registry import COMMANDS
    from ai_stp_contracts.schemas import CLI_MODELS

    mismatched: list[str] = []
    for command in COMMANDS:
        declared = command.descriptor.result_schema
        returned = typing.get_type_hints(command.handler).get("return")
        inside = typing.get_args(returned)
        assert declared is not None, f"{' '.join(command.descriptor.path)} declares no schema"
        assert inside, f"{' '.join(command.descriptor.path)} does not return Answer[Model]"

        name = declared.removeprefix("urn:ai-stp:schema:v1:")
        if CLI_MODELS.get(name) is not inside[0]:
            mismatched.append(
                f"{' '.join(command.descriptor.path)} declares {name} "
                f"but returns {getattr(inside[0], '__name__', inside[0])}"
            )

    assert not mismatched, sorted(mismatched)


def test_only_the_shared_invoker_calls_the_v3_transport() -> None:
    """One place decides how a v3 provider is spawned, because one already didn't.

    `provider_invoker` holds the launcher discovery, the isolation boundary, the
    Windows exception `#416` scoped, and the writable places an operation needs.
    A second hand-built call to `invocation_v3.invoke` inherits none of that and
    stays plausible: it works on Linux, which is where it is written and read.

    Both known instances failed exactly that way. One built a plan argv without
    `--prefix`, and six providers were asked to install a program without being
    told where. The other — `select provider-conformance` — discovered the
    launcher itself and so could never run on a host that has no launcher to
    discover, which is every Windows host (`#423`).

    `invocation_v2.invoke` is deliberately not covered here: `conformance_v2`
    needs a phase-carrying signature the shared invoker does not offer, so that
    caller is a different shape rather than a second copy of this one.
    """
    home = CLI_SOURCE / "provider" / "invocation.py"
    strays: list[str] = []
    for path in sorted(CLI_SOURCE.rglob("*.py")):
        if path == home:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if (
                isinstance(called, ast.Attribute)
                and called.attr == "invoke"
                and isinstance(called.value, ast.Name)
                and called.value.id == "invocation_v3"
            ):
                strays.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert not strays, (
        "these spawn a v3 provider without the shared boundary; "
        "call provider.invocation.provider_invoker instead: " + ", ".join(strays)
    )


def test_no_command_declares_one_option_twice() -> None:
    """A duplicate declaration is invisible: the second silently wins.

    Added after a blind edit gave `install plan` two `unverified-provider`
    options. Nothing caught it — not the option-is-read sweep, which only asks
    whether *some* handler reads the name, and not the golden fixture, which
    records whatever the registry says. The machine help would then have shown
    one option twice to every agent reading it.

    The failure is quiet by construction, which is the only reason this is worth
    a structural check rather than review.
    """
    from ai_stp_cli.registry import COMMANDS

    duplicated: list[str] = []
    for command in COMMANDS:
        names = [option.name for option in command.descriptor.parameters]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            duplicated.append(f"{' '.join(command.descriptor.path)}: {', '.join(repeated)}")

    assert not duplicated, sorted(duplicated)
