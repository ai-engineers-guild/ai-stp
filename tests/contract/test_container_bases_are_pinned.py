"""A base image named by tag is not pinned, and a republished tag leaves no trace.

`Dockerfile` already carried the argument — the `uv` line explains that `:0.9`
moves, that two builds of one commit could resolve different releases, and that
`SPEC-024` requires the image to be reproducible from the commit. It was applied
to `uv` and not to the `FROM python:3.12-slim` two lines above it, and not at
all in `Dockerfile.user-docs`.

The asymmetry that makes this worth a check rather than a habit: a **stale** pin
announces itself — the version reads as going backwards, and dependabot opens a
pull request. A **republished tag** announces nothing. The digest under it
changes, every build after it differs from every build before it, and nothing in
the tree records that anything happened.

Two claims here, and the second is the one a single-file review misses.
"""

from __future__ import annotations

import re
from pathlib import Path

#: `FROM <image>:<tag>` where the image names a registry rather than an earlier
#: stage. A stage reference (`FROM base AS api`) carries no tag and is skipped
#: by the pattern itself.
_FROM = re.compile(
    r"^FROM\s+(?P<ref>[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+)(?P<digest>@sha256:[0-9a-f]{64})?"
)

#: Compose services in the file production actually runs. `docker-compose.dev.yml`
#: is deliberately absent: a developer pulling a newer `postgres:16` is the point
#: of a dev stack, and pinning it would mean a digest bump before every local
#: `up`. The exemption is the file, named, rather than a rule about tags.
_PINNED_COMPOSE = ("docker-compose.prod.yml",)

_IMAGE = re.compile(r"^\s+image:\s+(?P<ref>[^\s@]+)(?P<digest>@sha256:[0-9a-f]{64})?\s*$")


def _dockerfiles() -> list[Path]:
    return sorted(Path().glob("Dockerfile*"))


def test_every_container_base_is_pinned_by_digest() -> None:
    unpinned: list[str] = []
    for path in _dockerfiles():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = _FROM.match(line)
            if found and not found.group("digest"):
                unpinned.append(f"{path}:{number} {found.group('ref')}")
    assert not unpinned, unpinned


def test_production_compose_images_are_pinned_by_digest() -> None:
    unpinned: list[str] = []
    for name in _PINNED_COMPOSE:
        path = Path(name)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = _IMAGE.match(line)
            if found is None or found.group("digest"):
                continue
            # A service whose image comes from a required variable is pinned by
            # whoever sets it, and the compose file refuses to start without it.
            if found.group("ref").startswith("${"):
                continue
            unpinned.append(f"{path}:{number} {found.group('ref')}")
    assert not unpinned, unpinned


def test_one_image_and_tag_resolves_to_one_digest_across_the_tree() -> None:
    """Per-file pinning is reproducible per file and still builds on two bases.

    `Dockerfile.worker-safety` pinned one republish of `python:3.12-slim` and
    `Dockerfile` pinned another. Each was internally reproducible; together they
    meant the platform image and the scanner image ran different interpreters,
    with nothing anywhere saying so.
    """
    seen: dict[str, set[str]] = {}
    for path in _dockerfiles():
        for line in path.read_text(encoding="utf-8").splitlines():
            found = _FROM.match(line)
            if found and found.group("digest"):
                seen.setdefault(found.group("ref"), set()).add(found.group("digest"))
    split = {ref: sorted(digests) for ref, digests in seen.items() if len(digests) > 1}
    assert not split, split
