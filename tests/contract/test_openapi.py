"""The generated OpenAPI document agrees with the models and with schemas/v1.

Two artifacts are published from one source: the per-model files in
`schemas/v1` and the OpenAPI document beside them. Generation makes drift
structurally impossible, so these tests check the properties generation cannot:
that every reference resolves, that every schema is a valid schema, that the two
artifacts describe the same objects, and that no model is published without a
route that serves it.
"""

import json
import re
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate as validate_openapi

from ai_stp_contracts.http import API_BASE_PATH, http_status_for
from ai_stp_contracts.openapi import (
    NESTED_ONLY_MODELS,
    OPENAPI_VERSION,
    OPERATIONS,
    build_document,
    render,
)
from ai_stp_contracts.schemas import CLI_MODELS, HTTP_MODELS, OPENAPI_FILENAME
from ai_stp_foundation.errors import ERROR_CODES

SCHEMAS_DIR = Path(__file__).parents[2] / "schemas" / "v1"
DOCUMENT = build_document()
COMPONENTS = cast(dict[str, dict[str, object]], cast(dict[str, object], DOCUMENT["components"]))
SCHEMAS = cast(dict[str, dict[str, object]], COMPONENTS["schemas"])
PATHS = cast(dict[str, dict[str, dict[str, object]]], DOCUMENT["paths"])


def operations() -> list[tuple[str, str, dict[str, object]]]:
    return [
        (path, method, entry)
        for path, methods in sorted(PATHS.items())
        for method, entry in sorted(methods.items())
    ]


def component_name(model: object) -> str:
    """The component key of an exported model, narrowed for the type checker."""
    name = getattr(model, "__name__", None)
    assert isinstance(name, str), model
    return name


def refs(node: object) -> list[str]:
    """Every `$ref` anywhere in the document."""
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in cast(dict[str, object], node).items():
            if key == "$ref" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(refs(value))
        return found
    if isinstance(node, list):
        return [ref for item in cast(list[object], node) for ref in refs(item)]
    return []


def test_the_committed_document_matches_the_generator() -> None:
    committed = (SCHEMAS_DIR / OPENAPI_FILENAME).read_text(encoding="utf-8")
    assert committed == render()


def test_rendering_is_deterministic() -> None:
    assert render() == render()


def test_the_document_declares_openapi_3_1() -> None:
    assert DOCUMENT["openapi"] == OPENAPI_VERSION == "3.1.0"


def test_every_reference_resolves_inside_the_document() -> None:
    # An unresolvable $ref makes the document unusable to the platform track
    # without telling anyone at generation time.
    for ref in refs(DOCUMENT):
        assert ref.startswith("#/components/schemas/"), ref
        assert ref.removeprefix("#/components/schemas/") in SCHEMAS, ref


def test_every_component_schema_is_a_valid_schema() -> None:
    # OpenAPI 3.1 schemas are JSON Schema 2020-12, so the metaschema applies.
    for name, schema in sorted(SCHEMAS.items()):
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:  # pragma: no cover - only on a real defect
            pytest.fail(f"{name} is not a valid 2020-12 schema: {error}")


def test_every_published_model_is_reachable_from_a_route() -> None:
    # A model exported to schemas/v1 that no operation serves is not future
    # work, it is a published object with no way to obtain it.
    nested = {model.__name__ for model in NESTED_ONLY_MODELS}
    for name, model in sorted(HTTP_MODELS.items()):
        component = component_name(model)
        assert component in SCHEMAS, f"{name} is published but absent from the document"
        if component not in nested:
            served = any(
                component
                in {
                    component_name(operation.response) if operation.response else None,
                    component_name(operation.body) if operation.body else None,
                    component_name(operation.query) if operation.query else None,
                }
                for operation in OPERATIONS
            )
            assert served, f"{name} is published but no operation serves it"


def test_the_two_artifacts_describe_the_same_objects() -> None:
    # The per-model file and the embedded component come from one source, so
    # their property sets and required sets must agree. Reference roots differ
    # by design (`#/$defs` versus `#/components/schemas`), so shape is what is
    # compared.
    for name, model in sorted(HTTP_MODELS.items()):
        standalone = json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
        embedded = SCHEMAS[component_name(model)]
        assert sorted(cast(dict[str, object], standalone["properties"])) == sorted(
            cast(dict[str, object], embedded["properties"])
        ), name
        assert standalone.get("required") == embedded.get("required"), name
        assert standalone.get("additionalProperties") == embedded.get("additionalProperties"), name


def test_every_route_lives_under_the_declared_base_path() -> None:
    for path in PATHS:
        assert path.startswith(f"{API_BASE_PATH}/"), path


def test_every_path_template_is_declared_as_a_parameter() -> None:
    for path, _method, entry in operations():
        templated = set(re.findall(r"\{([^}]+)\}", path))
        declared = {
            cast(dict[str, object], parameter)["name"]
            for parameter in cast(list[object], entry["parameters"])
            if cast(dict[str, object], parameter)["in"] == "path"
        }
        assert templated == declared, path


def test_operation_ids_are_unique() -> None:
    ids = [cast(str, entry["operationId"]) for _path, _method, entry in operations()]
    assert sorted(ids) == sorted(set(ids))


def test_authentication_is_declared_where_it_is_required() -> None:
    by_id = {operation.operation_id: operation for operation in OPERATIONS}
    for _path, _method, entry in operations():
        operation = by_id[cast(str, entry["operationId"])]
        security = cast(list[object], entry["security"])
        assert bool(security) is operation.authenticated
        if operation.authenticated:
            assert security == [{"bearerAuth": []}]


def test_the_anonymous_catalog_stays_anonymous() -> None:
    # The catalog is readable without an account (SPEC-001); requiring a token
    # here would silently close the product's front door.
    for path, _method, entry in operations():
        if path.startswith(f"{API_BASE_PATH}/catalog") or path.startswith(
            f"{API_BASE_PATH}/health"
        ):
            assert entry["security"] == []


def test_every_error_response_carries_the_shared_envelope() -> None:
    # One error shape means the CLI parses cloud and local failures through one
    # reader (docs/contracts/cli-json.md).
    for path, _method, entry in operations():
        responses = cast(dict[str, dict[str, object]], entry["responses"])
        for status, response in sorted(responses.items()):
            if not status.startswith(("4", "5")):
                continue
            if status == "503" and "ReadinessResponse" in json.dumps(response):
                continue  # readiness reports its failing check, not an envelope
            assert "ErrorEnvelope" in json.dumps(response), f"{path} {status}"


def test_declared_error_statuses_come_from_the_registry() -> None:
    # A status invented per route would contradict the closed mapping the
    # registry owns.
    for path, _method, entry in operations():
        responses = cast(dict[str, dict[str, object]], entry["responses"])
        for status, response in sorted(responses.items()):
            described = cast(str, response.get("description", ""))
            for code in ERROR_CODES:
                if code in described:
                    assert http_status_for(code) == int(status), f"{path} {code}"


def test_a_mutation_declares_its_idempotency_and_precondition_headers() -> None:
    by_id = {operation.operation_id: operation for operation in OPERATIONS}
    for path, _method, entry in operations():
        operation = by_id[cast(str, entry["operationId"])]
        headers = {
            cast(dict[str, object], parameter)["name"]
            for parameter in cast(list[object], entry["parameters"])
            if cast(dict[str, object], parameter)["in"] == "header"
        }
        if operation.idempotent_mutation:
            assert "Idempotency-Key" in headers, path
        if operation.requires_precondition:
            assert "If-Match" in headers, path


def test_every_response_carries_the_correlation_header() -> None:
    for path, _method, entry in operations():
        success = cast(dict[str, dict[str, object]], entry["responses"])[
            str(by_operation_status(cast(str, entry["operationId"])))
        ]
        assert "X-Request-Id" in cast(dict[str, object], success["headers"]), path


def by_operation_status(operation_id: str) -> int:
    return next(item.status for item in OPERATIONS if item.operation_id == operation_id)


def test_a_search_declares_its_filters_as_query_parameters() -> None:
    entry = PATHS[f"{API_BASE_PATH}/catalog/components"]["get"]
    names = {
        cast(dict[str, object], parameter)["name"]
        for parameter in cast(list[object], entry["parameters"])
        if cast(dict[str, object], parameter)["in"] == "query"
    }
    assert {"q", "tags", "harness_id", "component_type", "cursor", "page_size"} <= names
    assert "include_experimental" in names


def test_the_document_passes_the_openapi_metaschema() -> None:
    # Every component being a valid 2020-12 schema is necessary and not
    # sufficient: the document around them is its own specification, and only
    # its own validator knows whether a route, parameter or response object is
    # well formed.
    validate_openapi(json.loads(render()))  # pyright: ignore[reportUnknownArgumentType]


def test_every_documented_example_validates_against_its_schema() -> None:
    # "Every documented example validates" is an acceptance criterion of #71.
    # An example is what a reader copies, so an invalid one is worse than none.
    from ai_stp_contracts.fixtures import case as fixture_case

    checked = 0
    for path, _method, entry in operations():
        media_blocks: list[dict[str, object]] = []
        request_body = cast(dict[str, object] | None, entry.get("requestBody"))
        if request_body is not None:
            content = cast(dict[str, dict[str, object]], request_body["content"])
            if "application/json" in content:
                media_blocks.append(content["application/json"])
        for response in cast(dict[str, dict[str, object]], entry["responses"]).values():
            content = cast(dict[str, dict[str, object]] | None, response.get("content"))
            # A streamed artifact has no JSON block and therefore no example to
            # validate; its content is bytes.
            if content is not None and "application/json" in content:
                media_blocks.append(content["application/json"])

        for media in media_blocks:
            examples = cast(dict[str, dict[str, object]] | None, media.get("examples"))
            if not examples:
                continue
            ref = cast(dict[str, str], media["schema"])["$ref"]
            schema = dict(SCHEMAS[ref.removeprefix("#/components/schemas/")])
            schema["$defs"] = SCHEMAS
            for case_id, example in sorted(examples.items()):
                assert fixture_case(case_id), case_id
                resolved = json.loads(
                    json.dumps(schema).replace("#/components/schemas/", "#/$defs/")
                )
                validator = Draft202012Validator(resolved)  # pyright: ignore[reportArgumentType]
                errors = sorted(
                    validator.iter_errors(example["value"]),  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
                    key=lambda error: list(error.path),
                )
                assert errors == [], (
                    f"{path} example {case_id}: {errors[0].message if errors else ''}"
                )
                checked += 1
    assert checked >= 15, f"only {checked} documented examples were checked"


def test_the_document_carries_an_example_for_every_operation_the_corpus_covers() -> None:
    # Schemas alone tell an implementer the shape; an example tells them what a
    # real answer looks like. #71 asks for both.
    from ai_stp_contracts.fixtures import cases_of_kind

    documented: set[str] = set()
    for _path, _method, entry in operations():
        for response in cast(dict[str, dict[str, object]], entry["responses"]).values():
            content = cast(dict[str, dict[str, object]] | None, response.get("content"))
            json_block = content.get("application/json") if content else None
            if json_block and json_block.get("examples"):
                documented.add(cast(str, entry["operationId"]))
    covered = {item.operation_id for item in cases_of_kind("positive")}
    assert covered <= documented, f"operations with a case but no example: {covered - documented}"


def test_the_pack_declares_no_route_outside_the_sprint_boundary() -> None:
    # #70 excluded publication, sync, grants, reports and provider operations.
    # #179 adds `/v1/sync/*`. #181 adds publications, grants, reports and staff.
    # Remaining excluded surface is harness provider operations (not OAuth
    # `{provider}`) and a free-standing publish/moderation alias namespace.
    # Checked on literal segments only: `{provider}` in the OAuth callback is
    # an identity provider, not a harness provider operation.
    forbidden = {
        "providers",
        "moderation",
        # free-standing publish alias is not used; the surface is /publications
        "publish",
    }
    for path in PATHS:
        literal = {
            segment.lower()
            for segment in path.split("/")
            if segment and not segment.startswith("{")
        }
        assert forbidden.isdisjoint(literal), path


def test_every_mutation_reports_its_operation_id() -> None:
    # docs/contracts/http-api.md: a mutating operation returns an operation id.
    # It travels as a header rather than in the body so a 204 or an error can
    # carry it too.
    by_id = {operation.operation_id: operation for operation in OPERATIONS}
    for path, _method, entry in operations():
        operation = by_id[cast(str, entry["operationId"])]
        if not operation.idempotent_mutation:
            continue
        success = cast(dict[str, dict[str, object]], entry["responses"])[str(operation.status)]
        assert "X-Operation-Id" in cast(dict[str, object], success["headers"]), path


def test_the_cli_boundary_never_leaks_into_the_http_document() -> None:
    # Two machine boundaries are published under one gate: `/v1` and the
    # agent-to-CLI contract. They are not the same surface, and a CLI payload
    # appearing in the OpenAPI document would tell the platform track to
    # implement a route that does not exist.
    for name, model in sorted(CLI_MODELS.items()):
        assert component_name(model) not in SCHEMAS, f"{name} is a CLI payload, not an HTTP one"
