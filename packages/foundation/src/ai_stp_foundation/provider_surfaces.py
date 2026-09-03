"""Exact released provider projection profiles used by the first alpha contract."""

from typing import Final, NamedTuple

from ai_stp_foundation.harnesses import HarnessId


class ProviderSurfaceIdentity(NamedTuple):
    profile_id: str
    profile_digest: str
    bundle_format: str = "ai-stp-bundle/1"


PROVIDER_SURFACES: Final[dict[HarnessId, ProviderSurfaceIdentity]] = {
    "antigravity": ProviderSurfaceIdentity(
        "antigravity/native-files/1",
        "sha256:523d4da484f3c1022d72eec24a110488fffbff312746556da6f066bd12843377",
    ),
    "claude-code": ProviderSurfaceIdentity(
        "claude/native-and-marketplace/1",
        "sha256:d0fb520ede8275d6016e46155dd19f26ee83c3d7cc19fa6a41a53ac15d033976",
    ),
    "codex": ProviderSurfaceIdentity(
        "codex/native-files/1",
        "sha256:dec511eaf959c597a727d1063c8184cc84ee4982f74713c15c9f86c6b1eb8cd7",
    ),
    "cursor": ProviderSurfaceIdentity(
        "cursor/native-and-plugins/2",
        "sha256:8e5c294bb4727c972602333af03f006e3826fc23b38ebaba007298171b0db7f1",
    ),
    "grok-build": ProviderSurfaceIdentity(
        "grok/native-and-plugins/1",
        "sha256:9c7bcb866a5c8070729b57f77e81f11a7a1a25a744fa785fd6cbd747c5db6f54",
    ),
    "opencode": ProviderSurfaceIdentity(
        "opencode/native-files/1",
        "sha256:6b89633299236de4f2b6a7d0a712fc67813a1213790241ef3a2573251641e489",
    ),
    "pi": ProviderSurfaceIdentity(
        "pi/native-files/2",
        "sha256:eb0c48c5a09ab76e86018d0031d17664a6bdfc8dc5bfcf7b8470d04b52686ce1",
    ),
}
