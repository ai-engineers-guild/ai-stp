"""The CLI as a real process: streams, exit codes and a golden registry.

Everything here runs `ai-stp` through a subprocess rather than calling `main`.
An in-process test shares the interpreter's streams and its installed packages,
so it cannot see a byte written straight to file descriptor 1 by a library, an
import that only fails from the console script, or an exit code the shell
actually observes. Those are the parts of `#72` a caller depends on.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest
from jsonschema import Draft202012Validator

from ai_stp_cli.commands import machine_help
from ai_stp_cli.registry import COMMANDS

#: How long one invocation may take before the wait itself is the failure.
#: Generous for a slow runner and finite on purpose: an unbounded wait turns
#: a blocked child into a job that ends at its own ceiling with nothing to
#: show, which is how a missing credential-store pin cost four macOS runs
#: before anything named it.
INVOCATION_SECONDS: Final[int] = 300

GOLDEN = Path(__file__).parents[1] / "golden" / "cli" / "machine-help.json"
SCHEMAS = Path(__file__).parents[2] / "schemas" / "v1"

#: Any ANSI control sequence. Machine stdout must contain none: a caller pipes
#: it into a JSON parser, not into a terminal.
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

#: Replaces the version in the golden registry. The fixture pins which commands
#: and flags exist; pinning the build number too would turn every release into
#: an unrelated diff.
PINNED_VERSION = "0.0.0-pinned"


def run(*argv: str, home: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
        "USERPROFILE": str(home),
        # Force the widest possible interpretation of "no colour": if anything
        # ever decided to colourise, this is the switch it would ignore.
        "FORCE_COLOR": "1",
        # No session bus, so the operating system credential store is genuinely
        # unreachable: this is the SSH-and-container situation the fallback
        # exists for, and it must never reach the developer's real keyring.
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent",
        # Windows (and any host with a trusted OS keyring) still opens the
        # locker when DBUS is irrelevant. Pin the file tier so process tests
        # plant secrets under XDG and never touch the host Credential Locker.
        "AI_STP_FORCE_FILE_CREDENTIAL_STORE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "ai_stp_cli", *argv],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        timeout=INVOCATION_SECONDS,
    )


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A clean installation whose catalogue address resolves nowhere.

    Pinned rather than inherited. These checks were written when the shipped
    `catalog.url` was `https://ai-stp.example`, and several of them mean "no
    platform" — an offline machine meeting a typed refusal. They said so by
    saying nothing, and relied on the default being unusable.

    The default is the deployment now, so inheriting it would point this suite
    at production: real requests, from a test run, against the live catalogue.
    `.example` is reserved by RFC 2606 for exactly this and belongs here, in the
    test that wants an address which cannot answer, rather than in the value a
    person gets before configuring anything.
    """
    settings = tmp_path / "config" / "ai-stp" / "config.yaml"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text('catalog:\n  url: "https://ai-stp.example"\n', encoding="utf-8")
    return tmp_path


@pytest.fixture
def ready(home: Path) -> Path:
    """A home where the installation exists, which is what a read command reads.

    The read commands used to create what they reported, so a clean directory
    was enough to exercise them. Now that creating names itself, reading an
    installation that was never set up is a typed `AI_STP_NOT_FOUND` — correct,
    and not what these checks are about.
    """
    run("device", "init", "--json", home=home)
    run("passport", "developer", "init", "--json", home=home)
    run("passport", "device", "refresh", "--json", home=home)
    return home


#: Every command that answers without changing anything. Kept as one list so a
#: new read command is covered by all of the process-level checks at once.
READ_COMMANDS = [
    ("version",),
    ("passport", "device", "show"),
    ("doctor",),
    ("capabilities",),
    ("config", "show"),
    ("help", "--agent"),
    ("auth", "status"),
    ("device", "show"),
    ("install", "status"),
    ("consent", "list"),
    ("component", "find"),
]

#: Commands that create durable local state. Kept apart from the read list so a
#: read command cannot quietly join it.
WRITE_COMMANDS = [
    ("device", "init"),
    ("passport", "developer", "init"),
    ("passport", "device", "refresh"),
]


@pytest.mark.parametrize("argv", READ_COMMANDS)
def test_machine_stdout_is_exactly_one_json_object_and_stderr_is_empty(
    argv: tuple[str, ...], ready: Path
) -> None:
    result = run(*argv, "--json", home=ready)
    assert result.returncode == 0
    assert result.stderr == ""
    assert not ANSI.search(result.stdout)
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["schema_version"] == 1


def test_a_refused_invocation_exits_two_with_an_envelope_on_stdout(home: Path) -> None:
    result = run("nope", "--json", home=home)
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"]["code"] == "AI_STP_VALIDATION_ERROR"


def test_a_human_failure_writes_stderr_and_leaves_stdout_empty(home: Path) -> None:
    result = run("nope", home=home)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("AI_STP_VALIDATION_ERROR: ")


def test_an_empty_human_invocation_opens_first_run_help(home: Path) -> None:
    result = run(home=home)
    assert result.returncode == 0
    assert result.stderr == ""
    assert "Usage: ai-stp" in result.stdout
    assert "ai-stp doctor --json" in result.stdout
    assert "ai-stp help --agent --json" in result.stdout


def test_auth_help_and_machine_registry_expose_provider_choices(home: Path) -> None:
    help_result = run("auth", "--help", home=home)
    assert help_result.returncode == 0
    assert help_result.stderr == ""
    assert "ai-stp auth login --provider google" in help_result.stdout
    assert "ai-stp auth login --provider github" in help_result.stdout

    registry_result = run("help", "--agent", "--json", home=home)
    commands = json.loads(registry_result.stdout)["data"]["commands"]
    login = next(command for command in commands if command["path"] == ["auth", "login"])
    provider = next(item for item in login["parameters"] if item["name"] == "provider")
    assert provider["choices"] == ["google", "github"]


@pytest.mark.parametrize(
    "argv",
    [
        ("auth", "login"),
        ("auth", "login", "--google"),
        ("auth", "login", "--provider", "gitlab"),
        ("auth", "google", "login"),
    ],
)
def test_auth_usage_failures_are_actionable_in_machine_mode(
    argv: tuple[str, ...], home: Path
) -> None:
    result = run(*argv, "--json", home=home)
    assert result.returncode == 2
    assert result.stderr == ""
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"
    assert envelope["next_actions"] == [
        "auth login --provider google --json",
        "auth login --provider github --json",
    ]


@pytest.mark.parametrize(
    ("argv", "names"),
    [
        (("auth", "login", "--provider", "google", "--bogus"), "--bogus"),
        (("auth", "login", "--provider", "github", "--bogus"), "--bogus"),
        (("auth", "login", "--provider", "google", "--provider"), "--provider"),
    ],
)
def test_a_correct_provider_is_never_blamed_for_someone_else_s_mistake(
    argv: tuple[str, ...], names: str, home: Path
) -> None:
    """The repair instruction must point at the argument that is wrong.

    Every parse failure under `auth login` used to end at the same sentence,
    "auth login requires --provider with google or github" — including the
    calls above, which supply a valid provider and fail for an unrelated
    reason. An agent told to fix `--provider` edits the one argument that was
    already right, and the envelope is valid JSON while it says so.

    The cases the adapter still owns are covered above: an absent provider, an
    unsupported one, and the reversed word order.
    """
    result = run(*argv, "--json", home=home)
    assert result.returncode == 2
    assert result.stderr == ""
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "AI_STP_VALIDATION_ERROR"
    message = envelope["error"]["message"]
    assert names in message, message
    assert "requires --provider" not in message, message
    assert envelope["error"]["details"].get("parameter") != "provider"


def test_the_auth_repair_offers_exactly_the_declared_providers(home: Path) -> None:
    """The suggestion is read from the registry, not restated beside it."""
    declared = next(
        parameter.choices
        for command in COMMANDS
        if command.descriptor.path == ["auth", "login"]
        for parameter in command.descriptor.parameters
        if parameter.name == "provider"
    )
    envelope = json.loads(run("auth", "login", "--json", home=home).stdout)
    assert envelope["next_actions"] == [f"auth login --provider {name} --json" for name in declared]
    assert envelope["error"]["details"]["allowed"] == ", ".join(declared)


def test_a_portable_root_skill_is_discovered_and_adopted_by_exact_path(home: Path) -> None:
    repository = home / "portable-skill"
    repository.mkdir()
    manifest = repository / "SKILL.md"
    manifest.write_text("# portable\n", encoding="utf-8")

    discovered = run("component", "discover", "--root", str(repository), "--json", home=home)
    assert discovered.returncode == 0
    candidates = json.loads(discovered.stdout)["data"]["components"]
    portable = next(item for item in candidates if item["source_path"].endswith("SKILL.md"))
    assert portable["component_type"] == "skill"
    assert portable["harness_id"] is None
    assert portable["layout_source"] == "agentskills.io/specification"

    adopted = run(
        "component",
        "adopt",
        "--root",
        str(repository),
        "--path",
        str(manifest),
        "--json",
        home=home,
    )
    assert adopted.returncode == 0
    passport = json.loads(adopted.stdout)["data"]
    assert passport["stable_id"].startswith("component_")
    assert passport["facts"]["component_type"]["value"] == "skill"

    quality = run(
        "component",
        "passport",
        "quality",
        "--id",
        passport["stable_id"],
        "--json",
        home=home,
    )
    assert quality.returncode == 0
    report = json.loads(quality.stdout)["data"]
    Draft202012Validator(
        json.loads((SCHEMAS / "cli-component-quality-report.schema.json").read_text("utf-8"))
    ).validate(report)  # pyright: ignore[reportUnknownMemberType]
    assert report["informational_only"] is True
    assert report["affects_component_verified"] is False


def test_doctor_exits_zero_on_a_machine_that_is_not_set_up(home: Path) -> None:
    # A non-zero exit here would make the first run after installation look
    # broken and would stop any caller running under `set -e`.
    result = run("doctor", "--json", home=home)
    assert result.returncode == 0
    assert json.loads(result.stdout)["data"]["state"] == "needs_user_action"


def test_the_installed_console_script_is_the_same_program(home: Path) -> None:
    # `python -m` and the console script can diverge — a broken entrypoint only
    # shows up through the script the user actually types.
    script = Path(sys.executable).parent / "ai-stp"
    if not script.exists():
        pytest.skip("console script is not installed in this environment")
    result = subprocess.run(
        [str(script), "version", "--json"],
        capture_output=True,
        text=True,
        env={**os.environ, "XDG_CONFIG_HOME": str(home / "config")},
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["data"]["cli_version"]


def _pinned(document: dict[str, Any]) -> dict[str, Any]:
    return {**document, "cli_version": PINNED_VERSION}


def test_the_command_registry_matches_its_golden_fixture(home: Path) -> None:
    # The registry is a machine boundary five harness projections read. Adding,
    # renaming or re-describing a command has to show up as a reviewed diff
    # rather than as a silent change under a passing suite.
    result = run("help", "--agent", "--json", home=home)
    live = _pinned(json.loads(result.stdout)["data"])
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert live == expected


def test_the_golden_fixture_matches_the_registry_in_process() -> None:
    # The same comparison without a subprocess, so a failure says whether the
    # registry changed or the process wrapper did.
    live = _pinned(machine_help.registry({}).payload.model_dump(mode="json"))
    assert live == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_report_preview_is_process_visible_and_confirm_still_requires_a_person(home: Path) -> None:
    digest = "sha256:" + "b" * 64
    preview = run(
        "report",
        "preview",
        "--kind",
        "component",
        "--id",
        "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "--version",
        "1.0",
        "--content-digest",
        digest,
        "--idempotency-key",
        "report-process-012345",
        "--json",
        home=home,
    )
    assert preview.returncode == 0
    planned = json.loads(preview.stdout)["data"]
    assert planned["report"]["content_digest"] == digest
    assert planned["report"]["diagnostics"] == ""

    undecided = run(
        "report",
        "confirm",
        "--plan-id",
        planned["plan_id"],
        "--plan-digest",
        planned["plan_digest"],
        "--json",
        home=home,
    )
    assert undecided.returncode == 4
    assert json.loads(undecided.stdout)["error"]["code"] == "AI_STP_USER_DECISION_REQUIRED"


@pytest.mark.parametrize(
    ("argv", "schema"),
    [
        (("version",), "cli-version-report"),
        (("doctor",), "cli-doctor-report"),
        (("capabilities",), "cli-capabilities"),
        (("config", "show"), "cli-config-report"),
        (("help", "--agent"), "cli-machine-help"),
        (("auth", "status"), "cli-auth-status"),
        (("device", "show"), "cli-device-identity"),
        (("passport", "developer", "init"), "cli-passport-view"),
        (("passport", "device", "show"), "cli-passport-view"),
        (
            (
                "link",
                "web",
                "--kind",
                "component",
                "--id",
                "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
                "--version",
                "1.0",
            ),
            "cli-deep-link",
        ),
    ],
)
def test_what_the_process_emits_validates_against_the_published_schema(
    argv: tuple[str, ...], schema: str, ready: Path
) -> None:
    # The models produce both the payload and the schema, so validating one
    # against the other in memory would prove nothing. This reads the schema
    # committed under `schemas/v1` — the file a consumer in another language
    # actually has — and checks the bytes a real process wrote.
    published = json.loads(
        (SCHEMAS / f"{schema}.schema.json").read_text(encoding="utf-8"),
    )
    result = run(*argv, "--json", home=ready)
    validator = Draft202012Validator(published)  # pyright: ignore[reportArgumentType]
    validator.validate(json.loads(result.stdout)["data"])  # pyright: ignore[reportUnknownMemberType]


def test_every_command_declaring_a_result_schema_has_one_published() -> None:
    # A `result_schema` naming a URN with no file behind it sends an agent
    # looking for a contract that was never shipped.
    for descriptor in machine_help.registry({}).payload.commands:
        if descriptor.result_schema is None:
            continue
        name = descriptor.result_schema.removeprefix("urn:ai-stp:schema:v1:")
        assert (SCHEMAS / f"{name}.schema.json").exists(), descriptor.result_schema


def test_a_clean_home_gets_a_working_installation_without_sudo(home: Path) -> None:
    # The first-run acceptance criterion, exercised as a user meets it: nothing
    # exists, one command runs, and the layout it creates is owner-only.
    assert not (home / "data").exists()
    result = run("device", "init", "--json", home=home)
    assert result.returncode == 0

    data = home / "data" / "ai-stp"
    device_file = data / "device.json"
    assert device_file.exists()
    if os.name != "nt":
        # POSIX-only: Windows ACLs govern access; st_mode is not 0o600/0o700.
        assert stat.S_IMODE(device_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(data.stat().st_mode) == 0o700
        for secret in (data / "secrets").glob("*.secret"):
            assert stat.S_IMODE(secret.stat().st_mode) == 0o600


def test_a_second_run_changes_nothing(home: Path) -> None:
    first = json.loads(run("device", "init", "--json", home=home).stdout)["data"]
    second = json.loads(run("device", "show", "--json", home=home).stdout)["data"]
    assert first == second


def test_no_command_puts_key_material_on_either_stream(home: Path) -> None:
    # `SPEC-011` REQ-1108 as a process-level check: the private key is read from
    # disk and never appears in what the process writes.
    shown = run("device", "init", "--json", home=home)
    device_id = json.loads(shown.stdout)["data"]["device_id"]
    # The key is stored under the device it belongs to, so the name is derived
    # rather than assumed: a shared name is what let one installation overwrite
    # another's key.
    secret_path = home / "data" / "ai-stp" / "secrets" / f"device-key.{device_id}.secret"
    if not secret_path.exists():
        # File-tier oracle: Linux CI forces the file tier through a broken D-Bus.
        # On Windows, and on any host with a trusted OS keyring, the seed is not
        # on disk at all, so this process-level harvest cannot run.
        pytest.skip("file-tier secret absent; OS keyring holds the seed on this host")
    seed = secret_path.read_text(encoding="utf-8")
    material = json.loads(seed)["seed"]
    assert material

    for argv in READ_COMMANDS:
        result = run(*argv, "--json", home=home)
        assert material not in result.stdout, argv
        assert material not in result.stderr, argv
        assert "seed" not in result.stdout, argv


def test_output_carries_no_home_path_material(home: Path) -> None:
    # `#73` requires home-path material out of output. The check is run against
    # a home the process really uses, so a leak would be visible.
    result = run("config", "show", "--json", home=home)
    payload = json.loads(result.stdout)["data"]
    rendered = json.dumps(payload)
    assert str(Path.home()) not in rendered


def test_a_reset_needs_confirmation_and_then_replaces_the_identity(home: Path) -> None:
    before = json.loads(run("device", "init", "--json", home=home).stdout)["data"]

    refused = run("device", "reset", "--json", home=home)
    assert refused.returncode == 4
    assert json.loads(refused.stdout)["error"]["code"] == "AI_STP_USER_DECISION_REQUIRED"

    done = run("device", "reset", "--confirm", "--json", home=home)
    assert done.returncode == 0
    after = json.loads(done.stdout)["data"]
    assert after["device_id"] != before["device_id"]
    assert after["public_key"] != before["public_key"]


def test_a_reset_keeps_local_data(home: Path) -> None:
    run("device", "init", "--json", home=home)
    keepsake = home / "data" / "ai-stp" / "registry.sqlite"
    keepsake.write_text("local rows", encoding="utf-8")
    run("device", "reset", "--confirm", "--json", home=home)
    assert keepsake.read_text(encoding="utf-8") == "local rows"


def test_the_fallback_tier_is_reported_rather_than_assumed(home: Path) -> None:
    # The subprocess inherits `FORCE_COLOR` and a broken bus address, so the
    # operating system store is genuinely unreachable — the same situation as an
    # SSH session or a container.
    result = run("device", "init", "--json", home=home)
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["credential_store"] in ("file", "os_keyring")
    if envelope["data"]["credential_store"] == "file":
        assert envelope["warnings"]


def test_a_clean_home_builds_a_registry_that_reopens_deterministically(home: Path) -> None:
    first = run("passport", "developer", "init", "--json", home=home)
    assert first.returncode == 0
    registry = home / "data" / "ai-stp" / "registry.sqlite"
    assert registry.exists()
    if os.name != "nt":
        # POSIX-only: Windows st_mode is not 0o600 even when the registry is protected.
        assert stat.S_IMODE(registry.stat().st_mode) == 0o600

    second = run("passport", "developer", "show", "--json", home=home)
    assert second.returncode == 0
    assert json.loads(second.stdout)["data"] == json.loads(first.stdout)["data"]


def test_sync_preview_reaches_the_local_revision_graph_without_writing(home: Path) -> None:
    created = run("passport", "developer", "init", "--json", home=home)
    stable_id = json.loads(created.stdout)["data"]["stable_id"]
    registry = home / "data" / "ai-stp" / "registry.sqlite"
    before = registry.read_bytes()

    result = run("sync", "preview", "--id", stable_id, "--json", home=home)

    assert result.returncode == 0
    payload = json.loads(result.stdout)["data"]
    assert payload["state"] == "up_to_date"
    assert payload["stable_id"] == stable_id
    assert payload["candidate_revision_id"] == payload["head_revision_ids"][0]
    assert registry.read_bytes() == before


def test_reading_a_passport_before_it_exists_creates_nothing(home: Path) -> None:
    result = run("passport", "developer", "show", "--json", home=home)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "AI_STP_NOT_FOUND"
    assert not (home / "data" / "ai-stp" / "registry.sqlite").exists()


def test_local_state_needs_no_network(home: Path) -> None:
    # `offline-capability.md` puts passports in the offline column. The check is
    # the absence of a socket, not a claim about one.
    for argv in (
        ("passport", "developer", "init"),
        ("passport", "developer", "update", "--set", "role=backend"),
        ("passport", "developer", "show"),
        ("passport", "device", "refresh"),
        ("passport", "device", "show"),
    ):
        result = run(*argv, "--json", home=home)
        assert result.returncode == 0, argv
        assert json.loads(result.stdout)["ok"] is True


def test_two_homes_keep_separate_device_passports_and_separate_owners(tmp_path: Path) -> None:
    # `SPEC-002` REQ-213 and REQ-215: device passports are per device and are
    # never merged into one cross-device environment.
    one, two = tmp_path / "one", tmp_path / "two"
    first = json.loads(run("passport", "device", "refresh", "--json", home=one).stdout)["data"]
    second = json.loads(run("passport", "device", "refresh", "--json", home=two).stdout)["data"]
    assert first["stable_id"] != second["stable_id"]
    assert first["owner_id"] != second["owner_id"]
    # `SPEC-014` REQ-1418 adds the harness survey to the device passport, and
    # both homes observe the same machine — so the fact *names* match while the
    # identities do not, which is exactly the separation being checked.
    assert (
        sorted(first["facts"])
        == sorted(second["facts"])
        == [
            "architecture",
            "harness_versions",
            "installed_harnesses",
            "operating_system",
            "tool_versions",
        ]
    )


def test_device_passport_and_toolchain_harnesses_share_one_detection_result(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Isolate discovery from the host. `run()` copies `os.environ`, so PATH and
    # user roots would otherwise find installed harnesses and launch them.
    empty_path = home / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "localappdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setenv("CODEX_HOME", str(home / "codex-home"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home / "pi-home"))
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(home / "opencode-home"))
    monkeypatch.setenv("GROK_HOME", str(home / "grok-home"))
    survey = json.loads(run("toolchain", "harnesses", "--json", home=home).stdout)["data"][
        "harnesses"
    ]
    refresh = json.loads(run("passport", "device", "refresh", "--json", home=home).stdout)["data"]
    installed = [item["harness_id"] for item in survey if item["state"] != "available"]
    available = [item["harness_id"] for item in survey if item["state"] == "available"]
    facts = refresh["facts"]
    assert facts["installed_harnesses"]["value"] == installed
    for harness_id in available:
        assert harness_id not in facts["installed_harnesses"]["value"]
    if "pi" in available:
        assert "pi" not in facts["installed_harnesses"]["value"]
    versions = facts["harness_versions"]["value"]
    for item in survey:
        if item["state"] == "available":
            assert item["installations"] == []
            continue
        assert item["installations"]
        installation = item["installations"][0]
        assert installation["surface"] in {"cli", "desktop"}
        assert installation["version_source"]
        assert installation["diagnostic"]
        assert f"{item['harness_id']}={installation['version']}" in versions


def test_starting_over_by_deleting_the_data_directory_works(home: Path) -> None:
    # On the file tier both halves live under the data directory, so deleting it
    # leaves nothing behind and the next run mints a fresh identity cleanly.
    #
    # On the operating system tier the key outlives the directory, which is what
    # a user with a real keyring meets — and what made the installed wheel refuse
    # to do anything until the user reset it by hand. That direction is covered
    # in `tests/unit/test_cli_identity.py`, where the store can be controlled;
    # here the store is deliberately the file tier, so this pins the other half.
    first = json.loads(run("device", "init", "--json", home=home).stdout)["data"]
    shutil.rmtree(home / "data")

    # Reading says so rather than quietly minting a replacement.
    gone = run("device", "show", "--json", home=home)
    assert json.loads(gone.stdout)["error"]["code"] == "AI_STP_NOT_FOUND"

    result = run("device", "init", "--json", home=home)
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["device_id"] != first["device_id"]


def test_a_record_without_its_key_is_still_refused(home: Path) -> None:
    # The other direction stays a failure: a server may already know this
    # device_id, and re-minting would change an identity someone has on file.
    run("device", "init", "--json", home=home)
    secrets = list((home / "data" / "ai-stp" / "secrets").glob("*.secret"))
    if not secrets:
        # File-tier only: removing *.secret is a no-op when the OS keyring holds
        # the key (Windows WinVault, a working SecretService). Unit tests cover
        # the OS-keyring half; this process test is the file-tier oracle.
        pytest.skip("file-tier secrets absent; OS keyring holds the key on this host")
    for secret in secrets:
        secret.unlink()
    result = run("device", "show", "--json", home=home)
    assert result.returncode == 4
    assert json.loads(result.stdout)["error"]["code"] == "AI_STP_PRECONDITION_FAILED"


def test_a_cloud_command_without_a_platform_fails_typed_and_leaks_no_address(home: Path) -> None:
    # The configured catalogue address does not resolve, which is what an
    # offline machine meets. The failure has to be a registered code, and the
    # address must not travel in it.
    result = run("auth", "login", "--provider", "google", "--json", home=home)
    assert result.returncode in (5, 2)
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] in {
        "AI_STP_DEPENDENCY_UNAVAILABLE",
        "AI_STP_VALIDATION_ERROR",
    }
    assert "ai-stp.example" not in result.stdout
    assert result.stderr == ""


def test_signing_out_when_nothing_is_held_is_not_a_failure(home: Path) -> None:
    result = run("auth", "logout", "--json", home=home)
    assert result.returncode == 0
    assert json.loads(result.stdout)["data"]["state"] == "local_only"


def test_completing_a_sign_in_that_was_never_started_is_typed(home: Path) -> None:
    result = run("auth", "complete", "--json", home=home)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "AI_STP_NOT_FOUND"


def test_a_sign_in_needs_a_provider(home: Path) -> None:
    result = run("auth", "login", "--json", home=home)
    assert result.returncode == 2
    assert "provider" in json.loads(result.stdout)["error"]["message"]


def test_a_catalogue_read_without_a_platform_is_typed_and_writes_nothing(home: Path) -> None:
    # The configured address does not resolve, and nothing is cached. That is a
    # typed failure, not an empty page: `offline-capability.md` forbids turning
    # absence of network into an empty successful result.
    result = run("registry", "search", "--kind", "component", "--json", home=home)
    assert result.returncode == 5
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert result.stderr == ""
    # A read command creates no local state.
    assert not (home / "data" / "ai-stp" / "registry.sqlite").exists()


def test_a_catalogue_read_needs_a_kind(home: Path) -> None:
    result = run("registry", "search", "--json", home=home)
    assert result.returncode == 2
    assert "kind" in json.loads(result.stdout)["error"]["message"]


def test_switching_the_catalogue_off_is_reported_not_worked_around(home: Path) -> None:
    config = home / "config" / "ai-stp" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("catalog:\n  enabled: false\n", encoding="utf-8")
    result = run("registry", "search", "--kind", "component", "--json", home=home)
    assert result.returncode == 5
    assert "switched off" in json.loads(result.stdout)["error"]["message"]


def test_switching_off_the_catalogue_and_sync_leaves_a_complete_offline_path(ready: Path) -> None:
    # `SPEC-011` REQ-1117: offline mode is reached by switching off the
    # catalogue and synchronisation and needs no other change. Every local
    # command must still work, and the two that reach out must say why they
    # cannot rather than failing obscurely.
    config = ready / "config" / "ai-stp" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("catalog:\n  enabled: false\nsync:\n  enabled: false\n", encoding="utf-8")

    for argv in (
        ("version",),
        ("capabilities",),
        ("doctor",),
        ("config", "show"),
        ("auth", "status"),
        ("device", "show"),
        ("passport", "developer", "init"),
        ("passport", "developer", "update", "--set", "role=backend"),
        ("passport", "developer", "show"),
        ("passport", "device", "show"),
        ("help", "--agent"),
    ):
        result = run(*argv, "--json", home=ready)
        assert result.returncode == 0, argv
        assert json.loads(result.stdout)["ok"] is True, argv

    reported = json.loads(run("capabilities", "--json", home=ready).stdout)["data"]
    assert reported["catalog_enabled"] is False
    assert reported["sync_enabled"] is False

    refused = run("registry", "search", "--kind", "component", "--json", home=ready)
    assert refused.returncode == 5
    assert "switched off" in json.loads(refused.stdout)["error"]["message"]


def test_the_whole_project_and_toolchain_path_works_with_the_network_off(ready: Path) -> None:
    """The exit criterion of phase 3, as real processes rather than as units.

    Reading a project, indexing it, outlining its symbols, recording its
    passport and reporting the toolchain all have to complete from verified
    local state. None of them is allowed to need the network, and the way to
    show that is to switch it off and run them.
    """
    config = ready / "config" / "ai-stp" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("catalog:\n  enabled: false\nsync:\n  enabled: false\n", encoding="utf-8")

    work = ready / "projects" / "thing"
    (work / "src").mkdir(parents=True)
    (work / ".git").mkdir()
    (work / "src" / "app.py").write_text("def main() -> None: ...\n", encoding="utf-8")
    (work / "pyproject.toml").write_text('[project]\nname = "thing"\n', encoding="utf-8")

    for argv in (
        ("project", "discover", "--root", str(work.parent)),
        ("project", "index", "--root", str(work)),
        ("project", "symbols", "--root", str(work)),
        ("project", "passport", "--root", str(work)),
        ("toolchain", "profile"),
        ("toolchain", "harnesses"),
    ):
        result = run(*argv, "--json", home=ready)
        assert result.returncode == 0, argv
        assert json.loads(result.stdout)["ok"] is True, argv

    # Twice, because a re-scan is the thing that must not manufacture history.
    first = json.loads(run("project", "passport", "--root", str(work), "--json", home=ready).stdout)
    second = json.loads(
        run("project", "passport", "--root", str(work), "--json", home=ready).stdout
    )
    assert first["data"]["stable_id"] == second["data"]["stable_id"]
    assert first["data"]["revision_id"] == second["data"]["revision_id"]

    # And an install with nothing cached says what a person must do rather than
    # reaching for a network that is not there.
    profile = json.loads(run("toolchain", "profile", "--json", home=ready).stdout)["data"]
    pinned = next(
        item["tools"][0]["tool_id"] for item in profile["ecosystems"] if item.get("tools")
    )
    blocked = run("toolchain", "install", "--tool", pinned, "--offline", "--json", home=ready)
    assert blocked.returncode == 0
    answer = json.loads(blocked.stdout)["data"]
    assert answer["action"] == "needs_user_action"
    assert answer["offline_capable"] is False


def test_a_held_cloud_credential_never_reaches_any_output(home: Path) -> None:
    # `SPEC-011` REQ-1108 for the more sensitive secret. The device key is
    # already checked; a refresh token grants cloud access, and this is the
    # process-level form: plant one, run everything, and look at what the
    # process actually wrote.
    run("device", "init", "--json", home=home)
    secrets = home / "data" / "ai-stp" / "secrets"
    secrets.mkdir(parents=True, exist_ok=True)
    planted = "ROTATE-ME-IF-THIS-EVER-APPEARS"
    (secrets / "cloud-credentials.secret").write_text(
        json.dumps(
            {
                "account_id": "account_01KZAA000000000000000000A0",
                "device_id": "device_01KZAA000000000000000000A0",
                "access_token": planted,
                "refresh_token": planted,
                "expires_at": "2099-01-01T00:00:00.000Z",
                "state": "active",
            }
        ),
        encoding="utf-8",
    )
    (secrets / "cloud-credentials.secret").chmod(0o600)

    signed_in = run("auth", "status", "--json", home=home)
    assert json.loads(signed_in.stdout)["data"]["state"] == "authenticated"

    for argv in [*READ_COMMANDS, ("passport", "developer", "init")]:
        for mode in (("--json",), ()):
            result = run(*argv, *mode, home=home)
            assert planted not in result.stdout, argv
            assert planted not in result.stderr, argv


def test_logging_out_removes_the_credential_from_disk(home: Path) -> None:
    shown = run("device", "init", "--json", home=home)
    device_id = json.loads(shown.stdout)["data"]["device_id"]
    secrets = home / "data" / "ai-stp" / "secrets"
    planted = secrets / "cloud-credentials.secret"
    planted.write_text(
        json.dumps(
            {
                "account_id": "account_01KZAA000000000000000000A0",
                "device_id": "device_01KZAA000000000000000000A0",
                "access_token": "a",
                "refresh_token": "r",
                "expires_at": "2099-01-01T00:00:00.000Z",
                "state": "active",
            }
        ),
        encoding="utf-8",
    )
    run("passport", "developer", "init", "--json", home=home)

    result = run("auth", "logout", "--json", home=home)
    assert result.returncode == 0
    assert not planted.exists()
    # The device key and the registry are not credentials and stay.
    assert (secrets / f"device-key.{device_id}.secret").exists()
    assert (home / "data" / "ai-stp" / "registry.sqlite").exists()


def test_no_passport_collects_environment_values_or_local_paths(ready: Path) -> None:
    # `SPEC-003` REQ-307 and `SPEC-002` REQ-214: transcripts, secret values,
    # shell history and optional source content are not collected, and no
    # absolute user path enters a passport revision.
    #
    # Today's passports observe only the operating system and the architecture,
    # so this passes trivially. That is the point of pinning it now: the
    # detector `SPEC-014` describes will make collecting easy, and this is what
    # should fail the moment it collects too much.
    ready.mkdir(parents=True, exist_ok=True)
    (ready / ".env").write_text("API_TOKEN=leak-me-through-a-passport\n", encoding="utf-8")
    (ready / ".bash_history").write_text("export SUPER_SECRET=leak-me-too\n", encoding="utf-8")

    environment = {
        **os.environ,
        "XDG_CONFIG_HOME": str(ready / "config"),
        "XDG_DATA_HOME": str(ready / "data"),
        "HOME": str(home),
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent",
        # The same pin the helper above carries, and for the same reason it
        # gives: a host with a trusted OS keyring opens the locker whatever DBUS
        # says. Missing here, this test reached the macOS Keychain on a headless
        # runner and never came back — forty-three minutes of silence until the
        # job's own ceiling ended it, four runs in a row.
        "AI_STP_FORCE_FILE_CREDENTIAL_STORE": "1",
        "AI_STP_TEST_SECRET": "leak-me-from-the-environment",
    }

    def emitted(*argv: str) -> str:
        return subprocess.run(
            [sys.executable, "-m", "ai_stp_cli", *argv, "--json"],
            capture_output=True,
            text=True,
            env=environment,
            check=True,
            timeout=INVOCATION_SECONDS,
        ).stdout

    emitted("passport", "developer", "init")
    for argv in (("passport", "device", "show"), ("passport", "developer", "show")):
        output = emitted(*argv)
        for forbidden in (
            "leak-me-through-a-passport",
            "leak-me-too",
            "leak-me-from-the-environment",
            "AI_STP_TEST_SECRET",
            str(home),
        ):
            assert forbidden not in output, (argv, forbidden)
        # No absolute path of any shape belongs in a passport revision.
        facts = json.loads(output)["data"]["facts"]
        for name, fact in facts.items():
            assert not str(fact["value"]).startswith("/"), name


@pytest.mark.parametrize("argv", READ_COMMANDS)
def test_the_whole_envelope_validates_against_its_published_schema(
    argv: tuple[str, ...], ready: Path
) -> None:
    # The payload schemas were checked; the envelope around them was not, even
    # though it is published as `cli-envelope-success` and is what every caller
    # parses first. A consumer in another language has that file and nothing
    # was holding the CLI to it.
    published = json.loads(
        (SCHEMAS / "cli-envelope-success.schema.json").read_text(encoding="utf-8")
    )
    result = run(*argv, "--json", home=ready)
    validator = Draft202012Validator(published)  # pyright: ignore[reportArgumentType]
    validator.validate(json.loads(result.stdout))  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.parametrize(
    "argv",
    [
        ("nope",),
        ("help",),
        ("registry", "search", "--kind", "component"),
        ("auth", "complete"),
    ],
)
def test_a_failure_envelope_validates_against_its_published_schema(
    argv: tuple[str, ...], home: Path
) -> None:
    published = json.loads((SCHEMAS / "cli-envelope-error.schema.json").read_text(encoding="utf-8"))
    result = run(*argv, "--json", home=home)
    assert result.returncode != 0
    envelope = json.loads(result.stdout)
    validator = Draft202012Validator(published)  # pyright: ignore[reportArgumentType]
    validator.validate(envelope)  # pyright: ignore[reportUnknownMemberType]

    error = json.loads((SCHEMAS / "cli-error.schema.json").read_text(encoding="utf-8"))
    inner = Draft202012Validator(error)  # pyright: ignore[reportArgumentType]
    inner.validate(envelope["error"])  # pyright: ignore[reportUnknownMemberType]


def test_concurrent_first_runs_produce_one_identity(home: Path) -> None:
    """Six processes reaching a clean home at once, which is what an agent does.

    Bootstrap creates an owner record, a device record, a device key and two
    passports — a read-then-write spread across files and a database. Without an
    interprocess lock the processes interleave and crash each other; measured on
    this suite before the lock existed, three of six exited non-zero.

    The lock keeps the race from starting. The unique index added in schema 2
    decides it anyway for the cases a lock cannot reach — another mount, another
    machine, a future sync — so both are asserted here.
    """
    import concurrent.futures
    import sqlite3

    def once(_index: int) -> subprocess.CompletedProcess[str]:
        return run("passport", "device", "refresh", "--json", home=home)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(once, range(6)))

    assert [item.returncode for item in results] == [0] * 6, [
        item.stderr[:200] for item in results if item.returncode
    ]
    assert len({json.loads(item.stdout)["data"]["stable_id"] for item in results}) == 1

    registry = sqlite3.connect(home / "data" / "ai-stp" / "registry.sqlite")
    try:
        counts = dict(
            registry.execute("SELECT kind, COUNT(*) FROM entity GROUP BY kind").fetchall()
        )
    finally:
        registry.close()
    assert counts == {"device": 1}

    identifiers = {json.loads(item.stdout)["data"]["owner_id"] for item in results}
    assert len(identifiers) == 1


def test_a_read_command_leaves_a_clean_home_untouched(home: Path) -> None:
    """The defect this split is about, checked where a caller would see it.

    `device show` was declared `read` and minted an identity; `passport device
    show` was named `show` and wrote a revision. An agent plans around the
    mutability class in the machine help, so observing an installation must not
    be what brings it into existence.
    """
    for argv in (
        ("device", "show"),
        ("passport", "device", "show"),
        ("passport", "developer", "show"),
    ):
        result = run(*argv, "--json", home=home)
        envelope = json.loads(result.stdout)
        assert envelope["ok"] is False, argv
        assert envelope["error"]["code"] == "AI_STP_NOT_FOUND", argv
        assert envelope["next_actions"], argv
        # Nothing at all: not a directory, not a database, not a key.
        assert not (home / "data").exists(), argv


def test_local_read_collections_and_refusals_do_not_bootstrap_a_clean_home(home: Path) -> None:
    cases = (
        (("install", "status"), True),
        (("consent", "list"), True),
        (("component", "find"), True),
        (("install", "recover", "--operation", "operation_missing"), False),
        (("select", "eligibility", "--harness", "claude-code"), True),
    )

    for argv, succeeds in cases:
        result = run(*argv, "--json", home=home)
        envelope = json.loads(result.stdout)
        assert envelope["ok"] is succeeds, (argv, result.stdout[:200])
        if not succeeds:
            assert envelope["error"]["code"] == "AI_STP_NOT_FOUND", argv
        assert not (home / "data").exists(), argv


def test_every_command_declared_read_writes_nothing(ready: Path) -> None:
    """Against a real installation, not only an empty one.

    An empty home cannot catch a read that rewrites what it finds — a refreshed
    passport revision, a re-minted key, a migrated database.
    """
    import hashlib

    def snapshot() -> dict[str, str]:
        taken: dict[str, str] = {}
        for item in sorted((ready / "data").rglob("*")):
            # `-wal` and `-shm` are SQLite's own bookkeeping: opening a database
            # in write-ahead mode creates them whether or not anything is
            # written, and they are removed again on a clean close. What a read
            # must not change is the content, which is the file beside them.
            if item.is_file() and not item.name.endswith(("-wal", "-shm")):
                taken[str(item.relative_to(ready))] = hashlib.sha256(item.read_bytes()).hexdigest()
        return taken

    before = snapshot()
    assert before, "the fixture produced no state to compare against"
    for argv in READ_COMMANDS:
        result = run(*argv, "--json", home=ready)
        assert result.returncode == 0, (argv, result.stdout[:200])
    assert snapshot() == before
