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
        "sha256:d46222869ceecea45f4eb42a31e4309d5960e0d366345d1adb0ddc04e33fd5b9",
    ),
    ("antigravity", "project"): ProviderSurfaceIdentity(
        "antigravity/native-files/project/1",
        "sha256:6709b8225f55d2ce6753850ff80c973bf03959cc4aaba31c4d5fbe8128d5e0ea",
    ),
    ("claude-code", "global"): ProviderSurfaceIdentity(
        "claude/native-and-marketplace/1",
        "sha256:c685d34c5386cd16ba27a57a7fd960e788dafa2544cd8f715ad88176c4ede551",
    ),
    ("claude-code", "project"): ProviderSurfaceIdentity(
        "claude/native-files/project/1",
        "sha256:593fddfbb3d576d5e3e286f7905d8ec0b1dcef074e6da101b7c6c10cbcee75d0",
    ),
    ("codex", "global"): ProviderSurfaceIdentity(
        "codex/native-files/1",
        "sha256:0b51b0ddd434f62c11b504102dafb62a28a59a6436104882355632e6d86f2585",
    ),
    ("codex", "user_root"): ProviderSurfaceIdentity(
        "codex/native-files/user-root/1",
        "sha256:d4a402e1ecb70feefee4c36e819c15c46dc4bed0d8f022da45e37047dbff0ee2",
    ),
    ("codex", "project"): ProviderSurfaceIdentity(
        "codex/native-files/project/1",
        "sha256:89ccffaec2c7c7577ee818ca5252d0877b5ad3227fa56461bca5df0280d8ea8f",
    ),
    ("cursor", "global"): ProviderSurfaceIdentity(
        "cursor/native-and-plugins/2",
        "sha256:2cae2fea2245f5d816f86baa4843a70bdf915aef1e48e0902a6fd57f2b0fcca6",
    ),
    ("cursor", "user_root"): ProviderSurfaceIdentity(
        "cursor/native-files/user-root/1",
        "sha256:0ef4a2820dc61341e293076c7ef81b4ee989c6c7132ce17d52f07d8e9e0a5c7a",
    ),
    ("cursor", "project"): ProviderSurfaceIdentity(
        "cursor/native-files/project/1",
        "sha256:08019697bf8116d466a20188dbadfb5d8d40fd75653179a34a87937a02e2ad77",
    ),
    ("grok-build", "global"): ProviderSurfaceIdentity(
        "grok/native-and-plugins/1",
        "sha256:616d9a0667abf01fdf1e8c756bbf9341f23bf57a41c4291b40f33add0b0f7590",
    ),
    ("grok-build", "user_root"): ProviderSurfaceIdentity(
        "grok/native-files/user-root/1",
        "sha256:53b7a1d11b6e9eafe870bbcd8b6f6a208e89929d674d50e3e436d7b984182845",
    ),
    ("opencode", "global"): ProviderSurfaceIdentity(
        "opencode/native-files/1",
        "sha256:3598000e9206586d606faea1d12c1a3f80a0b7f812c350eb9236a44a303e19ac",
    ),
    ("opencode", "user_root"): ProviderSurfaceIdentity(
        "opencode/native-files/user-root/1",
        "sha256:89088644bb23d353252a0c01088d7856af878ee10b3fef3097c95fb94d07ea77",
    ),
    ("pi", "global"): ProviderSurfaceIdentity(
        "pi/native-files/2",
        "sha256:7e6131ce8c8386540cbd31c9c82b4e2db3ee865f1d8093ebf10b62337f234062",
    ),
    ("pi", "user_root"): ProviderSurfaceIdentity(
        "pi/native-files/user-root/1",
        "sha256:f6e6851da4def264317162a6ba7ba11b9c873bf5cf4086694b34185e82bb7237",
    ),
}


def provider_surface(harness_id: HarnessId, target_scope: TargetScope) -> ProviderSurfaceIdentity:
    """Return the exact profile for one supported harness scope."""
    return PROVIDER_SURFACES[(harness_id, target_scope)]
