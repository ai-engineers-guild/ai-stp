# pyright: reportPrivateUsage=false
"""The whole of the client's analytics egress, held to `SPEC-013`.

`REQ-1316`-`REQ-1319` and `docs/contracts/cli-telemetry.md` own the behaviour;
this is where the four acceptance rows are actually observed. The tests are
grouped by requirement rather than by module, because the requirement is what a
reader is checking against and the code that implements one is spread across
`telemetry`, `config` and the install command.

Nothing here reaches a network. `tests/conftest.py` suppresses the egress for
the whole suite; the tests that need the send path delete that guard and replace
the transport, so what is exercised is the code's own decision rather than a
collector's mood.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest

from ai_stp_cli import config, identity, telemetry
from ai_stp_cli.commands import install as install_cmd
from ai_stp_cli.commands import telemetry as telemetry_cmd
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, installation, revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_contracts.first_party import versions as corpus_versions
from ai_stp_passports import SetupVersionPassport

pytestmark = pytest.mark.cli

AT = "2026-01-01T00:00:00.000Z"


def _many_component_setup() -> tuple[str, str, int]:
    """A real first-party setup with more than one component, and how many.

    `REQ-1318` says one request per component installed, so the fixture has to
    be a setup of more than one — but *which* setup and *how many* are facts
    about somebody else's builder tree. A pinned identifier stood here until
    2026-08-29 and stopped existing the moment the corpus was rebuilt from the
    live setup systems. The shape is asserted; the identity is looked up.
    """
    setups = [
        item
        for item in corpus_versions()
        if item.kind == "setup" and isinstance(item.passport, SetupVersionPassport)
    ]
    chosen = max(setups, key=lambda item: len(cast(SetupVersionPassport, item.passport).components))
    members = len(cast(SetupVersionPassport, chosen.passport).components)
    assert members > 1
    return chosen.passport.stable_id, chosen.passport.version, members


MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION, MANY_COMPONENT_COUNT = _many_component_setup()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, dict[str, str]]]]:
    """Every ping the code decided to send, without any of them leaving.

    The suite-wide suppression is lifted here on purpose: it short-circuits the
    reporting step before it reaches a transport, so a test that kept it would
    observe the guard rather than the decision. What replaces it is the send
    itself, so the code still runs the whole way and nothing reaches a network.
    """
    monkeypatch.delenv(telemetry.SUPPRESS_ENVIRONMENT, raising=False)
    recorded: list[tuple[str, dict[str, str]]] = []

    def _send(url: str, fields: Mapping[str, str]) -> bool:
        recorded.append((url, dict(fields)))
        return True

    original = telemetry.send
    telemetry.send = _send  # type: ignore[assignment]
    install_cmd.telemetry.send = _send  # type: ignore[assignment]
    try:
        yield recorded
    finally:
        telemetry.send = original  # type: ignore[assignment]
        install_cmd.telemetry.send = original  # type: ignore[assignment]


def _consented(url: str = "https://collector.example") -> str:
    """Accepted consent and a switch that is on: the only state that sends."""
    answer = telemetry.accept()
    config.write_config({"telemetry.enabled": True, "telemetry.url": url})
    return answer.anon


def _materialize(stable_id: str, version: str) -> str:
    """Put a first-party setup and its components in the local registry."""
    corpus = corpus_versions()
    setup = next(
        item
        for item in corpus
        if item.passport.kind == "setup"
        and item.passport.stable_id == stable_id
        and item.passport.version == version
    )
    validated = SetupVersionPassport.model_validate(setup.passport.model_dump(mode="json"))
    wanted = {ref.stable_id for ref in validated.components}
    selected = [
        item
        for item in corpus
        if item is setup
        or (item.passport.kind == "component" and item.passport.stable_id in wanted)
    ]
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        for item in selected:
            content.put(connection, item.artifact, at=AT)
            document = item.passport.model_dump(mode="json")
            document.pop("revision_id")
            stored = revisions.commit(connection, document, device_id="device_test")
            versions.record(
                connection,
                stable_id=item.passport.stable_id,
                version=item.passport.version,
                passport_digest=item.passport_digest,
                revision_id=stored.revision_id,
                at=AT,
            )
    assert isinstance(setup.passport, SetupVersionPassport)
    return setup.passport.harness_id


def _plan(action: str, harness: str, stable_id: str = "", version: str = "") -> installation.Plan:
    return installation.Plan(
        operation_id="operation_test",
        action=action,
        author="account_test",
        target_id=f"target:{harness}",
        expected_target_digest="sha256:" + "0" * 64,
        provider_version="1.0.0",
        effects=(),
        confirmation="",
        recovery_action="rollback",
        expires_at=AT,
        created_at=AT,
        setup_stable_id=stable_id,
        setup_version=version,
    )


def _observed(version: str) -> Callable[[str], str]:
    """Stand in for probing the harness, which needs the harness installed."""

    def _probe(harness: str) -> str:
        del harness
        return version

    return _probe


def _report(plan: installation.Plan, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the reporting step the way settling an operation runs it."""
    monkeypatch.setattr(install_cmd, "_observed_harness_version", _observed("1.2.3"))
    with closing(open_registry(configured_path(), create=True)) as connection:
        install_cmd._report_installation(connection, plan)


# --------------------------------------------------------------------------
# REQ-1316 — nothing is sent before somebody agreed, and agreement is an event
# --------------------------------------------------------------------------


def test_an_install_without_consent_sends_nothing(
    sent: list[tuple[str, dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default state is silence, and it takes no configuration to get it."""
    harness = _materialize(MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
    config.write_config({"telemetry.url": "https://collector.example"})

    _report(_plan("install", harness, MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION), monkeypatch)

    assert telemetry.consent().state == telemetry.STATE_NOT_ASKED
    assert sent == []


def test_turning_telemetry_on_by_setting_a_value_is_refused() -> None:
    """Consent cannot be granted by editing a file.

    A value written this way would say the feature is on with nothing able to
    say who agreed or when, which is the one thing consent exists to record.
    """
    with pytest.raises(CliFailure) as raised:
        config.set_values({"telemetry.enabled": "true"})

    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"
    assert config.stored_values().get("telemetry.enabled") is None


def test_turning_telemetry_off_by_setting_a_value_is_not_refused() -> None:
    """Withdrawal is never harder than the thing it withdraws."""
    _consented()

    config.set_values({"telemetry.enabled": "false"})

    assert config.stored_values()["telemetry.enabled"] is False


def test_refusing_and_never_being_asked_are_identical_on_the_wire(
    sent: list[tuple[str, dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The difference between the two never leaves the machine.

    If a refusal were observable — as a different request, or as the absence of
    one where silence is not the default — then the refusal itself would be the
    signal, and refusing would report something about the operator.
    """
    harness = _materialize(MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
    plan = _plan("install", harness, MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)

    _report(plan, monkeypatch)
    while_never_asked = list(sent)

    telemetry.decline()
    _report(plan, monkeypatch)
    while_declined = list(sent)

    assert while_never_asked == []
    assert while_declined == []


def test_consent_without_confirmation_is_not_consent() -> None:
    """A flag somebody passed without reading it is not an answer."""
    with pytest.raises(CliFailure) as raised:
        telemetry_cmd.consent({"accept": True})

    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"
    assert telemetry.consent().state == telemetry.STATE_NOT_ASKED


def test_the_screen_takes_exactly_one_answer() -> None:
    """Neither both nor neither. A default here would decide for somebody."""
    for parameters in ({"confirm": True}, {"accept": True, "decline": True, "confirm": True}):
        with pytest.raises(CliFailure) as raised:
            telemetry_cmd.consent(parameters)
        assert raised.value.code == "AI_STP_VALIDATION_ERROR"

    assert telemetry.consent().state == telemetry.STATE_NOT_ASKED


def test_accepting_records_the_answer_and_turns_the_feature_on() -> None:
    """The command is the only door, so it has to open the whole way."""
    answer = telemetry_cmd.consent({"accept": True, "confirm": True})

    assert telemetry.consent().state == telemetry.STATE_ACCEPTED
    assert config.stored_values()["telemetry.enabled"] is True
    assert answer.payload.state == "accepted"
    assert answer.payload.enabled is True


# --------------------------------------------------------------------------
# REQ-1317 — a closed field list, and nothing that names the machine
# --------------------------------------------------------------------------


def test_the_request_carries_exactly_the_declared_fields() -> None:
    fields = telemetry.ping(
        operating_system="linux",
        harness="codex",
        harness_version="0.140.1",
        ai_stp_version="0.1.0",
        component_type="mcp",
        name="serena",
        source="platform",
        identifier="component_01",
        version="1.2",
        anon="anon-1",
    )

    assert fields is not None
    assert tuple(fields) == telemetry.PING_FIELDS


def test_the_declared_field_list_is_the_contract_document() -> None:
    """The closed list lives in three places and they have to agree.

    Widening the request means editing the code, the contract and `SPEC-013`
    together. This is what makes forgetting one of them fail rather than ship.
    """
    contract = Path("docs/contracts/cli-telemetry.md").read_text(encoding="utf-8")
    named = [line for line in contract.splitlines() if line.startswith("| `")]
    documented = tuple(line.split("`")[1] for line in named)

    assert documented == telemetry.PING_FIELDS


def test_a_field_outside_the_list_is_refused_rather_than_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The builder enforces the closed set, not a comment above it."""
    monkeypatch.setattr(telemetry, "PING_FIELDS", (*telemetry.PING_FIELDS, "project"))

    assert (
        telemetry.ping(
            operating_system="linux",
            harness="codex",
            harness_version="0.140.1",
            ai_stp_version="0.1.0",
            component_type="mcp",
            name="serena",
            source="platform",
            identifier="component_01",
            version="1.2",
            anon="anon-1",
        )
        is None
    )


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_missing_value_makes_it_not_a_ping(blank: str) -> None:
    """A declared field filled with a placeholder is a worse answer than none."""
    assert (
        telemetry.ping(
            operating_system="linux",
            harness="codex",
            harness_version="0.140.1",
            ai_stp_version="0.1.0",
            component_type="mcp",
            name=blank,
            source="platform",
            identifier="component_01",
            version="1.2",
            anon="anon-1",
        )
        is None
    )


def test_a_source_that_is_not_public_is_not_a_source() -> None:
    """`platform` and `github` are the whole set: anything else names nowhere."""
    assert (
        telemetry.ping(
            operating_system="linux",
            harness="codex",
            harness_version="0.140.1",
            ai_stp_version="0.1.0",
            component_type="mcp",
            name="serena",
            source="local",
            identifier="/home/someone/work/serena",
            version="1.2",
            anon="anon-1",
        )
        is None
    )


def test_a_component_nobody_can_name_publicly_produces_no_entry() -> None:
    """A private object with no public repository has no public identity.

    Sending a stable id for it would publish that the object exists; sending its
    source would publish where it lives. So it is left out entirely, and leaving
    it out is what makes the setup's other components still reportable.
    """
    assert install_cmd._public_identity({"visibility": "private"}, "component_01") == ("", "")
    assert install_cmd._public_identity(
        {"visibility": "private", "source": {"repository": "/home/someone/work/thing"}},
        "component_01",
    ) == ("", "")
    assert install_cmd._public_identity(
        {"visibility": "private", "source": {"repository": "git@github.com:org/private.git"}},
        "component_01",
    ) == ("", "")


def test_a_private_object_is_named_by_its_public_repository() -> None:
    """Before an object is on the platform, the honest public name is where
    it came from — and only when that is a public GitHub address."""
    assert install_cmd._public_identity(
        {"visibility": "private", "source": {"repository": "https://github.com/org/repo"}},
        "component_01",
    ) == ("https://github.com/org/repo", "github")
    assert install_cmd._public_identity({"visibility": "public"}, "component_01") == (
        "component_01",
        "platform",
    )


def test_the_request_names_the_kind_of_component_not_the_kind_of_passport(
    sent: list[tuple[str, dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`component_type` is one of the eight, and `kind` is not that field.

    Every component passport carries `kind: component` as its discriminator, so
    reading `kind` here sent a constant under the name of an answer — a field
    that looked populated and told nobody anything.
    """
    harness = _materialize(MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
    _consented()

    _report(_plan("install", harness, MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION), monkeypatch)

    kinds = {fields["component_type"] for _, fields in sent}
    assert kinds
    assert kinds <= {
        "instruction",
        "skill",
        "mcp",
        "hook",
        "command",
        "agent",
        "plugin",
        "setting",
    }


def test_nothing_sent_names_the_machine_it_was_sent_from(
    sent: list[tuple[str, dict[str, str]]],
    monkeypatch: pytest.MonkeyPatch,
    isolated_environment: Path,
) -> None:
    """The strongest form of the rule: no value contains this home directory.

    Stated against the actual temporary home rather than a list of forbidden
    keys, so a future field that happens to carry a path fails here even though
    nobody thought to add it to a list.
    """
    harness = _materialize(MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
    _consented()
    monkeypatch.setenv("AI_STP_PROJECT", "a-private-project-name")

    _report(_plan("install", harness, MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION), monkeypatch)

    assert sent
    home = str(isolated_environment)
    for _, fields in sent:
        for value in fields.values():
            assert home not in value
            assert "a-private-project-name" not in value
            assert not value.startswith("/")
            assert not value.startswith("account_")


def test_a_cleartext_collector_is_refused_unless_the_packets_stay_here() -> None:
    """The catalogue address rule, for the same reason."""
    assert telemetry.address_allowed("https://collector.example")
    assert telemetry.address_allowed("http://localhost:9000")
    assert telemetry.address_allowed("http://127.0.0.1:9000")
    assert not telemetry.address_allowed("http://collector.example")
    assert not telemetry.address_allowed("ftp://collector.example")
    assert not telemetry.address_allowed("https://")
    assert not telemetry.address_allowed("")


# --------------------------------------------------------------------------
# REQ-1318 — best effort, only on install and update, one per component
# --------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["backup", "rollback", "remove", "status"])
def test_only_installing_something_reports_installing_something(
    action: str, sent: list[tuple[str, dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restore put nothing anywhere, and reads put nothing anywhere twice."""
    harness = _materialize(MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
    _consented()

    _report(_plan(action, harness, MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION), monkeypatch)

    assert sent == []


@pytest.mark.parametrize("action", ["install", "update"])
def test_a_setup_of_many_components_gives_one_request_each(
    action: str, sent: list[tuple[str, dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One request per component actually installed, not one per operation."""
    harness = _materialize(MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
    _consented()

    _report(_plan(action, harness, MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION), monkeypatch)

    assert len(sent) == MANY_COMPONENT_COUNT
    assert {url for url, _ in sent} == {"https://collector.example"}
    assert len({fields["id"] for _, fields in sent}) == MANY_COMPONENT_COUNT
    assert {fields["anon"] for _, fields in sent} == {telemetry.consent().anon}


def test_a_harness_version_nobody_observed_is_not_guessed_at(
    sent: list[tuple[str, dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A declared field cannot be filled with an empty string and sent."""
    harness = _materialize(MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
    _consented()
    monkeypatch.setattr(install_cmd, "_observed_harness_version", _observed(""))

    with closing(open_registry(configured_path(), create=True)) as connection:
        install_cmd._report_installation(
            connection, _plan("install", harness, MANY_COMPONENT_SETUP, MANY_COMPONENT_VERSION)
        )

    assert sent == []


def test_a_collector_that_is_down_is_not_a_failed_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refusal, timeout and a 500 all mean the same thing here: nothing.

    The result of an installation is a property of the target. A collector that
    is unreachable, slow or broken changes nothing about whether the setup was
    installed, so none of these may surface as an error or a retry.
    """
    monkeypatch.delenv(telemetry.SUPPRESS_ENVIRONMENT, raising=False)
    import httpx

    class _Answer:
        status_code = 500

    def _raising(error: Exception) -> Callable[..., object]:
        def _get(*_: object, **__: object) -> object:
            raise error

        return _get

    def _refused(*_: object, **__: object) -> _Answer:
        return _Answer()

    behaviours: tuple[Callable[..., object], ...] = (
        _raising(httpx.ConnectError("refused")),
        _raising(httpx.ReadTimeout("slow")),
        _raising(RuntimeError("something nobody anticipated")),
        _refused,
    )
    for behaviour in behaviours:
        monkeypatch.setattr(httpx, "get", behaviour)
        assert telemetry.send("https://collector.example", {"os": "linux"}) is False


def test_a_collector_that_answers_is_reported_as_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(telemetry.SUPPRESS_ENVIRONMENT, raising=False)
    import httpx

    seen: dict[str, Any] = {}

    class _Answer:
        status_code = 204

    def _get(url: str, params: Mapping[str, str] | None = None, timeout: float = 0.0) -> _Answer:
        seen["url"] = url
        seen["params"] = dict(params or {})
        seen["timeout"] = timeout
        return _Answer()

    monkeypatch.setattr(httpx, "get", _get)

    assert telemetry.send("https://collector.example", {"os": "linux"}) is True
    assert seen["url"] == "https://collector.example"
    assert seen["params"] == {"os": "linux"}
    assert seen["timeout"] == telemetry.TIMEOUT_SECONDS


def test_the_suppression_guard_holds_even_against_a_reachable_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What keeps `just check` from touching a live collector."""
    import httpx

    def _forbidden(*_: object, **__: object) -> object:
        raise AssertionError("the suppressed path must not reach the transport")

    monkeypatch.setattr(httpx, "get", _forbidden)

    assert telemetry.suppressed() is True
    assert telemetry.send("https://collector.example", {"os": "linux"}) is False


def test_reporting_can_never_turn_a_healthy_install_into_a_failed_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard around the whole body, asserted rather than assumed.

    This runs inside the transaction that settles an operation, so an exception
    escaping it would fail an installation that already succeeded.
    """
    _consented()

    def _explode(*_: object, **__: object) -> object:
        raise RuntimeError("the registry is on fire")

    monkeypatch.setattr(install_cmd, "_installed_components", _explode)

    with closing(open_registry(configured_path(), create=True)) as connection:
        install_cmd._report_installation(connection, _plan("install", "codex", "setup_01", "1.0"))


def test_a_setup_this_machine_does_not_hold_reports_nothing(
    sent: list[tuple[str, dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is invented for a passport that is not there to read."""
    _consented()

    _report(_plan("install", "codex", "setup_01KZWSHE3VWEF0NT2XVRH45AJ9", "9.9"), monkeypatch)
    _report(_plan("install", "codex"), monkeypatch)

    assert sent == []


# --------------------------------------------------------------------------
# REQ-1319 — the identifier: minted on consent, dropped on either kind of off
# --------------------------------------------------------------------------


def test_declining_forgets_the_identifier() -> None:
    """The state is kept and the identifier is not.

    Keeping the state is what stops the question being asked again; keeping the
    identifier would leave behind the one thing consent was needed for.
    """
    _consented()

    telemetry.decline()

    answer = telemetry.consent()
    assert answer.state == telemetry.STATE_DECLINED
    assert answer.anon == ""
    assert "anon" not in json.loads(telemetry.record_path().read_text(encoding="utf-8"))


def test_switching_the_feature_off_forgets_the_identifier_too() -> None:
    """Off that keeps one is off in name only.

    The recorded answer survives, because being switched off is not the same as
    having been asked and refused — the question does not come back.
    """
    _consented()

    config.set_values({"telemetry.enabled": "false"})

    answer = telemetry.consent()
    assert answer.state == telemetry.STATE_ACCEPTED
    assert answer.anon == ""
    assert answer.accepted is False


def test_consenting_again_mints_a_different_identifier() -> None:
    """Turning it off and on again must not link the two periods together.

    That linkage is exactly what somebody switching it off was avoiding, so a
    resurrected identifier would undo the withdrawal it followed.
    """
    first = _consented()
    telemetry.decline()
    second = telemetry.accept().anon

    assert first
    assert second
    assert first != second


def test_the_identifier_is_not_the_device_identity() -> None:
    """`anon` distinguishes one installation from another and nothing else.

    The device identity is bound to an account and signs for it. Reusing it here
    would make an anonymous ping attributable, which is the whole difference.
    """
    anon = _consented()
    record, _ = identity.load_or_create()

    assert anon != record.device_id
    assert record.device_id not in telemetry.record_path().read_text(encoding="utf-8")


def test_an_ordinary_status_read_never_prints_the_identifier() -> None:
    """Naming the field is the point; printing its value would defeat it.

    A status command that showed it would become the one place it can be copied
    out of, which is the opposite of what it exists for.
    """
    _consented()

    status = telemetry_cmd.show({}).payload
    rendered = status.model_dump_json()

    assert "anon" in status.collected
    assert telemetry.consent().anon not in rendered


def test_an_unreadable_record_is_never_asked_rather_than_an_error() -> None:
    """This is consulted while an install settles, not by somebody invoking it.

    A corrupt byte there must not become a failed installation, and treating it
    as "never asked" is also the safe direction: it sends nothing.
    """
    path = telemetry.record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    for text in ("{ not json", '"a string"', '{"state": "something-else"}', "[]"):
        path.write_text(text, encoding="utf-8")
        answer = telemetry.consent()
        assert answer.state == telemetry.STATE_NOT_ASKED
        assert answer.accepted is False


def test_the_answer_lives_in_local_state_and_not_in_the_configuration() -> None:
    """Consent is an event, recorded where events are, not where settings are.

    Kept apart on purpose: "enabled" must not be able to appear by editing a
    file with nobody able to say where it came from.
    """
    anon = _consented()

    settings = config.config_path().read_text(encoding="utf-8")
    assert telemetry.record_path() != config.config_path()
    assert anon not in settings
    assert "anon" not in settings
    assert "telemetry-consent" in telemetry.record_path().name
