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
from urllib.parse import urlsplit

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


def test_the_shipped_catalogue_address_is_one_that_can_answer() -> None:
    """A default that cannot work is not a default.

    `catalog.url` shipped as `https://ai-stp.example`. `.example` is reserved by
    RFC 2606 for documentation and resolves nowhere, so a fresh install found no
    components and no setups at all — and said so as
    `AI_STP_DEPENDENCY_UNAVAILABLE: the platform could not be reached`, which
    reads as an outage rather than as an address that was never real.

    Measured before the change: `registry search --kind component` on a clean
    home returned that error; with `catalog.url` pointed at the deployment it
    returned fifty components and a cursor. Every evidence slice in this
    repository already defaulted to the deployment, so the CLI was the one place
    still holding the placeholder.

    The check is the property rather than the hostname: a reserved documentation
    domain may not be the value a person gets before configuring anything.
    """
    reserved = (".example", ".invalid", ".test", ".localhost")
    shipped = {
        field.path: field.default
        for field in declared_fields()
        if isinstance(field.default, str) and field.default.startswith("https://")
    }
    assert shipped, "no address-shaped defaults found, so this guards nothing"
    offending = {
        path: value
        for path, value in shipped.items()
        # Telemetry is exempt, and the reason is stronger than the one first
        # written here. "Off by default" would only argue that the placeholder
        # is rarely reached; what makes it *correct* is that there is nothing to
        # point it at. Measured: no telemetry route exists in `apps/api`, and
        # the deployment answers 404 on every plausible path. `.example` is the
        # honest value for a receiver that has not been built.
        #
        # It is also visible rather than hidden: `telemetry show` prints the
        # address and its source, so a person reading the consent screen sees a
        # documentation domain before answering. And the send is best-effort by
        # construction (`REQ-1318`) — every path out is "no ping" rather than an
        # error, so a placeholder cannot fail an install.
        #
        # When a receiver exists this exemption should go, not be widened.
        if path != "telemetry.url"
        and any(urlsplit(value).hostname.endswith(suffix) for suffix in reserved)  # pyright: ignore[reportOptionalMemberAccess]
    }
    assert not offending, offending
