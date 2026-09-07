from pathlib import Path

from ai_stp_passports.versions import COMPONENT_TYPES


def test_forward_migration_matches_canonical_component_taxonomy() -> None:
    source = Path("migrations/versions/0050_exact_public_targets_and_cli_taxonomy.py").read_text()
    assert all(f'    "{component}",' in source for component in COMPONENT_TYPES)
    assert "'marketplace'" not in source


def test_forward_migration_keeps_stale_state_and_does_not_edit_0033() -> None:
    source = Path("migrations/versions/0050_exact_public_targets_and_cli_taxonomy.py").read_text()
    assert "'stale'" in source
    assert "0033" not in source
