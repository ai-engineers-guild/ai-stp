"""One literal HarnessBundle oracle shared by Linux and macOS (`#167`)."""

import base64
import json
from pathlib import Path
from typing import cast

from ai_stp_cli.local import bundle
from ai_stp_foundation.canonical import JsonValue, canonize

GOLDEN = Path(__file__).parents[1] / "golden" / "bundle"
INPUT = GOLDEN / "cross-platform-v1-input.json"
MANIFEST = GOLDEN / "cross-platform-v1-manifest.json"


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _integer(value: object) -> int:
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def test_canonical_bundle_matches_the_cross_platform_byte_oracle() -> None:
    fixture = _object(json.loads(INPUT.read_text(encoding="utf-8")))
    build = _object(fixture["build"])
    held_sources = fixture["sources"]
    assert isinstance(held_sources, list)
    raw_sources = cast(list[object], held_sources)

    sources = tuple(
        bundle.Source(
            path=str(source["path"]),
            content=base64.b64decode(str(source["content_base64"]), validate=True),
            owner=str(source["owner"]),
            mode=_integer(source["mode"]),
        )
        for held in raw_sources
        for source in (_object(held),)
    )
    compiled = bundle.compile_bundle(
        sources,
        setup_stable_id=str(build["setup_stable_id"]),
        setup_version=str(build["setup_version"]),
        setup_digest=str(build["setup_digest"]),
        harness_id=str(build["harness_id"]),
        declared_paths=frozenset(str(item) for item in cast(list[object], build["declared_paths"])),
        setup_passport=cast(dict[str, JsonValue], build["setup_passport"]),
        composition_report=cast(dict[str, JsonValue], build["composition_report"]),
        conversion_report=cast(dict[str, JsonValue], build["conversion_report"]),
        input_digest=str(build["input_digest"]),
    )

    assert compiled.compiled
    assert compiled.digest == fixture["expected_digest"]
    assert compiled.artifact_digest == fixture["expected_artifact_digest"]
    assert compiled.archive == base64.b64decode(
        str(fixture["expected_archive_base64"]), validate=True
    )
    assert canonize(compiled.manifest) == MANIFEST.read_bytes().removesuffix(b"\n")
