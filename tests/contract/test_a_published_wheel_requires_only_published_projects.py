"""Legacy Python package metadata retains a complete internal dependency closure."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from release_scripts.build_candidate import INTERNAL_DEPENDENCIES, PUBLISHABLE


def _requirements(manifest: Path) -> list[str]:
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    project = document.get("project", {})
    return [str(item) for item in project.get("dependencies", [])]


def _distribution(requirement: str) -> str:
    """The distribution a requirement names, without its version or markers."""
    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", "[", " "):
        requirement = requirement.split(separator)[0]
    return requirement.strip()


@pytest.mark.parametrize("name", sorted(PUBLISHABLE))
def test_every_estate_requirement_of_a_published_project_is_itself_published(
    name: str,
) -> None:
    """A wheel on the index may only require distributions the index will serve."""
    unpublished = sorted(
        {
            distribution
            for requirement in _requirements(PUBLISHABLE[name])
            if (distribution := _distribution(requirement)).startswith("ai-stp-")
            and distribution not in PUBLISHABLE
        }
    )
    assert not unpublished, (
        f"{name} requires {', '.join(unpublished)}, which this estate does not publish: "
        "an install from the index would fail to resolve"
    )


@pytest.mark.parametrize("name", sorted(PUBLISHABLE))
def test_the_declared_dependency_map_matches_the_manifest(name: str) -> None:
    """The map the builder enforces pins against is the manifest's own set.

    A dependency missing from the map is never checked for its exact pin, which
    is how one arrived unnoticed.
    """
    from_manifest = {
        distribution
        for requirement in _requirements(PUBLISHABLE[name])
        if (distribution := _distribution(requirement)).startswith("ai-stp-")
    }
    assert from_manifest == set(INTERNAL_DEPENDENCIES[name])


def test_the_publisher_knows_every_published_project() -> None:
    """The release driver's list and the builder's set are one set, not two."""
    from release_scripts.publish_pypi import PACKAGES

    assert {f"ai-stp-{name}" for name in PACKAGES} == set(PUBLISHABLE)
