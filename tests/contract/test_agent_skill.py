"""Self-contained current projections; native command validation runs against the real CLI.

The native executable gate validates every documented command/flag against its
live machine registry. This suite proves packaging and generation independently
without requiring a Rust build in backend-only jobs.
"""

import re
import shutil
from pathlib import Path

import pytest
from docs_scripts import skill_projections

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "skills" / "canonical" / "ai-stp"
INVOCATION = re.compile(r"`(ai-stp [^`\n]+)`")


@pytest.mark.parametrize("projection", skill_projections.TARGETS, ids=lambda item: item.harness_id)
def test_repository_projection_is_self_contained_and_current(
    projection: skill_projections.Projection, tmp_path: Path
) -> None:
    source = skill_projections.PROJECTIONS / projection.directory
    assert (source / projection.filename).read_text(encoding="utf-8") == skill_projections.render(
        projection
    )
    delivered = tmp_path / "ai-stp"
    shutil.copytree(source, delivered)
    for document in delivered.rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            destination = (document.parent / target.split("#", 1)[0]).resolve()
            assert destination.is_relative_to(delivered), (document, target)
            assert destination.is_file(), (document, target)


def test_every_supported_harness_has_one_generated_projection() -> None:
    from ai_stp_foundation.harnesses import HARNESS_IDS

    assert {projection.harness_id for projection in skill_projections.TARGETS} == set(HARNESS_IDS)
    assert skill_projections.check() == []
    before = {path: path.read_bytes() for path in skill_projections.projection_files()}
    skill_projections.write()
    assert before == {path: path.read_bytes() for path in before}


def test_localized_playbooks_keep_the_same_command_references() -> None:
    for path in (PACKAGE / "references").glob("*.md"):
        translated = PACKAGE / "locale" / "ru" / "references" / path.name
        assert set(INVOCATION.findall(path.read_text(encoding="utf-8"))) == set(
            INVOCATION.findall(translated.read_text(encoding="utf-8"))
        )
