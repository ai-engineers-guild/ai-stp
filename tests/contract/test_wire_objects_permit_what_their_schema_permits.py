"""A response model must accept every document its own published schema allows.

`open_wire_object` writes `additionalProperties: true` into the generated
schema, and its docstring has said since it was written that a class using it
must be `extra="allow"`, never `extra="forbid"`. Nothing checked it. On
2026-09-02 twenty-six classes forbade extras while publishing a schema that
permitted them, and the two halves of one contract disagreed in the direction
that costs the most: the platform added an optional `components` list to the
checks summary, the deployed server answered `200` with it, and every released
CLI — `0.0.14` and `0.0.15` both — refused the body of `registry search` for
every kind, which is the one command a person uses to find a published setup.
An installed client could only have been rescued by upgrading it.

So the rule is measured here rather than described in a docstring. Requests are
the mirror and keep `extra="forbid"`: an unknown query parameter is a silently
dropped filter, not forward compatibility, and `strict_request_object` writes
`additionalProperties: false` to say so.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType
from typing import Any

import pytest
from pydantic import BaseModel

import ai_stp_contracts
from ai_stp_contracts import http, safety_checks


def _modules() -> list[ModuleType]:
    """Every module of the contract package, discovered rather than listed.

    A hand-written list is the defect this file exists for, one level up: the
    module that is forgotten is the one whose classes are never checked.
    """
    found = [ai_stp_contracts]
    for info in pkgutil.walk_packages(ai_stp_contracts.__path__, f"{ai_stp_contracts.__name__}."):
        try:
            found.append(importlib.import_module(info.name))
        except ImportError:  # pragma: no cover - a module needing an optional extra
            continue
    return found


def _wire_models() -> list[tuple[str, type[BaseModel], Any]]:
    """Every model in the contract package, with the wire hook it declares."""
    found: dict[str, tuple[str, type[BaseModel], Any]] = {}
    for module in _modules():
        for value in vars(module).values():
            if not inspect.isclass(value) or not issubclass(value, BaseModel):
                continue
            if value is BaseModel:
                continue
            name = f"{value.__module__}.{value.__qualname__}"
            found[name] = (name, value, value.model_config.get("json_schema_extra"))
    return sorted(found.values(), key=lambda item: item[0])


def test_the_sweep_reaches_the_models_it_is_meant_to_judge() -> None:
    """A guard on the guard: an empty walk would make both rules below vacuous."""
    models = _wire_models()
    hooks = [
        item for item in models if item[2] in (http.open_wire_object, http.strict_request_object)
    ]
    assert len(models) > 100, f"only {len(models)} models discovered"
    assert len(hooks) > 50, f"only {len(hooks)} of them declare a wire hook"


def test_every_response_object_accepts_the_additions_its_schema_promises() -> None:
    """`additionalProperties: true` in the schema, `extra="allow"` in the model."""
    offenders = [
        name
        for name, model, hook in _wire_models()
        if hook is http.open_wire_object and model.model_config.get("extra") != "allow"
    ]
    assert not offenders, (
        "these response models publish additionalProperties: true and then reject "
        f"the additions: {', '.join(sorted(offenders))}"
    )


def test_every_request_object_refuses_what_its_schema_refuses() -> None:
    """The mirror: an instruction is not a description, and does not tolerate additions."""
    offenders = [
        name
        for name, model, hook in _wire_models()
        if hook is http.strict_request_object and model.model_config.get("extra") != "forbid"
    ]
    assert not offenders, (
        "these request models publish additionalProperties: false and then accept "
        f"the additions: {', '.join(sorted(offenders))}"
    )


@pytest.mark.parametrize("kind", ["component", "setup"])
def test_a_newer_server_may_add_a_field_to_the_checks_summary(kind: str) -> None:
    """The exact document that broke every released client, accepted.

    Not a general property restated: this is the shape the deployed platform
    answered with on 2026-09-02 — an optional list inside `latest_checks` that
    no released model declared — and the unknown value is preserved rather than
    dropped, which is what `schema-evolution.md` asks of a reader.
    """
    summary = safety_checks.SafetyChecksSummary.model_validate(
        {
            "schema_version": 1,
            "status": "empty",
            "checks_passed_percent": None,
            "coverage_complete": False,
            "passed": 0,
            "failed": 0,
            "warning": 0,
            "not_run": 0,
            "total_countable": 0,
            "checks": [],
            "components": [],
            "a_field_from_a_later_server": {"kind": kind},
        }
    )
    assert summary.status == "empty"
    # Preserved, not dropped: `schema-evolution.md` asks a reader to keep an
    # unknown optional value, and `model_extra` is where pydantic keeps it.
    assert summary.model_extra == {"a_field_from_a_later_server": {"kind": kind}}
