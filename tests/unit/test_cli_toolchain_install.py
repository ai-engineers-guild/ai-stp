"""Installing a pinned tool: mostly proving that a hostile archive costs nothing."""

import io
import os
import tarfile
import zipfile
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.toolchain import Artifact, Tool, install

RUFF = Tool(
    tool_id="ruff",
    ecosystem="python",
    purpose="linter",
    version="0.16.1",
    license="MIT",
    entry_point="ruff",
    digest_source="vendor_published",
    artifacts={},
)


def _tar(members: dict[str, bytes], *, mode: int = 0o644) -> bytes:
    holder = io.BytesIO()
    with tarfile.open(fileobj=holder, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = mode
            archive.addfile(info, io.BytesIO(content))
    return holder.getvalue()


def _zip(members: dict[str, bytes]) -> bytes:
    holder = io.BytesIO()
    with zipfile.ZipFile(holder, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return holder.getvalue()


def _digest(content: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(content).hexdigest()


def _artifact(content: bytes) -> Artifact:
    return Artifact(url="https://example.test/ruff/0.16.1/ruff.tar.gz", digest=_digest(content))


def _pin(
    monkeypatch: pytest.MonkeyPatch,
    command: ModuleType,
    payload: bytes,
    *,
    serve: bytes | None = None,
) -> None:
    """Pin one tool for the command under test, and refuse the network by default.

    `serve=None` makes any download an outright failure rather than a stub that
    quietly succeeds: several of these tests are precisely the claim that the
    network was *not* reached, and a permissive stub would pass them either way.
    """

    def download(url: str, **_: object) -> bytes:
        if serve is None:
            raise AssertionError(f"the network was reached for {url}")
        return serve

    def pinned(tool_id: str) -> tuple[Tool, Artifact]:
        assert tool_id == RUFF.tool_id
        return RUFF, _artifact(payload)

    monkeypatch.setattr(install, "download", download)
    monkeypatch.setattr(command, "pinned_for", pinned)


@pytest.fixture
def payload() -> bytes:
    return _tar({"ruff": b"#!/bin/sh\necho 0.16.1\n"})


def test_a_plan_names_everything_before_anything_is_written(payload: bytes) -> None:
    # `REQ-1405`: a plan first. Nothing exists on disk after asking for one.
    prepared = install.plan(RUFF, _artifact(payload))
    assert prepared.action == "install"
    assert prepared.target.name == "0.16.1"
    assert prepared.digest == _digest(payload)
    assert not prepared.target.exists()
    assert not install.root().exists()


def test_an_install_verifies_stages_and_switches_a_pointer(payload: bytes) -> None:
    target, created = install.perform(RUFF, _artifact(payload), payload)
    assert (target / "ruff").exists()
    current_target = install.current_target("ruff")
    assert current_target is not None

    # `REQ-1404`: the tool is reached through the pointer, at an exact path.
    expected_binary = (
        current_target / "ruff" if os.name == "nt" else install.pointer("ruff") / "ruff"
    )
    assert install.binary(RUFF) == expected_binary
    assert install.current_target("ruff") == target
    assert install.binary(RUFF).read_bytes().startswith(b"#!/bin/sh")

    # `REQ-1411`: everything created is claimed, and nothing else is.
    assert str(target / "ruff") in [str(p) for p in created]
    assert set(install.owned()) == {str(p) for p in created}

    # Asking again is a no-op that says so rather than reinstalling.
    assert install.plan(RUFF, _artifact(payload)).action == "already_installed"


def test_the_tool_is_found_by_path_even_when_path_is_poisoned(
    payload: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`REQ-1404`, checked against a `PATH` that answers with something else."""
    install.perform(RUFF, _artifact(payload), payload)

    impostor = tmp_path / "poison"
    impostor.mkdir()
    (impostor / "ruff").write_text("#!/bin/sh\necho 9.9.9\n", encoding="utf-8")
    (impostor / "ruff").chmod(0o755)
    monkeypatch.setenv("PATH", str(impostor))

    # The surrounding environment now offers a different `ruff`. The managed
    # path does not consult it, so it is not a source of truth here.
    assert install.binary(RUFF).read_bytes().startswith(b"#!/bin/sh\necho 0.16.1")


def test_bytes_that_do_not_match_their_digest_never_reach_the_cache() -> None:
    good = _tar({"ruff": b"real"})
    with pytest.raises(CliFailure, match="does not match its pinned digest") as raised:
        install.remember(b"tampered", _digest(good))
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    # Nothing was written, so a later offline install cannot find it and trust
    # it: an unverified artifact in the cache would undo `REQ-1412` entirely.
    assert not install.cache_dir().exists() or not list(install.cache_dir().iterdir())


def test_a_cached_artifact_is_verified_again_on_the_way_out(payload: bytes) -> None:
    cached = install.remember(payload, _digest(payload))
    assert install.cached_bytes(_digest(payload)) == payload

    # A cache entry that changed on disk since it was written is refused, even
    # though it was verified when it arrived.
    cached.write_bytes(b"swapped underneath")
    with pytest.raises(CliFailure, match="does not match its pinned digest"):
        install.cached_bytes(_digest(payload))


def test_offline_uses_the_verified_cache_and_refuses_an_unknown_artifact(payload: bytes) -> None:
    # `REQ-1412` in both directions.
    unknown = install.plan(RUFF, _artifact(payload), offline=True)
    assert unknown.action == "needs_user_action"
    assert "not in the verified cache" in unknown.reason
    assert unknown.offline_capable is False

    install.remember(payload, _digest(payload))
    known = install.plan(RUFF, _artifact(payload), offline=True)
    assert known.action == "install"
    assert known.offline_capable is True

    with pytest.raises(CliFailure, match="not in the verified cache") as raised:
        install.cached_bytes(_digest(b"never seen"))
    # `REQ-1413`: a typed reason, so a caller can tell "needs network" from
    # "this is broken".
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_an_install_script_in_an_archive_is_unpacked_and_never_run(tmp_path: Path) -> None:
    """`REQ-1406`, as a fixture that would leave evidence if it ran."""
    marker = tmp_path / "executed"
    script = f"#!/bin/sh\ntouch {marker}\n".encode()
    hostile = _tar({"ruff": b"binary", "install.sh": script, "setup.py": b"import os"})

    target, _ = install.perform(RUFF, _artifact(hostile), hostile)

    assert (target / "install.sh").read_bytes() == script
    assert not marker.exists()


@pytest.mark.parametrize("member", ["../escaped", "../../escaped", "a/../../escaped"])
def test_an_archive_that_traverses_upward_is_refused(member: str, tmp_path: Path) -> None:
    hostile = _tar({member: b"payload"})
    with pytest.raises(CliFailure, match="could not be safely unpacked"):
        install.unpack(hostile, tmp_path / "into")
    assert not (tmp_path / "escaped").exists()


def test_an_absolute_member_is_neutralised_rather_than_refused(tmp_path: Path) -> None:
    """The `data` filter makes an absolute member relative; it does not refuse it.

    Worth pinning because it is not what one would assume from the two cases
    above, and because the property that matters is not "it raised" but "nothing
    landed outside the destination". Both spellings satisfy that, by different
    routes, and a test asserting the wrong one of the two would fail the day the
    filter changed which route it took.
    """
    unpacked = install.unpack(_tar({"/absolute/escaped": b"payload"}), tmp_path / "into")

    assert not (tmp_path / "absolute").exists()
    assert (tmp_path / "into" / "absolute" / "escaped").read_bytes() == b"payload"
    assert all((tmp_path / "into") in path.parents for path in unpacked)


def test_a_symlink_leaving_the_destination_is_refused(tmp_path: Path) -> None:
    holder = io.BytesIO()
    with tarfile.open(fileobj=holder, mode="w:gz") as archive:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../../../etc/passwd"
        archive.addfile(info)

    with pytest.raises(CliFailure, match="could not be safely unpacked"):
        install.unpack(holder.getvalue(), tmp_path / "into")


def test_an_archive_that_unpacks_to_more_than_allowed_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(install, "MAX_UNPACKED_BYTES", 16)
    with pytest.raises(CliFailure, match="weigh"):
        install.unpack(_tar({"big": b"x" * 64}), tmp_path / "into")

    monkeypatch.setattr(install, "MAX_UNPACKED_BYTES", 1 << 30)
    monkeypatch.setattr(install, "MAX_MEMBERS", 2)
    with pytest.raises(CliFailure, match="more entries"):
        install.unpack(_tar({f"f{n}": b"x" for n in range(5)}), tmp_path / "into")


def test_a_zip_artifact_unpacks_by_the_same_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unpacked = install.unpack(_zip({"ruff": b"binary", "docs/readme": b"text"}), tmp_path / "into")
    assert {path.name for path in unpacked} == {"ruff", "docs", "readme"}

    # The same budgets apply: the format changes, the rules do not.
    monkeypatch.setattr(install, "MAX_MEMBERS", 1)
    with pytest.raises(CliFailure, match="more entries"):
        install.unpack(_zip({"a": b"1", "b": b"2"}), tmp_path / "other")


def test_a_zip_member_that_tries_to_escape_lands_inside_anyway(tmp_path: Path) -> None:
    # `zipfile` sanitises member names itself rather than refusing them, so the
    # check is where the bytes ended up, not whether it raised.
    install.unpack(_zip({"../escaped": b"payload"}), tmp_path / "into")
    assert not (tmp_path / "escaped").exists()
    assert (tmp_path / "into" / "escaped").exists()


def test_something_that_is_neither_a_zip_nor_a_tar_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CliFailure, match="could not be safely unpacked"):
        install.unpack(b"just some bytes", tmp_path / "into")


def test_a_failure_partway_through_leaves_the_previous_version_current(
    payload: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`REQ-1405`: preparation, the pointer switch and the return, in one run."""
    install.perform(RUFF, _artifact(payload), payload)
    first = install.current_target("ruff")

    newer = replace(RUFF, version="0.17.0")
    broken = _tar({"../escape": b"payload"})
    with pytest.raises(CliFailure, match="could not be safely unpacked"):
        install.perform(newer, _artifact(broken), broken)

    # The old installation is still there and still current, and the staging
    # directory the failed install used is gone.
    assert install.current_target("ruff") == first
    assert install.binary(RUFF).read_bytes().startswith(b"#!/bin/sh")
    assert not list(install.tool_dir("ruff").glob(".*staging"))


def test_a_rollback_with_nowhere_to_go_removes_the_pointer(payload: bytes) -> None:
    install.perform(RUFF, _artifact(payload), payload)
    assert install.pointer("ruff").exists()

    # A pointer aimed at nothing is worse than no pointer: only one of the two
    # is obviously wrong to whatever reads it next.
    assert "removed" in install.rollback("ruff", None)
    assert not install.pointer("ruff").is_symlink()
    assert install.current_target("ruff") is None


def test_a_rollback_returns_to_the_named_installation(payload: bytes) -> None:
    install.perform(RUFF, _artifact(payload), payload)
    first = install.current_target("ruff")
    assert first is not None

    newer = replace(RUFF, version="0.17.0")
    second = _tar({"ruff": b"#!/bin/sh\necho 0.17.0\n"})
    install.perform(newer, _artifact(second), second)
    assert install.current_target("ruff") != first

    assert "0.16.1" in install.rollback("ruff", first)
    assert install.current_target("ruff") == first


def test_the_pointer_swap_is_a_rename_onto_an_existing_link(payload: bytes) -> None:
    install.perform(RUFF, _artifact(payload), payload)
    link = install.pointer("ruff")
    assert link.is_symlink() if os.name != "nt" else link.is_file()

    other = install.installed_path("ruff", "0.17.0")
    other.mkdir(parents=True)
    install.activate(other, "ruff")

    # Replaced in place rather than removed and recreated, so there is no moment
    # when a concurrent invocation finds no pointer at all.
    assert link.is_symlink() if os.name != "nt" else link.is_file()
    assert install.current_target("ruff") == other
    assert not (link.parent / f".{install.CURRENT}.staging").exists()


def test_a_broken_pointer_is_reported_as_nothing_rather_than_raising() -> None:
    link = install.pointer("ruff")
    link.parent.mkdir(parents=True)
    if os.name == "nt":
        link.write_text(
            f"path:{install.installed_path('ruff', 'never-installed')}", encoding="utf-8"
        )
    else:
        link.symlink_to(install.installed_path("ruff", "never-installed"))
    assert install.current_target("ruff") is not None

    link.unlink()
    link.write_text("not a symlink", encoding="utf-8")
    assert install.current_target("ruff") is None


def test_uninstall_removes_only_what_the_manifest_claims(payload: bytes) -> None:
    """`REQ-1411`: a user's own file inside the tool directory survives."""
    target, _ = install.perform(RUFF, _artifact(payload), payload)
    theirs = target / "notes-from-the-user.txt"
    theirs.write_text("mine", encoding="utf-8")

    removed, kept = install.remove("ruff")

    assert any("ruff" in item for item in removed)
    assert theirs.exists()
    assert any("notes-from-the-user" in item for item in kept)
    # And the manifest no longer claims what is gone.
    assert not any("0.16.1" in item for item in install.owned())


def test_uninstall_leaves_the_cache_and_other_tools_alone(payload: bytes) -> None:
    install.perform(RUFF, _artifact(payload), payload)
    other = replace(RUFF, tool_id="mypy")
    other_payload = _tar({"ruff": b"other"})
    install.perform(other, _artifact(other_payload), other_payload)

    install.remove("ruff")

    assert install.current_target("mypy") is not None
    # The cache is verified content addressed by digest, and keeping it is what
    # makes a reinstall work with no network (`REQ-1412`).
    assert list(install.cache_dir().iterdir())


def test_an_unreadable_ownership_manifest_claims_nothing(payload: bytes) -> None:
    install.perform(RUFF, _artifact(payload), payload)
    (install.root() / install.OWNERSHIP).write_text("{ not json", encoding="utf-8")

    # Claiming nothing means removing nothing. A corrupt manifest that was read
    # optimistically would delete by guesswork.
    assert install.owned() == []
    removed, kept = install.remove("ruff")
    assert removed == []
    assert kept


def test_nothing_here_needs_elevated_privileges(payload: bytes) -> None:
    """`REQ-1410`: an ordinary install writes under the user's own directory."""
    target, created = install.perform(RUFF, _artifact(payload), payload)
    home = Path(os.environ["HOME"]).resolve()
    for path in [target, *created, install.cache_dir(), install.root()]:
        assert home in path.resolve().parents or path.resolve() == home


def test_the_install_command_reports_the_exact_binary_and_what_it_created(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    from ai_stp_cli.commands import toolchain as command

    _pin(monkeypatch, command, payload, serve=payload)

    first = command.install_tool({"tool": "ruff"}).payload
    assert first.action == "installed"
    assert first.binary
    normalized_binary = first.binary.replace("\\", "/")
    expected_suffix = (
        "/toolchain/tools/ruff/0.16.1/ruff"
        if os.name == "nt"
        else "/toolchain/tools/ruff/current/ruff"
    )
    assert normalized_binary.endswith(expected_suffix)
    assert first.paths
    # `redact_home` on every path: an answer a harness may log should not carry
    # the user's home directory through it.
    assert all(not path.startswith("/home") for path in first.paths)

    second = command.install_tool({"tool": "ruff"}).payload
    assert second.action == "already_installed"


def test_the_install_command_uses_the_cache_before_the_network(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    from ai_stp_cli.commands import toolchain as command

    install.remember(payload, _digest(payload))
    _pin(monkeypatch, command, payload)
    assert command.install_tool({"tool": "ruff"}).payload.action == "installed"


def test_the_install_command_offline_asks_the_user_rather_than_reaching_out(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    from ai_stp_cli.commands import toolchain as command

    _pin(monkeypatch, command, payload)
    answer = command.install_tool({"tool": "ruff", "offline": True}).payload
    # `REQ-1410`: an exact statement of what is missing, and no attempt to
    # obtain anything on the user's behalf.
    assert answer.action == "needs_user_action"
    assert answer.offline_capable is False


def test_the_commands_refuse_a_tool_the_profile_does_not_pin() -> None:
    from ai_stp_cli.commands import toolchain as command

    with pytest.raises(CliFailure, match="pins no tool called"):
        command.install_tool({"tool": "not-a-real-tool"})
    with pytest.raises(CliFailure, match="a tool id is required"):
        command.install_tool({})
    with pytest.raises(CliFailure, match="a tool id is required"):
        command.remove_tool({})


def test_the_remove_command_reports_both_sides_of_the_manifest(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    from ai_stp_cli.commands import toolchain as command

    _pin(monkeypatch, command, payload, serve=payload)
    command.install_tool({"tool": "ruff"})
    (install.installed_path("ruff", "0.16.1") / "theirs.txt").write_text("mine", encoding="utf-8")

    answer = command.remove_tool({"tool": "ruff", "confirm": True}).payload
    assert answer.action == "removed"
    assert answer.paths
    assert any("theirs.txt" in item for item in answer.kept)


#: The canonical pinned form and the signed CDN URL GitHub answers it with.
_RELEASE = "https://github.com/astral-sh/ruff/releases/download/0.16.1/ruff-win.zip"
_SIGNED = (
    "https://release-assets.githubusercontent.com/github-production-release-asset/1/2"
    "?response-content-disposition=attachment%3B%20filename%3Druff-win.zip"
)


def test_a_release_asset_redirect_is_followed_once_and_only_to_the_same_asset() -> None:
    """GitHub answers every release asset with a redirect, so refusing all of them
    made the canonical pinned form unusable: a Windows `toolchain install --tool
    ruff` could not fetch the asset at all and the managed toolchain stayed
    empty on that platform (`#376`).

    What makes the hop safe is not trust in it. The source has to be a GitHub
    release download, the target has to be `https` on a host from the closed
    set, and it has to still name the same asset. The digest is checked after
    the bytes arrive and before anything is unpacked, which this does not touch.
    """
    import httpx

    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "release-assets.githubusercontent.com":
            return httpx.Response(200, content=b"artifact bytes")
        return httpx.Response(302, headers={"Location": _SIGNED})

    assert install.download(_RELEASE, transport=httpx.MockTransport(handle)) == b"artifact bytes"
    assert [request.url.host for request in seen] == [
        "github.com",
        "release-assets.githubusercontent.com",
    ]
    assert all("authorization" not in request.headers for request in seen)
    assert all("x-ai-stp-schema-version" not in request.headers for request in seen)


@pytest.mark.parametrize(
    ("source", "location", "reason"),
    [
        # Not a release asset at all: a pinned URL that redirects is no longer
        # the source that was pinned.
        ("https://example.test/moved", "https://example.test/a", "not_a_release_asset"),
        # A foreign host, however plausible.
        (_RELEASE, "https://elsewhere.test/ruff-win.zip", "host"),
        # The downgrade this refusal exists for.
        (_RELEASE, _SIGNED.replace("https://", "http://"), "scheme"),
        # Same host, different asset.
        (
            _RELEASE,
            _SIGNED.replace("ruff-win.zip", "something-else.zip"),
            "different_asset",
        ),
    ],
)
def test_a_redirect_outside_the_closed_set_is_refused_with_a_way_forward(
    source: str, location: str, reason: str
) -> None:
    """Every refusal names a next action; a bare 302 left an agent guessing."""
    import httpx

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": location})

    with pytest.raises(CliFailure) as refused:
        install.download(source, transport=httpx.MockTransport(handle))

    assert refused.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert reason in str(refused.value.details)
    assert refused.value.next_actions


def test_the_client_never_follows_redirects_on_its_own() -> None:
    """The hop is taken by hand or not at all."""
    source = Path(install.__file__).read_text(encoding="utf-8")
    assert "follow_redirects=False" in source
    assert "follow_redirects=True" not in source


def test_a_download_that_fails_or_oversteps_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(CliFailure, match="could not be fetched") as raised:
        install.download("https://example.test/a", transport=httpx.MockTransport(broken))
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"

    monkeypatch.setattr(install, "MAX_ARTIFACT_BYTES", 4)
    big = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 64))
    with pytest.raises(CliFailure, match="larger than one may be"):
        install.download("https://example.test/a", transport=big)


def test_a_leftover_staging_directory_from_a_crash_is_cleared_first(payload: bytes) -> None:
    # A previous run that died between unpacking and the pointer swap leaves one
    # of these behind. Reusing it would install a mixture of two archives.
    target = install.installed_path("ruff", "0.16.1")
    staging = target.with_name(f".{target.name}.staging")
    staging.mkdir(parents=True)
    (staging / "left-over-from-a-crash").write_text("stale", encoding="utf-8")

    installed, _ = install.perform(RUFF, _artifact(payload), payload)

    assert not (installed / "left-over-from-a-crash").exists()
    assert (installed / "ruff").exists()


def test_reinstalling_over_an_unpacked_but_uncurrent_version_replaces_it(payload: bytes) -> None:
    target = install.installed_path("ruff", "0.16.1")
    target.mkdir(parents=True)
    (target / "half-written").write_text("from an interrupted run", encoding="utf-8")
    assert install.current_target("ruff") is None

    installed, _ = install.perform(RUFF, _artifact(payload), payload)

    # Replaced rather than merged: an installation is the archive's contents, not
    # the archive's contents plus whatever survived a previous attempt.
    assert not (installed / "half-written").exists()
    assert (installed / "ruff").exists()


def test_a_pointer_that_cannot_be_read_is_reported_as_nothing(
    payload: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    install.perform(RUFF, _artifact(payload), payload)

    def refuse(self: Path, *_args: object, **_kwargs: object) -> Path:
        raise OSError("the link went away between the two calls")

    monkeypatch.setattr(Path, "read_text" if os.name == "nt" else "readlink", refuse)
    # A pointer that exists at `is_symlink()` and is gone at `readlink()` is an
    # ordinary race, not an error worth failing a read over.
    assert install.current_target("ruff") is None


def test_an_ownership_manifest_that_is_not_a_list_claims_nothing(payload: bytes) -> None:
    install.perform(RUFF, _artifact(payload), payload)
    (install.root() / install.OWNERSHIP).write_text('{"paths": ["/etc"]}', encoding="utf-8")

    # Valid JSON of the wrong shape. Reading it optimistically would treat the
    # key as a path and remove by guesswork.
    assert install.owned() == []


def test_a_tool_pinned_only_for_another_platform_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli import toolchain as manifest_module
    from ai_stp_cli.commands import toolchain as command

    # Captured before the patch: a replacement built by calling the thing it
    # replaces is a replacement that calls itself.
    real = manifest_module.load().tools[0]
    narrowed = replace(
        manifest_module.load(),
        tools=(replace(real, artifacts={"linux-aarch64": real.artifacts["linux-x86_64"]}),),
    )
    monkeypatch.setattr(manifest_module, "current_platform", lambda: "darwin-arm64")
    monkeypatch.setattr(manifest_module, "load", lambda: narrowed)

    with pytest.raises(CliFailure, match="pinned, but nothing for darwin-arm64") as raised:
        command.install_tool({"tool": real.tool_id})
    assert raised.value.details["available"] == "linux-aarch64"


def test_resolving_a_pinned_tool_finds_the_artifact_for_this_machine() -> None:
    """The happy path of the resolution itself, which every other test replaces.

    Worth its own test precisely because the command tests patch `pinned_for`
    away: without this, the only untested thing left would be the one piece of
    logic that decides which bytes get installed.
    """
    from ai_stp_cli import toolchain as manifest_module
    from ai_stp_cli.commands import toolchain as command

    pinned = manifest_module.load().tools[0]
    tool, artifact = command.pinned_for(pinned.tool_id)

    assert tool.tool_id == pinned.tool_id
    # Equal, not identical: `load` parses the manifest afresh on each call.
    assert artifact == pinned.artifacts[manifest_module.current_platform()]
    assert artifact.url.startswith("https://")
    assert artifact.digest.startswith("sha256:")
