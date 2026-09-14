"""Every retried mutation carries something the server can deduplicate.

The transport retries a transport error, a 5xx and a rate limit for any method,
because a lost answer is not an answer. That is only safe while every mutation
it can repeat is one the server recognises as the same operation. Today each of
them carries a durable idempotency key or is idempotent by construction — and
nothing in the code says so, which is how the next route added would inherit
blind retry without anyone deciding that it should.

This test is that decision, written down and checked: it reads the call sites
out of the transport modules and requires each mutating one to carry a key in
its request model, or to be listed below with the reason it does not need one.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Final

from pydantic import BaseModel

CLOUD = Path(__file__).resolve().parents[2] / "apps" / "cli" / "src" / "ai_stp_cli" / "cloud"
MUTATIONS: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: What the server stores a result under. `event_id` belongs to the private-sync
#: envelope, where the durable identity is per event rather than per request.
KEY_FIELDS: Final[tuple[str, ...]] = ("idempotency_key", "event_id")

#: Mutations that carry no key and do not need one, each with the reason. A new
#: entry here is a claim about the route that someone has to defend in review.
NATURALLY_REPLAY_SAFE: Final[dict[str, str]] = {
    "/auth/device/token": (
        "the device-code exchange is a poll by design: the CLI already repeats it "
        "while the user decides, and the code is the operation identity"
    ),
    "/auth/logout": "ending a session twice ends it once; there is no second effect to create",
    "/sync/push": (
        "the key is per event inside the envelope, not per request: "
        "SyncEvent.event_id is what the server deduplicates"
    ),
}


class _Site:
    """One mutating call the transport can repeat."""

    def __init__(self, module: str, line: int, method: str, route: str, body: ast.expr | None):
        self.module = module
        self.line = line
        self.method = method
        self.route = route
        self.body = body

    def __str__(self) -> str:
        return f"{self.module}:{self.line} {self.method} {self.route}"


def _sites(
    tree: ast.Module, source: str, module: str
) -> list[tuple[_Site, ast.FunctionDef | None]]:
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    found: list[tuple[_Site, ast.FunctionDef | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in {"call", "call_document"} or len(node.args) < 3:
            continue
        method = getattr(node.args[1], "value", "")
        if method not in MUTATIONS:
            continue
        route = ast.get_source_segment(source, node.args[2]) or ""
        body = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "body"),
            None,
        )
        enclosing = next(
            (
                function
                for function in functions
                if function.lineno <= node.lineno <= (function.end_lineno or node.lineno)
            ),
            None,
        )
        found.append((_Site(module, node.lineno, method, route, body), enclosing))
    return found


def _named_model(module_name: str, name: str) -> type[BaseModel] | None:
    module = importlib.import_module(module_name)
    candidate = getattr(module, name, None)
    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
        return candidate
    return None


def _model_for(site: _Site, enclosing: ast.FunctionDef | None) -> type[BaseModel] | None:
    """The request model behind a body argument.

    Either the function takes it as a typed parameter, or it builds one here —
    `login.start` mints its own idempotency key rather than accepting one.
    """
    module_name = f"ai_stp_cli.cloud.{Path(site.module).stem}"
    if isinstance(site.body, ast.Call):
        built = getattr(site.body.func, "id", None) or getattr(site.body.func, "attr", None)
        return None if built is None else _named_model(module_name, built)
    if not isinstance(site.body, ast.Name) or enclosing is None:
        return None
    wanted = site.body.id
    arguments = [*enclosing.args.args, *enclosing.args.kwonlyargs]
    for argument in arguments:
        if argument.arg == wanted and isinstance(argument.annotation, ast.Name):
            return _named_model(module_name, argument.annotation.id)
    for node in ast.walk(enclosing):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if wanted not in targets:
            continue
        built = getattr(node.value.func, "id", None) or getattr(node.value.func, "attr", None)
        if built is not None:
            return _named_model(module_name, built)
    return None


def test_every_retried_mutation_is_replay_safe() -> None:
    unsafe: list[str] = []
    seen = 0
    for path in sorted(CLOUD.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for site, enclosing in _sites(tree, source, path.name):
            seen += 1
            if any(known in site.route for known in NATURALLY_REPLAY_SAFE):
                continue
            if site.body is None:
                unsafe.append(f"{site} sends no body to identify the operation")
                continue
            model = _model_for(site, enclosing)
            if model is None:
                unsafe.append(f"{site} has no resolvable request model")
                continue
            if not any(field in model.model_fields for field in KEY_FIELDS):
                unsafe.append(f"{site} uses {model.__name__}, which carries no idempotency key")
    assert seen >= 15, "the transport inventory found almost nothing; the reader is broken"
    assert unsafe == [], "\n".join(unsafe)
