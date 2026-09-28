"""Regenerate component-version bodies in the HTTP contract corpus."""

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from tests.support.catalog_seed import FIXTURE_COMPONENT_ID, seed_corpus

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import derive_revision_id

TARGET = Path("packages/contracts/src/ai_stp_contracts/fixtures/v1/catalog.json")


def render() -> bytes:
    document = json.loads(TARGET.read_text(encoding="utf-8"))
    current = next(
        passport
        for kind, passport, _published, _digest in seed_corpus()
        if kind == "component"
        and passport["stable_id"] == FIXTURE_COMPONENT_ID
        and passport["version"] == "1.2"
    )
    version_digests = {
        passport["version"]: digest
        for kind, passport, _published, digest in seed_corpus()
        if kind == "component" and passport["stable_id"] == FIXTURE_COMPONENT_ID
    }
    for raw in document["cases"]:
        body = raw.get("body")
        if not isinstance(body, dict):
            continue
        if raw.get("operation_id") == "readComponent":
            for entry in body.get("versions", []):
                if isinstance(entry, dict) and entry.get("version") in version_digests:
                    entry["passport_digest"] = version_digests[entry["version"]]
            continue
        if raw.get("operation_id") != "readComponentVersion":
            continue
        previous = body.get("passport")
        if not isinstance(previous, dict):
            continue
        passport = dict(current)
        passport["visibility"] = previous.get("visibility", "public")
        passport["revision_id"] = derive_revision_id(passport)
        body["passport"] = passport
        body["passport_digest"] = digest_bytes(
            "ai-stp:passport:v1", canonize(cast(JsonValue, passport))
        )
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed corpus against a fresh render, writing nothing",
    )
    arguments = parser.parse_args()
    rendered = render()
    if arguments.check:
        if not TARGET.is_file() or TARGET.read_bytes() != rendered:
            print(
                f"contract corpus drifted from its seed source: {TARGET}; "
                "run release_scripts/update_component_fixture.py",
                file=sys.stderr,
            )
            return 1
        return 0
    TARGET.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
