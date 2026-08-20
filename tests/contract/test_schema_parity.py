"""Generated schemas in schemas/v1 match their models byte for byte (REQ-1509)."""

from pathlib import Path

from ai_stp_contracts.schemas import EXPORTED_MODELS
from ai_stp_foundation.schemas import check, render

SCHEMAS_DIR = Path(__file__).parents[2] / "schemas" / "v1"


def test_committed_schemas_match_generator() -> None:
    assert check(SCHEMAS_DIR, EXPORTED_MODELS) == []


def test_every_exported_model_has_a_schema_file() -> None:
    rendered = render(EXPORTED_MODELS)
    assert sorted(rendered) == sorted(f"{name}.schema.json" for name in EXPORTED_MODELS)


def test_rendering_is_deterministic() -> None:
    assert render(EXPORTED_MODELS) == render(EXPORTED_MODELS)
