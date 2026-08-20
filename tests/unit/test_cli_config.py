"""Reading configuration: the effective value and, truthfully, where it came from."""

from pathlib import Path

import pytest

from ai_stp_cli import config
from ai_stp_cli.errors import CliFailure


def _write(document: str) -> Path:
    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path


def test_without_a_file_every_value_is_a_default_and_that_is_not_an_error() -> None:
    # `SPEC-011` REQ-1114: every declared field has a default, and the absence of
    # a file is a complete configuration rather than a fault.
    report = config.effective_config()
    assert report.config_path is None
    assert {value.source for value in report.values} == {"default"}
    assert [value.path for value in report.values] == [
        field.path for field in config.declared_fields()
    ]


def test_a_written_value_is_reported_as_coming_from_the_file() -> None:
    # Reporting `default` for a value the user set would be a confident lie, and
    # `SPEC-011` REQ-1116 exists precisely so the two are distinguishable.
    path = _write("catalog:\n  enabled: false\nsearch:\n  result_limit: 5\n")
    report = config.effective_config()
    # A real path here: redaction belongs to rendering, and this value has to
    # stay openable.
    assert report.config_path == str(path)
    by_path = {value.path: value for value in report.values}
    assert by_path["catalog.enabled"].value is False
    assert by_path["catalog.enabled"].source == "config_file"
    assert by_path["search.result_limit"].value == 5
    assert by_path["catalog.url"].source == "default"


def test_a_list_valued_field_round_trips() -> None:
    _write("projects:\n  discovery_roots:\n    - /srv/one\n    - /srv/two\n")
    by_path = {value.path: value for value in config.effective_config().values}
    assert by_path["projects.discovery_roots"].value == ["/srv/one", "/srv/two"]


def test_an_empty_file_is_the_same_as_no_file() -> None:
    _write("")
    assert {value.source for value in config.effective_config().values} == {"default"}


def test_an_unknown_key_is_named_rather_than_ignored() -> None:
    # `SPEC-011` REQ-1115. A silently ignored key is how a user spends an
    # afternoon wondering why a setting has no effect.
    _write("catalogue:\n  enabled: false\n")
    with pytest.raises(CliFailure, match="unknown configuration key: catalogue") as raised:
        config.effective_config()
    assert raised.value.exit_code == 2


def test_a_file_that_is_not_yaml_is_a_validation_error() -> None:
    _write("catalog:\n  - [unclosed\n")
    with pytest.raises(CliFailure, match="not valid YAML"):
        config.effective_config()


def test_a_file_that_is_not_a_mapping_is_a_validation_error() -> None:
    _write("- one\n- two\n")
    with pytest.raises(CliFailure, match="must contain a mapping"):
        config.effective_config()


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("catalog:\n  enabled: yes-please\n", "must be a true/false value"),
        ("search:\n  result_limit: many\n", "must be a whole number"),
        ("search:\n  result_limit: true\n", "must be a whole number"),
        ("catalog:\n  url: 8\n", "must be a string"),
        ("projects:\n  discovery_roots: /srv\n", "must be a list of strings"),
        ("projects:\n  discovery_roots:\n    - 8\n", "must be a list of strings"),
    ],
)
def test_a_value_of_the_wrong_type_names_the_field_and_the_shape(
    document: str, expected: str
) -> None:
    _write(document)
    with pytest.raises(CliFailure, match=expected):
        config.effective_config()


def test_the_two_switches_capabilities_reports_come_from_the_same_read() -> None:
    _write("catalog:\n  enabled: false\nsync:\n  enabled: true\n")
    assert config.catalog_and_sync_enabled() == (False, True)


def test_paths_follow_xdg(isolated_environment: Path) -> None:
    assert config.config_path() == isolated_environment / "config" / "ai-stp" / "config.yaml"
    assert config.default_registry_path() == str(
        isolated_environment / "data" / "ai-stp" / "registry.sqlite"
    )


def test_paths_fall_back_to_the_home_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    # Pathlib-built home so separators match the host OS (POSIX vs Windows).
    home = tmp_path / "home" / "example"
    home.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    assert config.config_path() == home / ".config" / "ai-stp" / "config.yaml"
    assert config.default_registry_path() == str(
        home / ".local" / "share" / "ai-stp" / "registry.sqlite"
    )


def test_no_declared_field_can_hold_a_secret() -> None:
    # `docs/contracts/cli-config.md` keeps credentials in the system store. A
    # field whose name invites a token would be the first step away from that.
    forbidden = ("token", "secret", "password", "key", "credential")
    for field in config.declared_fields():
        assert not any(word in field.path.lower() for word in forbidden), field.path


def test_a_top_level_scalar_and_a_string_value_are_both_read() -> None:
    # `schema_version` is the one declared key that is not a section, and
    # `catalog.url` is the one declared string; neither has another test.
    _write("schema_version: 1\ncatalog:\n  url: https://example.test/v1\n")
    by_path = {value.path: value for value in config.effective_config().values}
    assert by_path["catalog.url"].value == "https://example.test/v1"
    assert by_path["catalog.url"].source == "config_file"


def test_an_override_beats_the_file_which_beats_the_default() -> None:
    # REQ-1116 names the order; this is the executable form of it, exercising
    # all three sources in one report.
    _write("search:\n  result_limit: 5\nsync:\n  enabled: true\n")
    report = config.effective_config({"search.result_limit": "9"})
    by_path = {value.path: value for value in report.values}
    assert (by_path["search.result_limit"].value, by_path["search.result_limit"].source) == (
        9,
        "command_argument",
    )
    assert (by_path["sync.enabled"].value, by_path["sync.enabled"].source) == (True, "config_file")
    assert (by_path["catalog.enabled"].value, by_path["catalog.enabled"].source) == (
        True,
        "default",
    )


def test_an_override_does_not_rewrite_the_file() -> None:
    # `cli-config.md`: an argument acts on this call only. That is what makes it
    # an override rather than a write, and why no command in #73 writes config.
    path = _write("search:\n  result_limit: 5\n")
    config.effective_config({"search.result_limit": "9"})
    assert path.read_text(encoding="utf-8") == "search:\n  result_limit: 5\n"
    assert config.effective_config().values[4].value == 5


@pytest.mark.parametrize(
    ("text", "expected"),
    [("true", True), ("yes", True), ("1", True), ("on", True), ("false", False), ("off", False)],
)
def test_a_boolean_override_accepts_the_usual_spellings(text: str, expected: bool) -> None:
    report = config.effective_config({"catalog.enabled": text})
    assert report.values[0].value is expected


def test_a_list_override_is_split_on_commas_and_drops_blanks() -> None:
    report = config.effective_config({"projects.discovery_roots": "/a, /b ,, /c"})
    assert report.values[5].value == ["/a", "/b", "/c"]


@pytest.mark.parametrize(
    ("path", "text", "expected"),
    [
        ("catalog.enabled", "maybe", "must be a true/false value"),
        ("search.result_limit", "many", "must be a whole number"),
    ],
)
def test_an_unparseable_override_is_refused_rather_than_coerced(
    path: str, text: str, expected: str
) -> None:
    # Falling back to the default here would look like the override applied.
    with pytest.raises(CliFailure, match=expected):
        config.effective_config({path: text})


def test_an_override_of_an_undeclared_key_is_refused() -> None:
    with pytest.raises(CliFailure, match=r"unknown configuration key: catalog\.colour"):
        config.effective_config({"catalog.colour": "blue"})


def test_rendering_folds_the_home_directory_away_but_reading_does_not(
    isolated_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The bug this pins: a redacted value was once stored rather than only
    # shown, so `doctor` checked whether a directory literally named `~` existed
    # in the working directory and found one a test had created.
    # Windows Path.home() ignores $HOME; pin home to the fixture tree so
    # redaction is exercised against the same paths the fixture wrote.
    monkeypatch.setattr(Path, "home", staticmethod(lambda: isolated_environment))
    _write("projects:\n  discovery_roots:\n    - " + str(isolated_environment / "work") + "\n")
    real = config.effective_config()
    shown = config.for_display(real)
    by_path = {value.path: value.value for value in real.values}
    by_shown = {value.path: value.value for value in shown.values}

    assert Path(str(by_path["registry.path"])).is_absolute()
    # Redacted machine paths always use POSIX separators after `~`.
    assert str(by_shown["registry.path"]).startswith("~/")
    assert by_shown["projects.discovery_roots"] == ["~/work"]
    assert str(shown.config_path).startswith("~/")
    # Values that are not paths are untouched by rendering.
    assert by_shown["catalog.url"] == by_path["catalog.url"]
    assert by_shown["search.result_limit"] == by_path["search.result_limit"]


def test_only_declared_path_fields_are_folded() -> None:
    # Declared, not inferred from the field name: a rename must not silently
    # change what gets redacted.
    assert {item.path for item in config.declared_fields() if item.is_path} == {
        "registry.path",
        "projects.discovery_roots",
    }


def test_a_string_override_is_taken_as_written() -> None:
    report = config.effective_config({"catalog.url": "https://example.test/v1"})
    assert report.values[1].value == "https://example.test/v1"
    assert report.values[1].source == "command_argument"


def test_rendering_leaves_a_path_field_with_no_value_alone() -> None:
    # `for_display` is total over the declared value types: a path field may
    # legitimately be absent, and folding `None` would invent a location.
    from ai_stp_contracts.machine_help import ConfigReport, ConfigValue

    report = ConfigReport(
        values=[ConfigValue(path="registry.path", value=None, source="default")],
        config_path=None,
    )
    assert config.for_display(report).values[0].value is None


@pytest.mark.parametrize(
    ("document", "expected", "at"),
    [
        # The defect: the section is declared, the key inside it is not, and
        # after flattening nothing compared the result against the field list.
        (
            "catalog:\n  urll: https://elsewhere.test/v1\n",
            "unknown configuration key",
            "catalog.urll",
        ),
        ("catalog: false\n", "must be a mapping", "catalog"),
        ("catalog:\n  url:\n    inner: x\n", "must not be a mapping", "catalog.url"),
        ("schema_version: 99\n", "reads configuration schema 1", "schema_version"),
        ("schema_version: nineteen\n", "must be a whole number", "schema_version"),
        ("catalogue:\n  enabled: false\n", "unknown configuration key", "catalogue"),
    ],
)
def test_a_document_the_declared_fields_cannot_hold_is_refused(
    document: str, expected: str, at: str
) -> None:
    _write(document)
    with pytest.raises(CliFailure, match=expected) as raised:
        config.effective_config()
    assert raised.value.details["at"] == at
    assert raised.value.exit_code == 2


def test_writing_a_value_is_idempotent_and_reports_only_what_changed() -> None:
    path, changed = config.set_values({"catalog.enabled": "false", "search.result_limit": "5"})
    assert set(changed) == {"catalog.enabled", "search.result_limit"}
    first = path.read_bytes()

    _path, again = config.set_values({"catalog.enabled": "false"})
    assert again == ()
    # Byte-identical, so an agent repeating itself cannot tell one run from the
    # next by the file either.
    assert path.read_bytes() == first


def test_a_written_file_is_read_back_as_coming_from_the_file() -> None:
    config.set_values({"catalog.enabled": "false"})
    by_path = {value.path: value for value in config.effective_config().values}
    assert by_path["catalog.enabled"].value is False
    assert by_path["catalog.enabled"].source == "config_file"


def test_unsetting_restores_the_default() -> None:
    config.set_values({"catalog.enabled": "false"})
    _path, removed = config.unset_values(("catalog.enabled",))
    assert removed == ("catalog.enabled",)
    by_path = {value.path: value for value in config.effective_config().values}
    assert by_path["catalog.enabled"].value is True
    assert by_path["catalog.enabled"].source == "default"

    # Removing what is not set is the state the caller asked for.
    _path, nothing = config.unset_values(("catalog.enabled",))
    assert nothing == ()


def test_writing_an_undeclared_field_is_refused_before_the_file_is_touched() -> None:
    config.set_values({"catalog.enabled": "false"})
    before = config.config_path().read_bytes()
    for call in (
        lambda: config.set_values({"catalog.colour": "blue"}),
        lambda: config.unset_values(("catalog.colour",)),
    ):
        with pytest.raises(CliFailure, match=r"unknown configuration key: catalog\.colour"):
            call()
    assert config.config_path().read_bytes() == before


def test_initialising_never_overwrites_an_existing_file() -> None:
    config.set_values({"search.result_limit": "5"})
    before = config.config_path().read_bytes()

    path, created = config.initialise()
    assert created is False
    assert path.read_bytes() == before

    path.unlink()
    _path, created = config.initialise()
    assert created is True


def test_no_declared_field_can_be_written_that_invites_a_secret() -> None:
    # The same closed list the reader enforces, checked against the words that
    # would make this file a credential store. `ADR-0058` keeps those elsewhere.
    for field in config.declared_fields():
        assert not any(word in field.path.lower() for word in config.SECRET_WORDS), field.path


def test_an_empty_assignment_is_refused_rather_than_writing_nothing() -> None:
    for call in (lambda: config.set_values({}), lambda: config.unset_values(())):
        with pytest.raises(CliFailure, match="nothing was"):
            call()
