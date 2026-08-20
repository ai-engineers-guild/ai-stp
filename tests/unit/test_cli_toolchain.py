"""The pinned toolchain manifest: mostly a set of refusals, on purpose."""

import platform
from pathlib import Path

import pytest

from ai_stp_cli import toolchain
from ai_stp_cli.errors import CliFailure

GOOD = """
schema_version = 1
profile = "mvp-full"

[ecosystems]
python = "Python"

[[tools]]
id = "ruff"
ecosystem = "python"
purpose = "linter"
version = "0.16.1"
license = "MIT"
entry_point = "ruff"
digest_source = "vendor_published"

[tools.artifacts.linux-x86_64]
url = "https://example.test/ruff/0.16.1/ruff.tar.gz"
digest = "sha256:{digest}"
""".format(digest="0" * 64)


def _without(field: str) -> str:
    return "\n".join(line for line in GOOD.splitlines() if not line.startswith(f"{field} ="))


def test_the_shipped_manifest_is_valid_and_covers_five_ecosystems() -> None:
    # `REQ-1407`: the profile covers Python, TypeScript/JavaScript, Rust, Go and
    # Dart/Flutter. An ecosystem nothing is pinned for is still declared.
    manifest = toolchain.load()
    assert manifest.profile == toolchain.PROFILE
    assert set(manifest.ecosystems) == {"python", "typescript", "rust", "go", "dart"}
    assert manifest.tools


def test_every_pinned_tool_states_everything_the_requirement_asks_for() -> None:
    # `REQ-1403`: exact version, exact source, integrity proof, licence and the
    # systems it supports.
    for tool in toolchain.load().tools:
        assert tool.version and not any(character in tool.version for character in "^~*<>= ")
        assert tool.license
        assert tool.artifacts
        for name, artifact in tool.artifacts.items():
            assert name in toolchain.SUPPORTED_PLATFORMS
            assert artifact.url.startswith("https://")
            assert tool.version in artifact.url
            assert artifact.digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        # A URL that resolves to something different tomorrow is not a pinned
        # dependency, however precise its checksum looks.
        (
            (
                "https://example.test/ruff/0.16.1/ruff.tar.gz",
                "https://example.test/latest/r.tar.gz",
            ),
            "floating source",
        ),
        # No integrity proof at all.
        (("sha256:" + "0" * 64, ""), "no usable integrity proof"),
        # A truncated one, which looks like a proof and is not.
        (("sha256:" + "0" * 64, "sha256:abc"), "no usable integrity proof"),
        # A range is not a version.
        (('version = "0.16.1"', 'version = "^0.16"'), "version range rather than a version"),
        # Plain HTTP for something whose integrity we then assert.
        (("https://example.test/ruff", "http://example.test/ruff"), "other than HTTPS"),
        # A source that does not name the version it claims to pin.
        (
            ("https://example.test/ruff/0.16.1/ruff.tar.gz", "https://example.test/r/r.tar.gz"),
            "does not pin 0.16.1",
        ),
        # A platform nobody supports.
        (
            ("[tools.artifacts.linux-x86_64]", "[tools.artifacts.solaris-sparc]"),
            "unsupported platform",
        ),
        # An ecosystem the manifest never declared.
        (('ecosystem = "python"', 'ecosystem = "cobol"'), "undeclared ecosystem"),
        # An integrity provenance that is neither of the two meanings.
        (
            ('digest_source = "vendor_published"', 'digest_source = "trust me"'),
            "unknown integrity provenance",
        ),
        # A manifest written for another build.
        (("schema_version = 1", "schema_version = 9"), "reads toolchain manifest schema 1"),
    ],
)
def test_an_under_specified_entry_is_refused_and_says_where(
    mutation: tuple[str, str], expected: str
) -> None:
    before, after = mutation
    with pytest.raises(CliFailure, match=expected) as raised:
        toolchain.parse(GOOD.replace(before, after))
    # Naming the field is the difference between a message a person can act on
    # and one that makes them guess.
    assert raised.value.details["at"]
    assert raised.value.exit_code == 2


@pytest.mark.parametrize(
    "field", ["ecosystem", "purpose", "version", "license", "entry_point", "digest_source"]
)
def test_a_missing_required_field_is_named(field: str) -> None:
    with pytest.raises(CliFailure, match=f"declares no {field}"):
        toolchain.parse(_without(field))


def test_a_tool_with_no_platform_at_all_is_refused() -> None:
    stripped = GOOD.split("[tools.artifacts.linux-x86_64]")[0]
    with pytest.raises(CliFailure, match="supports no platform"):
        toolchain.parse(stripped)


def test_a_manifest_that_is_not_toml_or_has_no_ecosystems_is_refused() -> None:
    with pytest.raises(CliFailure, match="not valid TOML"):
        toolchain.parse("this is [not toml")
    with pytest.raises(CliFailure, match="declares no ecosystems"):
        toolchain.parse("schema_version = 1\nprofile = 'mvp-full'\n")


def test_a_tool_declared_twice_is_refused() -> None:
    doubled = GOOD + GOOD.split("[[tools]]", 1)[1].join(["[[tools]]", ""])
    with pytest.raises(CliFailure, match="declared twice"):
        toolchain.parse(doubled)


def test_the_profile_is_the_same_whatever_the_project_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`REQ-1402`, checked from two genuinely different working directories.

    An empty project and a documentation project resolve to the same profile,
    because what a developer needs installed is not deducible from what they
    have written so far. `monkeypatch.chdir` rather than `os.chdir`: a test that
    leaves the process somewhere else is a test that breaks the next one.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    documented = tmp_path / "documented"
    documented.mkdir()
    (documented / "README.md").write_text("# hello", encoding="utf-8")

    manifest = toolchain.load()
    target = toolchain.current_platform()

    resolved: list[tuple[str, ...]] = []
    for place in (empty, documented):
        monkeypatch.chdir(place)
        resolved.append(
            tuple(f"{item.ecosystem}:{item.state}" for item in toolchain.plan(manifest, target))
        )
    assert resolved[0] == resolved[1]


def test_an_ecosystem_with_nothing_pinned_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = toolchain.load()
    plans = {item.ecosystem: item for item in toolchain.plan(manifest, "linux-x86_64")}
    assert plans["python"].state == "available"
    for ecosystem in ("typescript", "rust", "go", "dart"):
        assert plans[ecosystem].state == "not_available"
        assert plans[ecosystem].reason

    # And an ecosystem whose tool exists but not for this platform says a
    # different thing, because those are different problems.
    elsewhere = {item.ecosystem: item for item in toolchain.plan(manifest, "darwin-x86_64")}
    assert elsewhere["python"].state == "available"


def test_a_tool_pinned_for_another_platform_only_is_reported_as_such() -> None:
    narrow = GOOD.replace("[tools.artifacts.linux-x86_64]", "[tools.artifacts.darwin-arm64]")
    manifest = toolchain.parse(narrow)
    plans = {item.ecosystem: item for item in toolchain.plan(manifest, "linux-x86_64")}
    assert plans["python"].state == "not_available"
    assert "nothing pinned for linux-x86_64" in (plans["python"].reason or "")


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", "linux-x86_64"),
        ("Linux", "aarch64", "linux-aarch64"),
        ("Linux", "arm64", "linux-aarch64"),
        ("Darwin", "arm64", "darwin-arm64"),
        ("Darwin", "x86_64", "darwin-x86_64"),
    ],
)
def test_one_machine_has_one_name(
    system: str, machine: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same hardware answers `arm64` on macOS and `aarch64` on Linux.
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert toolchain.current_platform() == expected


def test_an_unsupported_system_is_refused_rather_than_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "FreeBSD")
    monkeypatch.setattr(platform, "machine", lambda: "amd64")
    with pytest.raises(CliFailure, match="no managed toolchain") as raised:
        toolchain.current_platform()
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_windows_x64_has_a_managed_toolchain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    assert toolchain.current_platform() == "windows-x86_64"


def test_the_command_reports_every_ecosystem_including_the_empty_ones() -> None:
    from ai_stp_cli.commands import toolchain as toolchain_command

    answer = toolchain_command.profile({}).payload
    assert answer.profile == "mvp-full"
    assert len(answer.ecosystems) == 5
    python = next(item for item in answer.ecosystems if item.ecosystem == "python")
    assert python.state == "available"
    assert python.tools[0].digest_source == "vendor_published"
    assert python.tools[0].source.startswith("https://")
    empty = [item for item in answer.ecosystems if item.state == "not_available"]
    assert empty and all(item.reason for item in empty)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Every shape a hand-edited manifest can take wrongly, each named.
        # `tools` stands before the table header on purpose: in TOML everything
        # after `[ecosystems]` belongs to that table until the next header, so
        # writing it below would declare an ecosystem rather than a tool list.
        (
            "schema_version = 1\ntools = 'ruff'\n[ecosystems]\npython = 'Python'\n",
            "tools in the wrong shape",
        ),
        ("schema_version = 1\ntools = ['ruff']\n[ecosystems]\npython = 'Python'\n", "not a table"),
        (
            "schema_version = 1\n[ecosystems]\npython = 'Python'\n[[tools]]\nname = 'ruff'\n",
            "no identifier",
        ),
    ],
)
def test_a_malformed_manifest_names_the_shape_that_is_wrong(text: str, expected: str) -> None:
    with pytest.raises(CliFailure, match=expected):
        toolchain.parse(text)


def test_a_malformed_artifact_table_names_its_platform() -> None:
    broken = GOOD.replace(
        '[tools.artifacts.linux-x86_64]\nurl = "https://example.test/ruff/0.16.1/ruff.tar.gz"\n'
        'digest = "sha256:' + "0" * 64 + '"',
        '[tools.artifacts]\nlinux-x86_64 = "just a string"',
    )
    with pytest.raises(CliFailure, match="malformed artifact for linux-x86_64"):
        toolchain.parse(broken)
