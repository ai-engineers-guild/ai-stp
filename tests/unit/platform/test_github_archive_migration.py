"""Forward migration 0024 drops only derived GitHub archive caches."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "0024_drop_github_archive_cache.py"
)


def test_migration_0024_touches_only_derived_archive_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    upgrade, downgrade = text.split("def downgrade")
    assert "github_archive_latest" in upgrade
    assert "github_archive_history" in upgrade
    assert "drop_table" in upgrade
    assert "catalog_metadata" not in upgrade
    assert "account" not in upgrade
    assert "create_table" in downgrade
    assert "github_archive_latest" in downgrade
