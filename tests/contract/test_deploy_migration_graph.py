"""Deployment observes the same migration head as Alembic, including merges."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from deploy.verify_public import VerificationError, migration_head


def test_deployed_schema_inventory_matches_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert migration_head(Path("migrations/versions")) == scripts.get_current_head()


def test_merge_consumes_both_parent_heads(tmp_path: Path) -> None:
    graph = {"root": None, "left": "root", "right": "root", "merged": ("left", "right")}
    for revision, parent in graph.items():
        (tmp_path / f"{revision}.py").write_text(
            f"revision: str = {revision!r}\ndown_revision = {parent!r}\n", encoding="utf-8"
        )
    assert migration_head(tmp_path) == "merged"
    (tmp_path / "left.py").unlink()
    with pytest.raises(VerificationError, match="parents are absent"):
        migration_head(tmp_path)
