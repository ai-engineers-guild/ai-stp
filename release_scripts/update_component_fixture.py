"""Regenerate component-version bodies in the HTTP contract corpus."""

import json
from pathlib import Path
from typing import cast

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.catalog_seed import FIXTURE_COMPONENT_ID, seed_corpus

TARGET = Path("packages/contracts/src/ai_stp_contracts/fixtures/v1/catalog.json")


def main() -> None:
    document = json.loads(TARGET.read_text(encoding="utf-8"))
    current = next(
        passport
        for kind, passport, _published, _digest in seed_corpus()
        if kind == "component"
        and passport["stable_id"] == FIXTURE_COMPONENT_ID
        and passport["version"] == "1.2"
    )
    for raw in document["cases"]:
        body = raw.get("body")
        if raw.get("operation_id") != "readComponentVersion" or not isinstance(body, dict):
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
    TARGET.write_bytes(json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")


if __name__ == "__main__":
    main()
