"""Everything a published distribution requires of this estate is also published.

The candidate builder checks that each declared internal dependency is pinned to
the exact version. It never asked the other question: whether every `ai-stp-*`
requirement of a publishable project is a project this estate publishes at all.

On 2026-09-02 that gap became real. `ai-stp-cli` gained a runtime dependency on
`ai-stp-sources`, a new workspace package, pinned exactly like the others —
while the publishable set, the publisher's package list and the per-project
upload workflow all still named five. `ai-stp-sources` has never existed on
PyPI. The already-published `0.0.15` predates the dependency and is unaffected,
but the next release would have shipped a `ai-stp-cli` wheel whose metadata
requires a distribution no index serves, so every `pip install ai-stp-cli`
would fail to resolve. Nothing before the install verification would have said
so, and that step runs after the bytes are built and the tag is cut.

A dependency edge is cheap to add and invisible until someone installs from the
index rather than from the workspace. So it is asked here, of the metadata, on
every run.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from release_scripts.build_candidate import INTERNAL_DEPENDENCIES, PUBLISHABLE

WORKFLOW = Path(".github/workflows/publish-pypi.yml")
OVERLAY = Path("release_scripts/public_overlay/.github/workflows/publish-pypi.yml")


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


def test_every_published_project_can_be_uploaded_by_the_workflow() -> None:
    """A project nobody can upload is published in name only.

    Each distribution has its own OIDC identity and its own environment, so a
    project absent from the workflow's choices has no way to reach the index.
    """
    workflow = (OVERLAY if OVERLAY.is_file() else WORKFLOW).read_text(encoding="utf-8")
    missing = [
        name
        for name in sorted(PUBLISHABLE)
        if f"          - {name[len('ai-stp-') :]}" not in workflow
    ]
    assert not missing, f"the upload workflow offers no choice for: {', '.join(missing)}"


def test_the_publisher_knows_every_published_project() -> None:
    """The release driver's list and the builder's set are one set, not two."""
    from release_scripts.publish_pypi import PACKAGES

    assert {f"ai-stp-{name}" for name in PACKAGES} == set(PUBLISHABLE)
