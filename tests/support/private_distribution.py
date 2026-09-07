"""Sealed private component and setup fixtures with real native projection bytes."""

from typing import cast

from ai_stp_contracts.first_party import versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports import seal_adaptation
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.projections import build_projection
from ai_stp_passports.versions import (
    ComponentVersionPassport,
    ScopeAdaptation,
    SetupVersionPassport,
)
from ai_stp_sources.definition import freeze_setup_definition


def component_version(
    owner: str, stable_id: str, version: str
) -> tuple[dict[str, JsonValue], bytes]:
    base = next(
        item
        for item in versions()
        if isinstance(item.passport, ComponentVersionPassport)
        and item.passport.component_type == "instruction"
        and item.passport.origin_harness_id == "claude-code"
    )
    raw = cast(dict[str, JsonValue], base.passport.model_dump(mode="json"))
    assert isinstance(base.passport, ComponentVersionPassport)
    adaptation = base.passport.adaptations[0]
    scope_raw = adaptation.scope_adaptations[0].model_dump(mode="json")
    content = b"Prefer small focused changes and explain their purpose.\n"
    member = scope_raw["members"][0]
    member["content_artifact"] = {
        "digest": digest_bytes("ai-stp:artifact:v1", content),
        "size_bytes": len(content),
    }
    scope_raw["members"] = [member]
    payload = build_projection(ScopeAdaptation.model_validate(scope_raw), {member["path"]: content})
    scope_raw["projection_artifact"] = {
        "digest": digest_bytes("ai-stp:artifact:v1", payload),
        "size_bytes": len(payload),
    }
    adaptation_raw = adaptation.model_dump(mode="json")
    adaptation_raw["scope_adaptations"] = [scope_raw]
    raw.update(
        stable_id=stable_id,
        owner_id=owner,
        version=version,
        visibility="private",
        adaptations=[seal_adaptation(adaptation_raw).model_dump(mode="json")],
        artifact=cast(JsonValue, scope_raw["projection_artifact"]),
    )
    raw["revision_id"] = derive_revision_id(raw)
    ComponentVersionPassport.model_validate(raw)
    return raw, payload


def setup_version(
    owner: str, stable_id: str, version: str, component: dict[str, JsonValue]
) -> tuple[dict[str, JsonValue], bytes]:
    base = next(
        item
        for item in versions()
        if isinstance(item.passport, SetupVersionPassport)
        and item.passport.harness_id == "claude-code"
        and item.passport.posture == "minimal"
    )
    raw = cast(dict[str, JsonValue], base.passport.model_dump(mode="json"))
    ref = ComponentRef(
        stable_id=str(component["stable_id"]),
        version=str(component["version"]),
        passport_digest=digest_canonical("ai-stp:passport:v1", component),
    )
    frozen = freeze_setup_definition(
        setup_id=stable_id,
        version=version,
        harness_id="claude-code",
        input_digest=digest_canonical("ai-stp:passport:v1", component),
        publisher_id=owner,
        created_at=str(raw["created_at"]),
        catalog_members=(ref,),
        embedded_members=(),
    )
    raw.update(
        stable_id=stable_id,
        owner_id=owner,
        version=version,
        visibility="private",
        components=[ref.model_dump(mode="json")],
        artifact={
            "digest": digest_bytes("ai-stp:artifact:v1", frozen.payload),
            "size_bytes": len(frozen.payload),
        },
    )
    raw["revision_id"] = derive_revision_id(raw)
    SetupVersionPassport.model_validate(raw)
    return raw, frozen.payload
