"""A10/A11: coordinated standard family is not envelope v1 and not protocol v3."""

from __future__ import annotations

import json
from pathlib import Path

from ai_stp_contracts.authoring import ComponentTemplateDescriptor
from ai_stp_contracts.schemas import CLI_MODELS, HTTP_MODELS, current_inventory
from ai_stp_contracts.standard import (
    STANDARD_FAMILY,
    classify,
)
from ai_stp_foundation.schemas import schema_id

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_V3 = ROOT / "tests" / "golden" / "cli" / "component-scaffold-v3.json"
HEALTH_FIXTURE = (
    ROOT / "packages" / "contracts" / "src" / "ai_stp_contracts" / "fixtures" / "v1" / "health.json"
)
KIT_IDENTITY = ROOT / "provider-kit" / "v3" / "KIT-IDENTITY.json"


def test_inventory_lists_every_exported_schema_and_the_protocol_axes() -> None:
    inventory = current_inventory()
    assert inventory.standard_family == "ai-stp-standard/1"
    assert inventory.contract_digest.startswith("sha256:")
    axis_names = {axis.name for axis in inventory.axes}
    assert axis_names == {
        "standard_family",
        "http_api",
        "envelope",
        "provider_protocol",
        "kit_protocol",
        "component_generator",
        "setup_generator",
    }
    http_ids = {member.identity for member in inventory.members if member.axis == "http_schema"}
    exported_ids = {
        member.identity for member in inventory.members if member.axis == "exported_schema"
    }
    assert http_ids == {schema_id(name) for name in HTTP_MODELS}
    from ai_stp_contracts.schemas import EXPORTED_MODELS

    assert exported_ids == {schema_id(name) for name in EXPORTED_MODELS if name not in HTTP_MODELS}
    assert "cli-standard-inventory" not in HTTP_MODELS
    assert "cli-standard-inventory" in CLI_MODELS


def test_envelope_schema_version_one_is_not_the_standard_family() -> None:
    body = json.loads(HEALTH_FIXTURE.read_text(encoding="utf-8"))["cases"][0]["body"]
    classified = classify(body)
    assert classified.axis == "envelope"
    assert classified.identity == "schema_version:1"
    assert classified.axis != "standard_family"


def test_kit_protocol_three_is_not_the_standard_family() -> None:
    kit = json.loads(KIT_IDENTITY.read_text(encoding="utf-8"))
    classified = classify(kit)
    assert classified.axis == "kit_protocol"
    assert classified.identity == "3"
    assert classified.current is True
    assert classified.axis != "standard_family"


def test_a_naive_protocol_v3_to_v1_rename_does_not_become_envelope_or_family() -> None:
    renamed = {"protocol_version": 1, "harness_id": "claude"}
    classified = classify(renamed)
    assert classified.axis == "provider_protocol"
    assert classified.identity == "1"
    assert classified.current is False
    envelope = classify({"schema_version": 1, "status": "alive"})
    family = classify({"standard_family": STANDARD_FAMILY})
    assert {classified.axis, envelope.axis, family.axis} == {
        "provider_protocol",
        "envelope",
        "standard_family",
    }


def test_historical_scaffold_without_standard_family_stays_a_generator() -> None:
    golden = json.loads(HISTORICAL_V3.read_text(encoding="utf-8"))
    classified = classify(golden)
    assert classified.axis == "component_generator"
    assert classified.identity == "component-scaffold/3"
    assert classified.current is False
    ComponentTemplateDescriptor.model_validate(
        {
            "schema_version": 1,
            "template_version": "component-scaffold/3",
            "generator_version": "ai-stp/3",
            "component_type": "skill",
            "language": "none",
            "harness_variant": "portable",
            "executable": False,
        }
    )


def test_assigning_the_family_to_old_v1_bytes_is_refused_as_a_mix() -> None:
    mixed = {
        "schema_version": 1,
        "status": "alive",
        "standard_family": "1",
    }
    classified = classify(mixed)
    assert classified.axis == "standard_family"
    assert classified.current is False
    assert classified.problems


def test_current_family_document_classifies_as_the_family() -> None:
    inventory = current_inventory()
    classified = classify(inventory.model_dump(mode="json"))
    assert classified.axis == "standard_family"
    assert classified.identity == "ai-stp-standard/1"
    assert classified.current is True
    assert classified.problems == ()


def test_inventory_digest_is_stable_for_the_same_members() -> None:
    first = current_inventory()
    second = current_inventory()
    assert first.contract_digest == second.contract_digest


def test_http_and_exported_schema_axes_do_not_overlap() -> None:
    inventory = current_inventory()
    http_ids = {m.identity for m in inventory.members if m.axis == "http_schema"}
    exported_ids = {m.identity for m in inventory.members if m.axis == "exported_schema"}
    assert http_ids.isdisjoint(exported_ids)
    assert schema_id("cli-standard-inventory") in exported_ids
