"""The agent-facing `link web` command."""

import json
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli import app, config
from ai_stp_cli.commands import link
from ai_stp_contracts.deep_links import DeepLinkView

COMPONENT = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"


def test_link_web_is_pure_and_works_when_catalog_network_reads_are_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "schema_version: 1\ncatalog:\n  enabled: false\n  url: https://example.test/base\n",
        encoding="utf-8",
    )

    def network_would_be_a_bug(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("deep-link projection must not open an HTTP client")

    monkeypatch.setattr("httpx.Client", network_would_be_a_bug)
    answer = link.web(
        {
            "kind": "component",
            "id": COMPONENT,
            "version": "1.2",
            "locale": "en",
            "report": True,
        }
    )

    assert answer.payload == DeepLinkView.model_validate(answer.payload.model_dump())
    assert answer.payload.web_url == (
        f"https://example.test/base/en/catalog/components/{COMPONENT}/versions/1.2#report"
    )
    assert answer.payload.cli_argv[-2:] == ["--report", "--json"]


def test_cli_argv_from_one_result_reproduces_the_same_target(
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = link.web({"kind": "component", "id": COMPONENT, "version": "1.0"}).payload

    code = app.main(first.cli_argv[1:])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    envelope = cast(dict[str, object], json.loads(captured.out))
    second = DeepLinkView.model_validate(envelope["data"])
    assert second.target == first.target
    assert second.web_url == first.web_url
    assert second.cli_argv == first.cli_argv


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"kind": "publisher", "id": COMPONENT},
        {"kind": "component", "id": COMPONENT, "version": "latest"},
        {"kind": "component", "id": COMPONENT, "locale": "de"},
        {"kind": "component", "id": COMPONENT, "report": True},
    ],
)
def test_invalid_cli_targets_are_typed_validation_errors(
    parameters: dict[str, object],
) -> None:
    from ai_stp_cli.errors import CliFailure

    with pytest.raises(CliFailure) as raised:
        link.web(parameters)
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.details == {"contract": "deep_link_v1"}


def test_machine_failure_does_not_echo_untrusted_identifier(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_like = "token=must-not-appear"
    code = app.main(["link", "web", "--kind", "component", "--id", secret_like, "--json"])
    captured = capsys.readouterr()
    assert code == 2
    assert secret_like not in captured.out
    assert captured.err == ""


def test_link_command_does_not_create_local_state() -> None:
    link.web({"kind": "component", "id": COMPONENT})
    assert not config.config_path().exists()
    assert not Path(config.default_registry_path()).exists()
