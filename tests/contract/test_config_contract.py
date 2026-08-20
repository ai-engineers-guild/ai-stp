"""The configuration contract owns the fields; the code must match it.

`SPEC-011` REQ-1114 makes `docs/contracts/cli-config.md` the owner of the closed
field list and the defaults, and its oracle asks that a fixture cover every
field and every default. The document carries a YAML block with the concrete
values -- the machine-readable half of the contract -- and nothing was holding
the code to it.

Two lists that agree today and are checked by nobody are two lists that will
disagree, and the document is what a user reads before the code exists for
them.
"""

import re
from pathlib import Path
from typing import Any, cast

import yaml

from ai_stp_cli.config import declared_fields

CONTRACT = Path(__file__).parents[2] / "docs" / "contracts" / "cli-config.md"

#: Values the document states in prose because they depend on the machine.
#: Their shape is checked instead of their text.
ENVIRONMENT_DEPENDENT = {"registry.path"}


def _documented() -> dict[str, object]:
    """The YAML block in the contract, flattened to dotted paths."""
    text = CONTRACT.read_text(encoding="utf-8")
    block = re.search(r"```yaml\n(.*?)```", text, re.DOTALL)
    assert block is not None, "the contract carries no YAML block of fields"
    document = cast(dict[str, Any], yaml.safe_load(block.group(1)))

    flat: dict[str, object] = {}
    for key, value in document.items():
        if key == "schema_version":
            continue
        if isinstance(value, dict):
            for inner, item in cast(dict[str, object], value).items():
                flat[f"{key}.{inner}"] = item
        else:
            flat[key] = value
    return flat


def test_the_code_declares_exactly_the_fields_the_contract_does() -> None:
    assert {field.path for field in declared_fields()} == set(_documented())


def test_every_default_matches_the_one_the_contract_states() -> None:
    documented = _documented()
    for field in declared_fields():
        if field.path in ENVIRONMENT_DEPENDENT:
            continue
        assert field.default == documented[field.path], field.path


def test_an_environment_dependent_default_still_has_the_shape_the_contract_shows() -> None:
    # `${XDG_DATA_HOME}/ai-stp/registry.sqlite` cannot be compared literally, but
    # its tail can: a default that stopped ending in the registry file name
    # would be a different contract. Compare with POSIX separators so Windows
    # paths still match the document's `/ai-stp/registry.sqlite` shape.
    documented = _documented()
    for path in ENVIRONMENT_DEPENDENT:
        field = next(item for item in declared_fields() if item.path == path)
        tail = str(documented[path]).split("}")[-1]
        actual = str(field.default).replace("\\", "/")
        assert actual.endswith(tail), path


def test_the_contract_states_a_default_for_every_field_it_declares() -> None:
    # A field in the table with no value in the block would leave the code free
    # to choose, and then the document would stop being the owner.
    text = CONTRACT.read_text(encoding="utf-8")
    tabled = set(re.findall(r"^\| `([a-z][a-z0-9_.]*)` \|", text, re.MULTILINE))
    assert tabled == set(_documented())
