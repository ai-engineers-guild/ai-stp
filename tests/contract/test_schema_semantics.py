"""Semantic parity: generated schemas accept and reject the same wire values
as the Python models, are metaschema-valid and carry stable identifiers."""

import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from ai_stp_contracts.schemas import EXPORTED_MODELS
from ai_stp_foundation import ComponentRef, SetupRef, digest_canonical, new_id
from ai_stp_foundation.schemas import SCHEMA_DIALECT, schema_id

SCHEMAS_DIR = Path(__file__).parents[2] / "schemas" / "v1"
DIGEST = digest_canonical("ai-stp:passport:v1", {"fixture": True})


def _schema(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text()))


def _schema_accepts(name: str, instance: object) -> bool:
    validator = Draft202012Validator(_schema(name))
    # jsonschema types its instance parameter with a private alias that plain
    # ``object`` cannot satisfy under strict mode; the runtime accepts any JSON.
    result = validator.is_valid(instance)  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    return bool(result)


def _model_accepts(model: type[BaseModel], instance: object) -> bool:
    try:
        model.model_validate(instance)
    except ValidationError:
        return False
    return True


def test_every_schema_is_metaschema_valid_with_stable_identity() -> None:
    seen_ids: set[str] = set()
    for name in EXPORTED_MODELS:
        schema = _schema(name)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == SCHEMA_DIALECT
        assert schema["$id"] == schema_id(name)
        assert schema["$id"] not in seen_ids
        seen_ids.add(cast(str, schema["$id"]))


_REF_CASES: list[tuple[str, type[BaseModel], dict[str, object], bool]] = [
    (
        "component-ref",
        ComponentRef,
        {"stable_id": new_id("component"), "version": "1.2", "passport_digest": DIGEST},
        True,
    ),
    (
        "component-ref",
        ComponentRef,
        {
            "stable_id": new_id("component"),
            "variant_id": new_id("variant"),
            "version": "0.1",
            "passport_digest": DIGEST,
        },
        True,
    ),
    (
        "component-ref",
        ComponentRef,
        {"stable_id": new_id("setup"), "version": "1.2", "passport_digest": DIGEST},
        False,
    ),
    (
        "component-ref",
        ComponentRef,
        {"stable_id": "component_8" + "0" * 25, "version": "1.2", "passport_digest": DIGEST},
        False,
    ),
    (
        "component-ref",
        ComponentRef,
        {"stable_id": new_id("component"), "version": "01.2", "passport_digest": DIGEST},
        False,
    ),
    (
        "component-ref",
        ComponentRef,
        {"stable_id": new_id("component"), "version": "1.2", "passport_digest": "sha256:xyz"},
        False,
    ),
    (
        "setup-ref",
        SetupRef,
        {"stable_id": new_id("setup"), "version": "2.10", "passport_digest": DIGEST},
        True,
    ),
    (
        "setup-ref",
        SetupRef,
        {
            "stable_id": new_id("setup"),
            "variant_id": new_id("variant"),
            "version": "1.0",
            "passport_digest": DIGEST,
        },
        False,
    ),
]


@pytest.mark.parametrize(("name", "model", "instance", "accepted"), _REF_CASES)
def test_model_and_schema_agree_on_references(
    name: str, model: type[BaseModel], instance: dict[str, object], accepted: bool
) -> None:
    assert _model_accepts(model, instance) is accepted
    assert _schema_accepts(name, instance) is accepted


def test_exactly_one_wire_version_exists_and_REQ_1510_is_not_yet_due() -> None:
    """A tripwire for `SPEC-015` REQ-1510, which cannot be satisfied yet.

    REQ-1510 asks that a change to canonicalization, a hash domain or an
    incompatible schema come with a new version, a migration and double-reading
    window, and mixed-version fixtures. None of that is testable while exactly
    one version exists — a mixed-version fixture needs two versions.

    So this pins the premise instead of pretending the requirement is met. The
    moment a second `schema_version` appears anywhere in the published schemas,
    this fails and points at the requirement that has just become due.
    """
    versions: set[str] = set()
    declaring = 0
    for path in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        document = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        properties = cast(dict[str, object], document.get("properties", {}))
        field = properties.get("schema_version")
        if not isinstance(field, dict):
            continue
        declaring += 1
        for key in ("const", "enum"):
            if key in field:
                versions.add(json.dumps(field[key]))

    assert declaring > 0, "no published schema declares a version"
    assert versions == {"1"}, (
        "a second wire version exists; SPEC-015 REQ-1510 now requires a migration "
        f"and double-reading window with mixed-version fixtures. Found: {sorted(versions)}"
    )
