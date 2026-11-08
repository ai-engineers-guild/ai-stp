"""Reconcile an immutable Desktop tag after its exact source has reached Main."""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any

from release_scripts._github_delivery import GitHub, PromotionRefused, require


def published(release: dict[str, Any], tag: str, version: str) -> None:
    require(
        release.get("tag_name") == tag
        and release.get("draft") is False
        and release.get("prerelease") is False
        and bool(release.get("published_at")),
        "Desktop release is not published",
    )
    assets = release.get("assets", [])
    names = [asset.get("name", "") for asset in assets]
    require(
        len(names) == len(set(names)) == 7 and "SHA256SUMS" in names,
        "Desktop release inventory is incomplete",
    )
    installers = [name for name in names if name != "SHA256SUMS"]
    require(
        {name.rsplit(".", 1)[-1] for name in installers}
        == {"deb", "rpm", "AppImage", "dmg", "msi", "exe"}
        and all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name)
            and re.search(rf"(?:^|[-_]){re.escape(version)}(?:[-_.]|$)", name)
            for name in installers
        ),
        "Desktop installer identity differs",
    )
    require(
        all(
            asset.get("state") == "uploaded"
            and asset.get("size", 0) > 0
            and re.fullmatch(r"sha256:[0-9a-f]{64}", asset.get("digest") or "")
            for asset in assets
        ),
        "Desktop release has incomplete asset digests",
    )


def reconcile(api: GitHub, head: str, version: str, run_id: int) -> bool:
    tag = f"desktop-v{version}"
    status, reference = api.request(f"git/ref/tags/{tag}")
    if status == 404:
        require(
            api.read("git/ref/heads/main")["object"]["sha"] == head,
            "Main changed before release tagging",
        )
        annotated = api.write(
            "git/tags",
            {
                "tag": tag,
                "message": f"Desktop {version}; qualified source {head}; Dev run {run_id}",
                "object": head,
                "type": "commit",
            },
            create=True,
        )
        api.write("git/refs", {"ref": f"refs/tags/{tag}", "sha": annotated["sha"]}, create=True)
        reference = api.read(f"git/ref/tags/{tag}")
    else:
        require(status == 200, f"Desktop tag could not be read ({status})")
    require(reference.get("object", {}).get("type") == "tag", "Annotated Desktop tag required")
    annotated = api.read("git/tags/" + reference["object"]["sha"])
    require(
        annotated.get("tag") == tag and annotated.get("object", {}).get("type") == "commit",
        "Desktop tag identity differs",
    )
    tagged_source = annotated["object"]["sha"]
    require(
        api.read(f"compare/{tagged_source}...{head}").get("status") in {"ahead", "identical"},
        "Desktop version belongs to a different source history",
    )
    status, release = api.request(f"releases/tags/{tag}")
    if status == 404:
        require(tagged_source == head, "An older Desktop version is not completely published")
        return True
    require(status == 200, f"Desktop release could not be read ({status})")
    if tagged_source == head:
        require(
            release.get("tag_name") == tag and release.get("prerelease") is False,
            "Desktop release identity differs",
        )
        # The publisher verifies existing digests, fills only missing assets
        # and publishes an acknowledged draft. It never replaces an asset.
        return True
    published(release, tag, version)
    return False


def main() -> None:
    try:
        api = GitHub(os.environ["REPOSITORY"])
        head, version = os.environ["HEAD_SHA"], os.environ["EXPECTED_VERSION"]
        require(bool(re.fullmatch(r"[0-9a-f]{40}", head)), "Exact source required")
        require(
            bool(re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version)),
            "Stable Desktop version required",
        )
        tag = f"desktop-v{version}"
        reference = api.read(f"git/ref/tags/{tag}")["object"]
        require(reference.get("type") == "tag", "Annotated Desktop tag required")
        annotated = api.read("git/tags/" + reference["sha"])
        require(
            annotated.get("tag") == tag
            and annotated.get("object", {}).get("type") == "commit"
            and annotated["object"]["sha"] == head,
            "Desktop tag does not name this source",
        )
        require(
            api.read("git/ref/heads/main")["object"]["sha"] == head,
            "Desktop tag is not current Main",
        )
    except (PromotionRefused, KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Desktop publication refused: {error}") from None


if __name__ == "__main__":
    main()
