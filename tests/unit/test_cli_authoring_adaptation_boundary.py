"""Authoring trees freeze into canonical adaptations at compose/release."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.commands import setup_compose as compose_commands
from ai_stp_cli.commands import setup_scaffold as setup_scaffold_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    authoring,
    bundle,
    component_passports,
    components,
    setup_compose,
    versions,
)
from ai_stp_cli.local.composition import rule_for
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.authoring import AUTHORING_DRAFT_MARKER
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.provider_surfaces import provider_surface
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_sources.local import resolve_local
from ai_stp_sources.models import PathIntent

COMMIT = "a" * 40
CREATED = "2026-09-04T12:00:00.000Z"


def test_a_draft_setup_scaffold_is_refused_until_todo_markers_are_replaced(
    tmp_path: Path,
) -> None:
    parameters = {
        "name": "review-pack",
        "harness": "codex",
        "output": str(tmp_path / "review-pack"),
        "components": "skill:review-kit",
    }
    plan = setup_scaffold_commands.plan(parameters).payload
    setup_scaffold_commands.apply({**parameters, "expected-plan-digest": plan.plan_digest})
    manifest = tmp_path / "review-pack" / "setup.json"
    with pytest.raises(CliFailure, match="invalid"):
        compose_commands.plan({"manifest": str(manifest), "root": str(tmp_path / "review-pack")})
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["tags"] = ["quality"]
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CliFailure, match="TODO\\(ai-stp-scaffold\\)"):
        compose_commands.plan({"manifest": str(manifest), "root": str(tmp_path / "review-pack")})


def test_completing_a_setup_scaffold_freezes_a_canonical_adaptation_and_v2_surface(
    tmp_path: Path,
) -> None:
    parameters = {
        "name": "review-pack",
        "harness": "codex",
        "output": str(tmp_path / "review-pack"),
        "components": "skill:review-kit",
    }
    plan = setup_scaffold_commands.plan(parameters).payload
    setup_scaffold_commands.apply({**parameters, "expected-plan-digest": plan.plan_digest})
    root = tmp_path / "review-pack"
    document = json.loads((root / "setup.json").read_text(encoding="utf-8"))
    document["description"] = "A completed review pack."
    document["tags"] = ["quality"]
    document["components"][0]["description"] = "A completed review skill."
    document["components"][0]["license_spdx"] = "MIT"
    document["components"][0]["redistribution_allowed"] = True
    (root / "setup.json").write_text(json.dumps(document), encoding="utf-8")

    manifest = setup_compose.parse_manifest(document)
    intent = PathIntent(relative_path=str(manifest.components[0].source["relative_path"]))
    snapshot = resolve_local(intent, local_root=root)
    resolved = setup_compose.compose(
        manifest=manifest,
        setup_id="setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        publisher_id="account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        created_at=CREATED,
        snapshots=[(manifest.components[0], snapshot)],
        catalog=[],
    )
    embedded = cast(list[object], resolved.frozen.document["embedded"])
    record = cast(dict[str, object], embedded[0])
    passport = ComponentVersionPassport.model_validate(record["passport"])
    adaptation = passport.adaptations[0]
    scope = adaptation.scope_adaptations[0]
    surface = provider_surface("codex", "global")
    skill_rule = rule_for("skill", "codex")
    assert skill_rule is not None
    assert adaptation.harness_id == "codex"
    assert adaptation.implementation_mode == "native"
    assert scope.required_surface.profile_id == surface.profile_id
    assert scope.required_surface.profile_digest == surface.profile_digest
    assert scope.required_surface.bundle_format == "ai-stp-bundle/2"
    assert all(
        member.path == skill_rule.relative or member.path.startswith(f"{skill_rule.relative}/")
        for member in scope.members
    )
    setup_passport: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "setup",
        "stable_id": "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    }
    compiled = bundle.compile_bundle(
        tuple(bundle.Source(member.path, b"skill", passport.stable_id) for member in scope.members),
        setup_stable_id="setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        setup_version="0.1",
        setup_digest=digest_canonical("ai-stp:passport:v1", setup_passport),
        harness_id="codex",
        declared_paths=frozenset(member.path for member in scope.members),
        setup_passport=setup_passport,
        composition_report={"chosen": []},
        conversion_report={"entries": []},
        input_digest="sha256:" + "c" * 64,
        target_scope="global",
        bundle_format=bundle.BUNDLE_FORMAT_V2,
        projection_profile=bundle.ProjectionProfileBinding(
            surface.profile_id, surface.profile_digest, "global"
        ),
        adaptation_bindings=(
            bundle.ComponentAdaptationBinding(
                stable_id=passport.stable_id,
                version=passport.version,
                passport_digest="sha256:" + "1" * 64,
                adaptation_id=adaptation.adaptation_id,
                projection_artifact_digest=scope.projection_artifact.digest,
                projection_artifact_size=scope.projection_artifact.size_bytes,
                provider_component_kind=scope.provider_component_kind,
                projection_kind=scope.projection_kind,
                member_paths=tuple(member.path for member in scope.members),
            ),
        ),
    )
    assert compiled.compiled, compiled.refusals


def test_adopting_a_scaffold_projection_releases_an_adaptation_for_the_provider_surface(
    tmp_path: Path,
) -> None:
    output = tmp_path / "review-kit"
    plan, files = authoring.scaffold_plan(
        component_type="skill",
        name="review-kit",
        language="none",
        harness_variant="codex",
        output=output,
    )
    authoring.apply_scaffold(plan, files, expected_digest=plan.plan_digest)
    projection = output / "projections" / "codex"
    home = tmp_path / "empty-home"
    home.mkdir()
    found = components.discover(project=projection, environment={"HOME": str(home)})
    skill = next(item for item in found if item.component_type == "skill")
    with closing(open_registry(configured_path(), create=True)) as connection:
        stored = components.adopt(connection, skill, device_id="device_test")
        with pytest.raises(CliFailure, match="not ready to release"):
            component_passports.materialize_version_passport(
                connection, stored.stable_id, "1.0", device_id="device_test", at=CREATED
            )
        component_passports.update(
            connection,
            stored.stable_id,
            stored.revision_id,
            ComponentPassportPatch.model_validate(
                {
                    "name": "review-kit",
                    "description": "A completed review skill.",
                    "tags": ["quality"],
                    "source": {
                        "repository": "https://github.com/example/review-kit",
                        "commit": COMMIT,
                        "path": "skills/review-kit",
                    },
                    "harness_id": "codex",
                    "component_type": "skill",
                    "projection_kind": "native_files",
                    "license": {"spdx_id": "MIT", "redistribution_allowed": True},
                }
            ),
            device_id="device_test",
        )
        passport, revision_id = component_passports.materialize_version_passport(
            connection, stored.stable_id, "1.0", device_id="device_test", at=CREATED
        )
        versions.record(
            connection,
            stable_id=stored.stable_id,
            version="1.0",
            passport_digest=digest_canonical(
                "ai-stp:passport:v1", cast(JsonValue, passport.model_dump(mode="json"))
            ),
            revision_id=revision_id,
            at=CREATED,
        )
    adaptation = passport.adaptations[0]
    scope = adaptation.scope_adaptations[0]
    surface = provider_surface("codex", scope.scope)
    assert AUTHORING_DRAFT_MARKER not in passport.description
    assert adaptation.harness_id == "codex"
    assert scope.required_surface.profile_id == surface.profile_id
    assert scope.required_surface.bundle_format == surface.bundle_format
    assert revision_id
