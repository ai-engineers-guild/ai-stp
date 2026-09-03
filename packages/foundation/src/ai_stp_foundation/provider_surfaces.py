"""Exact provider projection profiles selected by the first alpha contract."""

from typing import Final, Literal, NamedTuple

from ai_stp_foundation.harnesses import HarnessId

type TargetScope = Literal["global", "user_root", "project"]
type ProviderSurfaceKey = tuple[HarnessId, TargetScope]


class ProviderSurfaceIdentity(NamedTuple):
    profile_id: str
    profile_digest: str
    bundle_format: str = "ai-stp-bundle/2"


PROVIDER_SURFACES: Final[dict[ProviderSurfaceKey, ProviderSurfaceIdentity]] = {
    ("antigravity", "global"): ProviderSurfaceIdentity(
        "antigravity/native-files/1",
        "sha256:57f6266b21cc6f67743c00a5351bfa29047dd465343dc6a7b07fe8e0bbb1cc68",
    ),
    ("antigravity", "project"): ProviderSurfaceIdentity(
        "antigravity/native-files/project/1",
        "sha256:1373140c6b0b1a75be329cf2b204ea1c8b16841670932b9b11119f3eb77d3cde",
    ),
    ("claude-code", "global"): ProviderSurfaceIdentity(
        "claude/native-and-marketplace/1",
        "sha256:07275f1e2a6ec41e7578f30d15cafdec8ebaeeffd33766550982000b6c90f4cb",
    ),
    ("claude-code", "project"): ProviderSurfaceIdentity(
        "claude/native-files/project/1",
        "sha256:6da32397d5c35ba0049093c13c2dc27047fc27a0de128c159e82dc2e4405e6c2",
    ),
    ("codex", "global"): ProviderSurfaceIdentity(
        "codex/native-files/1",
        "sha256:aab7dd80770b68424c605b58786e685a149af76494fe9ebd6b866290a4f1e4d6",
    ),
    ("codex", "user_root"): ProviderSurfaceIdentity(
        "codex/native-files/user-root/1",
        "sha256:2bb816c4d55e6413bbf1f0903b7c1da1ce7df3a451a6e13a5295d878fdce0caf",
    ),
    ("codex", "project"): ProviderSurfaceIdentity(
        "codex/native-files/project/1",
        "sha256:28d783e5ebd7e960870bcbe3aa98267f94a507efef6dfd31aeab33420b418b8d",
    ),
    ("cursor", "global"): ProviderSurfaceIdentity(
        "cursor/native-and-plugins/2",
        "sha256:4cbd7979c0c4c7b970e77feba54c88292a4916af565ba1619e2ad2c6fe35821a",
    ),
    ("cursor", "user_root"): ProviderSurfaceIdentity(
        "cursor/native-files/user-root/1",
        "sha256:c4d49fcc664b6d3114f130da31845badfd4bf3dbcce13eafd08e72805bcff774",
    ),
    ("cursor", "project"): ProviderSurfaceIdentity(
        "cursor/native-files/project/1",
        "sha256:32c8e0a629216f9d1292160b24c4b7b3f6e860e0aa95bcab1aa479a5de666108",
    ),
    ("grok-build", "global"): ProviderSurfaceIdentity(
        "grok/native-and-plugins/1",
        "sha256:2f547e20c9fd04cd3c962e31dc3afae98c206547b43761a8bf3a4fb5ff7a4c37",
    ),
    ("grok-build", "user_root"): ProviderSurfaceIdentity(
        "grok/native-files/user-root/1",
        "sha256:fbd42f7df68b93b9f7eb76f4d676cc501d9951e2e250c80b956e36a28115c493",
    ),
    ("opencode", "global"): ProviderSurfaceIdentity(
        "opencode/native-files/1",
        "sha256:9cbb0167fd7baac1d5983c0289d6d77ff6b63b4ad5c934ff20a195d923ae5e86",
    ),
    ("opencode", "user_root"): ProviderSurfaceIdentity(
        "opencode/native-files/user-root/1",
        "sha256:7c423c5270ed3cf4da89ba7cb3834acbe5e42b51a248e81a156d2c1bcddf6fba",
    ),
    ("pi", "global"): ProviderSurfaceIdentity(
        "pi/native-files/2",
        "sha256:a1ba9ccdc4513e67544e10cdbaa7ce62d173db515ac1c2fb61ac1de1be6d880a",
    ),
    ("pi", "user_root"): ProviderSurfaceIdentity(
        "pi/native-files/user-root/1",
        "sha256:7f628953962e922ca42c431ffc37fda28d23334f4cb00b33cb6fcaa988558330",
    ),
}


def provider_surface(harness_id: HarnessId, target_scope: TargetScope) -> ProviderSurfaceIdentity:
    """Return the exact profile for one supported harness scope."""
    return PROVIDER_SURFACES[(harness_id, target_scope)]
