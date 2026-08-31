"""Build the first-party corpus from the live setup-system repositories.

There was no such tool. The manifests and the embedded artifacts under `v1/`
were assembled outside this repository, which is why the corpus went on citing
an estate that had been transferred to a personal account and archived — nothing
here could rebuild it, so nothing here noticed.

What it does. For each harness it reads all four posture trees under `setups/`
of that harness's setup-system at `main`, maps every path to a component using
this repository's own projection rules, packages each one, and emits a manifest
beside the artifacts. This sentence said `setups/nddev-builder/` alone, which
was true until 2026-08-30 and then went on describing a quarter of the work the
constant below already did — a stale reason argues, and this one would have told
a reader the catalogue holds seven setups when it holds twenty-eight.

Git's own tree and blob SHAs are recorded as `source_tree`, so provenance is
the repository's hash rather than ours, and `source.commit` names the last
commit that touched the captured path rather than HEAD — see `_tree`.

Two things it deliberately does not do.

It does not invent a component for a path no rule routes. `composition.rule_for`
decides, and a file under a namespace this compiler cannot place is reported
rather than packaged — codex's `agents/nddev-builder.toml` is the live case: a
codex role is an `agents.<name>` table in the settings file plus a layer it
points at, so the file is a companion of the setting rather than a component,
and there is no honest kind for it.

It does not reuse the displaced estate's stable identifiers. Those objects came
from a different repository, and wearing their ids would say a published version
came from a source it did not. Its **own** previous ids it does reuse, and must:
see `held_identities` for why a rebuild that reminted them would leave a seeded
corpus with no path from `1.0` to `1.1`.
"""

from __future__ import annotations

import argparse
import json
import stat
import subprocess
import tempfile
import zipfile
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

from ai_stp_foundation.digests import digest_bytes

#: harness_id -> setup-system repository. The two differ, and assuming they did
#: not is how a first probe reported two of these as nonexistent.
REPOSITORIES: dict[str, str] = {
    "claude-code": "claude-setup-system",
    "codex": "codex-setup-system",
    "cursor": "cursor-setup-system",
    "grok-build": "grok-setup-system",
    "pi": "pi-setup-system",
    "opencode": "opencode-setup-system",
    "antigravity": "antigravity-setup-system",
}

ORGANISATION = "NDDev-OpenNetwork"
#: The product axis the setup-systems publish on, in the order a reader should
#: meet them: least configured first. Each is a directory under `setups/` in
#: every one of the seven repositories, and its `setup.json` carries `"id"` with
#: exactly this string — measured across all 7x4 by the publishing side, which
#: also warned that `id` is **not** unique across the estate. `baseline` names
#: seven different setups, so the key is the pair.
#:
#: This was `nddev-builder` alone until 2026-08-30, so the catalogue carried 7
#: of the 28 published setups — a quarter, and the one posture least applicable
#: to an ordinary user, because it is the toolkit for building harness artifacts.
POSTURES: tuple[str, ...] = ("minimal", "baseline", "full-auto", "nddev-builder")


def setup_path(posture: str) -> str:
    return f"setups/{posture}/setup.json"


def home_prefix(posture: str) -> str:
    return f"setups/{posture}/home/"


def source_path(posture: str) -> str:
    """The path whose history is one posture's provenance."""
    return f"setups/{posture}"


ARTIFACT_DIGEST_DOMAIN = "ai-stp:artifact:v1"
COMPONENT_TREE = "ai-stp-component-tree/1"
COMPONENT_FILE = "ai-stp-component-file/1"


def _gh(path: str, jq: str) -> str:
    result = subprocess.run(
        ["gh", "api", path, "--jq", jq], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {path}: {result.stderr.strip()}")
    return result.stdout.strip()


def _blob(repository: str, sha: str) -> bytes:
    import base64

    raw = _gh(f"repos/{ORGANISATION}/{repository}/git/blobs/{sha}", ".content")
    return base64.b64decode(raw)


def source_commit(repository: str, posture: str) -> str:
    """The last commit that touched one posture's captured path.

    Split out of `_tree` so the property can be exercised directly: the question
    "which commit produced these bytes" has one answer, and it is not HEAD. It
    is asked per posture rather than per repository, because the four move
    independently and a shared answer would restore exactly the staleness the
    docstring on `_tree` describes, one level up.
    """
    path = source_path(posture)
    commit = _gh(f"repos/{ORGANISATION}/{repository}/commits?path={path}&per_page=1", ".[0].sha")
    if not commit:
        raise RuntimeError(f"{repository}: no commit has touched {path}")
    return commit


def _tree(repository: str) -> list[dict[str, Any]]:
    """Every entry of the repository at `main`, for all four postures at once.

    This asked for `commits/main` — the repository's HEAD — until 2026-08-29.
    HEAD moves on every provider release, and `source.commit` is inside a
    content-addressed passport, so all seven setup passports changed their
    digest whenever any provider released, whether or not `setups/nddev-builder`
    had moved. Measured that day: three provider releases moved two of
    thirty-three components and none of the seven setups, yet every setup
    passport differed.

    Because a published `X.Y` is immutable, that made a seeded corpus look
    outdated the moment any provider released, forever — and that appearance,
    not any content, deferred the catalogue reseed twice.

    So the provenance names the last commit that touched the captured path. It
    is the honest answer to "which commit produced these bytes", it changes when
    and only when they do, and git already holds it. The tree itself is still
    read at `main`: that is the state being captured.
    """
    raw = _gh(f"repos/{ORGANISATION}/{repository}/git/trees/main?recursive=1", ".tree")
    entries: list[dict[str, Any]] = json.loads(raw)
    return entries


#: The asset every setup-system publishes for the platform this script runs on.
#: Only Linux, and deliberately so: the point is to *ask* the provider, and a
#: build host that cannot run it must say so rather than guess.
LINUX_ASSET = "{name}-x86_64-unknown-linux-gnu"


def _platform_support(repository: str) -> tuple[list[str], list[str]]:
    """The operating systems and architectures the provider itself declares.

    This was two literals — `["linux"]` and `["x86_64"]` — written into the
    setup body below. All seven providers declare three systems and two
    architectures, so every published setup understated its own platform support,
    and it had done since the value was first typed. A value copied from a source
    and never compared to it again: the same defect as the archived provenance
    this builder exists to fix, one field along.

    The repair is one fewer copy rather than one more check. There is no
    fallback: a literal that stands in when the question cannot be asked is the
    copy coming back.
    """
    with tempfile.TemporaryDirectory() as held:
        directory = Path(held)
        name = LINUX_ASSET.format(name=repository)
        result = subprocess.run(
            [
                "gh",
                "release",
                "download",
                "--repo",
                f"{ORGANISATION}/{repository}",
                "--pattern",
                name,
                "--dir",
                str(directory),
                "--clobber",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{repository}: could not download {name}: {result.stderr.strip()}")
        binary = directory / name
        binary.chmod(0o755)
        answer = subprocess.run(
            [str(binary), "provider-info"], capture_output=True, text=True, check=False
        )
        if answer.returncode != 0:
            raise RuntimeError(f"{repository}: provider-info failed: {answer.stderr.strip()}")
        declared = json.loads(answer.stdout)
    systems = [str(item) for item in declared["supported_os"]]
    machines = [str(item) for item in declared["supported_arch"]]
    if not systems or not machines:
        raise RuntimeError(f"{repository}: provider-info declares an empty platform set")
    return sorted(systems), sorted(machines)


def _components(
    harness_id: str, entries: list[dict[str, Any]], posture: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Map one posture's home paths to components, or report why they are not."""
    from ai_stp_cli.local import composition

    rules = [rule for rule in composition.PROVIDER_RULES if rule.harness_id == harness_id]
    by_relative = {rule.relative: rule for rule in rules}
    blobs = {item["path"]: item for item in entries if item["type"] == "blob"}
    trees = {item["path"]: item for item in entries if item["type"] == "tree"}

    prefix = home_prefix(posture)
    found: list[dict[str, Any]] = []
    unrouted: list[str] = []
    claimed: set[str] = set()

    for rule in sorted(rules, key=lambda item: -len(item.relative)):
        base = f"{prefix}{rule.relative}"
        if rule.shape == "file":
            if base in blobs and base not in claimed:
                claimed.add(base)
                found.append(
                    {
                        "component_type": rule.component_type,
                        "projection_kind": rule.projection_kind,
                        "slug": rule.relative,
                        # The path the compiler will project this to, taken from
                        # the same rule rather than restated. The corpus used to
                        # carry a third hand-written projection table beside
                        # `PROVIDER_RULES` and the harness catalogue, and the
                        # three had already drifted — cursor's plugin was
                        # `plugins/local` in one and `plugins` in another.
                        "native_path": rule.relative,
                        "source_path": f"{posture}/home/{rule.relative}",
                        "source_tree": blobs[base]["sha"],
                        "artifact_format": COMPONENT_FILE,
                        "source_object_kind": "blob",
                    }
                )
            continue
        # A directory rule: every immediate child is one component.
        for path, item in sorted(trees.items()) + sorted(blobs.items()):
            parent, _, name = path.rpartition("/")
            if parent != base or path in claimed:
                continue
            claimed.add(path)
            found.append(
                {
                    "component_type": rule.component_type,
                    "projection_kind": rule.projection_kind,
                    "slug": name,
                    "native_path": f"{rule.relative}/{name}",
                    "source_path": f"{posture}/home/{rule.relative}/{name}",
                    "source_tree": item["sha"],
                    "artifact_format": (
                        COMPONENT_TREE if item["type"] == "tree" else COMPONENT_FILE
                    ),
                    "source_object_kind": "tree" if item["type"] == "tree" else "blob",
                }
            )

    for path in sorted(blobs):
        if not path.startswith(prefix) or path in claimed:
            continue
        relative = path[len(prefix) :]
        if any(relative.startswith(f"{item}/") for item in claimed_relatives(claimed, posture)):
            continue
        if relative.split("/")[0] not in by_relative and relative not in by_relative:
            unrouted.append(relative)
    return found, sorted(set(unrouted))


def claimed_relatives(claimed: set[str], posture: str) -> list[str]:
    prefix = home_prefix(posture)
    return [path[len(prefix) :] for path in claimed if path.startswith(prefix)]


def _package(repository: str, entries: list[dict[str, Any]], component: dict[str, Any]) -> bytes:
    """The exact bytes of one component, as the corpus embeds them."""
    prefix = f"setups/{component['source_path']}"
    if component["source_object_kind"] == "blob":
        return _blob(repository, component["source_tree"])
    members = sorted(
        (
            item
            for item in entries
            if item["type"] == "blob" and item["path"].startswith(f"{prefix}/")
        ),
        key=lambda item: str(item["path"]),
    )
    contents = [
        (item["path"][len(prefix) + 1 :], _blob(repository, item["sha"])) for item in members
    ]
    # The reader recomputes this with `digest_bytes`, which is domain-separated.
    # A plain `sha256` here produced an archive that validated against itself and
    # was refused by the only consumer — the manifest is not the authority on how
    # its own digests are formed.
    manifest = [
        {
            "path": relative,
            "byte_length": len(content),
            "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, content),
            "mode": 420,
        }
        for relative, content in contents
    ]
    body = json.dumps(
        {"files": manifest, "format": COMPONENT_TREE}, separators=(",", ":"), sort_keys=True
    ).encode()

    held = BytesIO()
    with zipfile.ZipFile(held, "w", zipfile.ZIP_STORED) as archive:
        # `component.json` first, and the members after it in name order: the
        # reader asserts the name list is sorted, and `component.json` sorts
        # before `files/`. Writing the manifest last produced an archive that
        # was valid and refused.
        for name, content in [("component.json", body)] + [
            (f"files/{relative}", content) for relative, content in contents
        ]:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            # The same three fields the local writer sets, and the reader checks
            # all three. `external_attr` without `S_IFREG` fails `stat.S_ISREG`,
            # which is how the first build produced archives every consumer
            # refused as corrupt — the file-type bits are not decoration.
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content)
    return held.getvalue()


def held_versions(out: Path) -> dict[str, str]:
    """The version each identity already carries, by stable id.

    A published `X.Y` is immutable (`REQ-2606`), so an object whose passport
    changes has to go out as a **new** version. Every member used to be `1.0`,
    argued from a premise that was true when written: the corpus had just been
    rebuilt from a different repository and minted fresh identifiers, so nothing
    here was a second attempt at an id somebody already held.

    That premise stopped being true the moment identity continuity started
    reusing them. Measured against the deployed catalogue on 2026-08-30: 40 of
    98 objects were held identities sitting at `1.0`, already published, and all
    40 had different passport bytes — republishing them at `1.0` is exactly what
    immutability forbids.
    """
    manifest_path = out / "corpus-sources.json"
    if not manifest_path.is_file():
        return {}
    held = json.loads(manifest_path.read_text(encoding="utf-8"))
    versions: dict[str, str] = {}
    for entry in held.get("harnesses", []):
        if entry.get("setup_id"):
            versions[entry["setup_id"]] = entry.get("setup_version", "1.0")
        for item in entry.get("components", []):
            if item.get("stable_id"):
                versions[item["stable_id"]] = item.get("version", "1.0")
    return versions


def next_version(current: str | None, *, moved: bool) -> str:
    """`1.0` for something new, the next minor for something that moved.

    Not a bump on every rebuild: a rebuild that changes no bytes must publish
    nothing, and a version carrying identical content is waste a reader has to
    tell apart from a real change. `first_party_launch_publication` remains the
    authority — it refuses a version already published with a different digest —
    and this only keeps the common case from reaching that refusal.
    """
    if current is None:
        return "1.0"
    if not moved:
        return current
    major, minor = (int(part) for part in current.split("."))
    return f"{major}.{minor + 1}"


def held_identities(
    out: Path,
) -> tuple[dict[tuple[str, str, str, str], str], dict[tuple[str, str], str]]:
    """The identifiers a previous build of this corpus already gave these objects.

    The docstring above says this builder does not reuse *the archived estate's*
    identifiers, and it does not: those objects came from another repository and
    wearing their ids would claim a source they never had.

    Reusing its **own** previous ids is the opposite case and it is required.
    `new_id` mints a fresh ULID per call, so before this function every rebuild
    replaced all forty identities. Published `X.Y` is immutable, so once the
    corpus is seeded that behaviour leaves no path from `1.0` to `1.1`: the next
    provider change could only be published as forty *new* objects, orphaning
    the seeded set and growing the catalogue by forty on every rebuild.

    Logical identity is `(harness, kind, slug, source_tree)` for a component and
    `(harness, posture)` for a setup. Both keys gained a member on 2026-08-30,
    when the build stopped reading one posture of four, and each addition
    answers a measurement rather than a preference.

    **The setup key.** `setup.json` publishes `"id"` with the posture in it, and
    that id is not unique across the estate — `baseline` names seven different
    setups. Keyed by harness alone, seven held identities would have smeared
    across twenty-eight objects, every one of them looking stable while naming
    something else.

    **The component key.** Read across all four postures, the seven repositories
    hold 152 files under `home/` and 130 distinct `(slug, content)` pairs: only
    13 slugs of 116 carry more than one content, and they are exactly the
    instruction and the setting file of each harness. A posture is expressed
    through those two and nothing else; every skill, command and agent is
    byte-identical wherever it appears.

    That measurement argues for keying on the content SHA, and the first
    version of this did. It is wrong, for the reason this docstring already
    gives one paragraph up. **Content separates a variant from a variant and
    cannot separate a variant from a version.** Under a content key, the day
    upstream edits `baseline`'s `CLAUDE.md` that object stops existing and a
    different one appears — no path from `1.0` to `1.1`, orphaning exactly what
    reusing identifiers exists to prevent, and now on every upstream edit rather
    than every rebuild. Measured on the live trees: ten components had already
    moved, so ten of thirty-three would have been orphaned on the first run.

    So the key is `(harness, kind, slug, posture)`. A component belongs to a
    setup and a setup is a `(harness, posture)`; the same slug in two postures is
    two objects that may happen to hold the same bytes today and may diverge
    tomorrow, and each keeps its own version line through that. The cost is
    named rather than hidden: an instruction identical across three postures is
    three catalogue objects. That is a presentation question — a card can say
    what it is identical to — and identity is not the place to solve it.
    """
    manifest_path = out / "corpus-sources.json"
    if not manifest_path.is_file():
        return {}, {}
    held = json.loads(manifest_path.read_text(encoding="utf-8"))
    # A manifest built before 2026-08-30 has no `posture`, because one posture
    # of four was read: it was `nddev-builder`. Reading it as that is what lets
    # the 33 component and 7 setup identities already published stay attached to
    # their objects; dropping the fallback would remint them and orphan the
    # seeded corpus, which is the failure this whole function exists to avoid.
    components = {
        (
            entry["harness_id"],
            item["component_type"],
            item["slug"],
            entry.get("posture", "nddev-builder"),
        ): item["stable_id"]
        for entry in held.get("harnesses", [])
        for item in entry.get("components", [])
        if item.get("stable_id")
    }
    setups = {
        (entry["harness_id"], entry.get("posture", "nddev-builder")): entry["setup_id"]
        for entry in held.get("harnesses", [])
        if entry.get("setup_id")
    }
    return components, setups


def build(harnesses: Sequence[str], *, out: Path, bump_all: bool = False) -> dict[str, Any]:
    from ai_stp_foundation.ids import new_id

    known_components, known_setups = held_identities(out)
    known_versions = held_versions(out)
    # What the *previous* manifest recorded for each object, so "did this move"
    # is answered against the bytes rather than against the clock.
    previous_trees: dict[str, str] = {}
    previous_setup_blobs: dict[str, str] = {}
    if (out / "corpus-sources.json").is_file():
        held = json.loads((out / "corpus-sources.json").read_text(encoding="utf-8"))
        for entry in held.get("harnesses", []):
            if entry.get("setup_id"):
                previous_setup_blobs[entry["setup_id"]] = entry.get("setup_blob", "")
            for item in entry.get("components", []):
                if item.get("stable_id"):
                    previous_trees[item["stable_id"]] = item.get("source_tree", "")
    report: dict[str, Any] = {"harnesses": {}, "unrouted": {}, "new_identities": []}
    manifest: list[dict[str, Any]] = []
    written: dict[str, bytes] = {}
    for harness_id in harnesses:
        repository = REPOSITORIES[harness_id]
        entries = _tree(repository)
        systems, machines = _platform_support(repository)
        by_posture = {posture: _components(harness_id, entries, posture) for posture in POSTURES}
        for posture in POSTURES:
            components, unrouted = by_posture[posture]
            path = setup_path(posture)
            setup = next((item for item in entries if item["path"] == path), None)
            if setup is None:
                raise RuntimeError(f"{repository} has no {path}")
            declared = json.loads(_blob(repository, setup["sha"]))
            # The posture is a published field, not a path segment we recognised.
            # Keying on the segment would work today and quietly disagree the
            # first time a directory is renamed without its `id`.
            if declared.get("id") != posture:
                raise RuntimeError(
                    f"{repository}: {path} declares id {declared.get('id')!r}, not {posture!r}"
                )
            setup_id = known_setups.get((harness_id, posture))
            if setup_id is None:
                setup_id = new_id("setup")
                report["new_identities"].append(f"setup {harness_id}/{posture}")
            for component in components:
                # A file rule's slug is its relative path, which may carry a
                # separator — antigravity's setting is
                # `antigravity-cli/settings.json`. An artifact name is a
                # filename, so the separator becomes a dash rather than a
                # directory nobody created.
                flat = component["slug"].replace("/", "-")
                # The posture is in the name because it is in the identity: the
                # same slug in two postures is two objects, and two objects may
                # not share a filename. It is not a disambiguator applied only
                # on collision — that would make one object's name depend on
                # whether another exists.
                name = f"{harness_id}-{posture}-{flat}-{component['component_type']}"
                suffix = (
                    ".zip"
                    if component["source_object_kind"] == "tree"
                    else Path(component["slug"]).suffix or ".txt"
                )
                component["artifact_name"] = f"{name}{suffix}"
                identity = (harness_id, component["component_type"], component["slug"], posture)
                held = known_components.get(identity)
                if held is None:
                    held = new_id("component")
                    report["new_identities"].append(
                        f"component {harness_id}/{posture}/{component['slug']}"
                    )
                component["stable_id"] = held
                component["version"] = next_version(
                    known_versions.get(held),
                    moved=bump_all
                    or previous_trees.get(held, component["source_tree"])
                    != component["source_tree"],
                )
                # Cached by content, not by name: postures sharing a blob share
                # the packaging work, while each still writes its own artifact,
                # because each is its own object.
                packaged = written.get(component["source_tree"])
                if packaged is None:
                    packaged = _package(repository, entries, component)
                    written[component["source_tree"]] = packaged
                (out / component["artifact_name"]).write_bytes(packaged)
            manifest.append(
                {
                    "commit": source_commit(repository, posture),
                    "components": components,
                    "evidence_ref": f"https://github.com/{ORGANISATION}/{repository}",
                    "harness_id": harness_id,
                    "posture": posture,
                    # Published prose, never composed here. `full-auto` runs to
                    # thousands of characters and is load-bearing safety context
                    # — it names things like the sandbox key reaching nothing on
                    # native Windows — so a browse card may clamp it and an
                    # install surface may not.
                    "setup_description": declared["description"],
                    # A missing `sources` is a statement, not an omission: five
                    # of the seven `minimal` setups set no product keys, so there
                    # is nothing to source. Rendering that as "undocumented"
                    # would be a third invented fact on the same page.
                    "setup_sources": declared.get("sources", []),
                    "repository": f"https://github.com/{ORGANISATION}/{repository}",
                    "supported_os": systems,
                    "supported_arch": machines,
                    "setup_blob": setup["sha"],
                    "setup_id": setup_id,
                    "setup_version": next_version(
                        known_versions.get(setup_id),
                        moved=bump_all
                        or previous_setup_blobs.get(setup_id, setup["sha"]) != setup["sha"],
                    ),
                    "setup_path": path,
                }
            )
            report["harnesses"][f"{harness_id}/{posture}"] = len(components)
            if unrouted:
                report["unrouted"][f"{harness_id}/{posture}"] = unrouted
    report["manifest"] = {"harnesses": manifest, "schema_version": 1}
    return report


def drift(manifest: dict[str, Any], harnesses: Sequence[str]) -> dict[str, Any]:
    """What actually moved since this manifest was built, counted in content.

    The manifest records each repository's `commit`, and a commit changes every
    time the provider releases — for reasons that have nothing to do with the
    `setups/nddev-builder/` payload this corpus captures. Comparing commits made
    all seven look stale after every provider release, and that reading deferred
    the catalogue reseed twice while the bytes had barely moved: measured on
    2026-08-29, three provider releases had changed **two** of thirty-three
    components and none of the seven setups.

    So the question is asked of the content. `source_tree` is git's own SHA of
    the blob or tree, and `setup_blob` of `setup.json`; both are recorded
    already. Comparing them against the live tree answers "does republishing
    this object say anything new", which is the question a reseed is actually
    waiting on.

    It reports and never refuses. A corpus that lags the provider by two
    components is a normal, publishable state — the next version carries them —
    and a tool that exits non-zero on it would reinstate exactly the block this
    measurement removes.
    """
    moved: dict[str, Any] = {"components": {}, "setups": [], "unchanged": 0, "changed": 0}
    recorded: dict[str, list[dict[str, Any]]] = {}
    for item in manifest["harnesses"]:
        recorded.setdefault(item["harness_id"], []).append(item)
    for harness_id in harnesses:
        entries_for = recorded.get(harness_id)
        if not entries_for:
            continue
        live = {item["path"]: item["sha"] for item in _tree(REPOSITORIES[harness_id])}
        for entry in entries_for:
            # `posture` may be absent in a manifest built before 2026-08-30, when
            # one posture of four was read. Reporting such an entry under its
            # harness alone would be the honest answer for the shape it has.
            posture = entry.get("posture")
            where = f"{harness_id}/{posture}" if posture else harness_id
            if live.get(entry["setup_path"]) != entry.get("setup_blob"):
                moved["setups"].append(where)
            for component in entry["components"]:
                path = f"setups/{component['source_path']}"
                if live.get(path) == component["source_tree"]:
                    moved["unchanged"] += 1
                    continue
                moved["changed"] += 1
                moved["components"].setdefault(where, []).append(component["slug"])
    return moved


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--harness", action="append", choices=sorted(REPOSITORIES))
    parser.add_argument(
        "--bump-all",
        action="store_true",
        help=(
            "give every held object its next minor version. For a change to the "
            "passport itself — a field added or removed — which moves every "
            "passport's bytes while no source byte moved, so the per-object test "
            "cannot see it."
        ),
    )
    parser.add_argument(
        "--drift",
        action="store_true",
        help="report what moved in the content since --out was built, and build nothing",
    )
    options = parser.parse_args(arguments)
    if options.drift:
        manifest = json.loads((options.out / "corpus-sources.json").read_text(encoding="utf-8"))
        print(
            json.dumps(
                drift(manifest, options.harness or sorted(REPOSITORIES)),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 0
    options.out.mkdir(parents=True, exist_ok=True)
    report = build(
        options.harness or sorted(REPOSITORIES), out=options.out, bump_all=options.bump_all
    )
    (options.out / "corpus-sources.json").write_text(
        json.dumps(
            report.pop("manifest"), separators=(",", ":"), sort_keys=True, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
