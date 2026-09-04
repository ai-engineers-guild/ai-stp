"""Current component-adaptation fields for tests that exercise other boundaries."""

from typing import cast

from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import seal_adaptation


def adaptation_fields(
    *,
    digest: str,
    size: int,
    harness_id: str = "claude-code",
    component_type: str = "skill",
    path: str = "skills/demo/SKILL.md",
) -> dict[str, object]:
    adaptation = seal_adaptation(
        cast(
            dict[str, JsonValue],
            {
                "harness_id": harness_id,
                "implementation_mode": "native",
                "source_artifact": None,
                "transform": None,
                "logical_component_type": component_type,
                "scope_adaptations": [
                    {
                        "scope": "global",
                        "projection_format": "ai-stp-adaptation-projection/1",
                        "projection_artifact": {"digest": digest, "size_bytes": size},
                        "provider_component_kind": component_type,
                        "projection_kind": "native_files",
                        "required_surface": {
                            "profile_id": f"{harness_id}/test/1",
                            "profile_digest": digest,
                            "bundle_format": "ai-stp-bundle/1",
                        },
                        "members": [
                            {
                                "path": path,
                                "object_type": "file",
                                "mode": 420,
                                "content_artifact": {"digest": digest, "size_bytes": size},
                                "native_ids": ["demo"],
                                "content_format": "application/octet-stream",
                                "ownership": "whole",
                                "write_semantics": "replace",
                                "withdrawal_semantics": "remove_path",
                            }
                        ],
                        "technical_support": "experimental",
                        "technical_support_reason": "test fixture",
                    }
                ],
            },
        )
    )
    return {
        "origin_harness_id": harness_id,
        "adaptations": [adaptation.model_dump(mode="json")],
    }
