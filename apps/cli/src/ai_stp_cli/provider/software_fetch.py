"""Fetch the program bytes a provider plan already named.

The provider never downloads: `download` is not one of the kit's seven commands,
and both commands that could have carried it are `network_requirement: none`. So
the consumer fetches, and it fetches something whose identity was fixed offline —
`sha256` and `byte_length` come from a plan bound into `plan_digest` before the
network was touched.

Nothing here is a second downloader. `toolchain/install.py` already holds a
hardened one — a cache named by its own digest, verification before anything is
unpacked, ownership tracking — and its guarantees are the same guarantees a
program archive needs. What is not reused is unpacking and activation: the
provider does both, and reimplementing them here would be a second opinion about
a layout that is not ours.
"""

from __future__ import annotations

from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider.operation_v3 import SoftwareArtifact
from ai_stp_cli.toolchain import install


def fetch(artifact: SoftwareArtifact, *, transport: object | None = None) -> Path:
    """Fetch one artifact, verify it against the plan, and return its cached path.

    The digest is the trust anchor and the URL is only a hint: bytes that do not
    match are refused whatever host served them. The length is checked as well,
    and separately — a truncated response can still be a prefix nobody digested,
    and reporting "wrong size" costs less to read than "wrong digest".

    A cached entry is preferred and re-verified on the way out. The cache is
    named by the digest, so a hit that reads back different bytes is impossible
    rather than merely unlikely.
    """
    cached = install.cache_dir() / install.digest_name(artifact.sha256)
    if cached.exists():
        # Re-verified on the way out by `cached_bytes`, because the file has
        # been at rest on a disk this CLI does not control since it was written.
        install.cached_bytes(artifact.sha256)
        return cached
    content = install.download(
        artifact.url,
        transport=transport,
        timeout=install.download_deadline(artifact.byte_length),
    )
    if len(content) != artifact.byte_length:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the fetched program is not the length its plan stated",
            details={
                "url": artifact.url,
                "expected": str(artifact.byte_length),
                "observed": str(len(content)),
            },
        )
    # Verifies before it stores: an unverified artifact never reaches a cache
    # that later reads are allowed to trust.
    install.verify(content, artifact.sha256)
    return install.remember(content, artifact.sha256)
