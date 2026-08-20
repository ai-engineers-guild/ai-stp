"""Golden canonicalization vectors: language-neutral fixtures for every port."""

import json
from pathlib import Path
from typing import cast

import pytest

from ai_stp_foundation import canonize, digest_bytes
from ai_stp_foundation.canonical import JsonValue

VECTORS_DIR = Path(__file__).parents[1] / "golden" / "canonical"
VECTOR_PATHS = sorted(VECTORS_DIR.glob("*.json"))


def test_vector_corpus_is_present() -> None:
    assert len(VECTOR_PATHS) >= 5


@pytest.mark.parametrize("path", VECTOR_PATHS, ids=lambda path: path.stem)
def test_golden_vector(path: Path) -> None:
    vector = cast(dict[str, JsonValue], json.loads(path.read_text(encoding="utf-8")))
    value = vector["value"]
    expected_canonical = cast(str, vector["canonical"])
    canonical = canonize(value)
    assert canonical.decode("utf-8") == expected_canonical
    digests = cast(dict[str, str], vector["digests"])
    for domain, expected in digests.items():
        assert digest_bytes(domain, canonical) == expected
