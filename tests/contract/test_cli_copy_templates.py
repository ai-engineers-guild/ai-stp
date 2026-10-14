"""Web copy is generated from one owner; native verify.py checks its commands."""

import pytest

from ai_stp_contracts import cli_copy


def test_catalog_handoff_preserves_pin_without_inventing_local_install_facts() -> None:
    stable_id = "setup_01KZWSHE3V0T8KVJYFEKWJV63Z"
    prompt = cli_copy.install_setup_start(stable_id, "2.13")
    assert f"{stable_id} version 2.13" in prompt
    assert cli_copy.INTENTS_BOOTSTRAP in prompt
    assert "--input -" not in prompt
    assert cli_copy.install_task_start(stable_id, "2.14") != prompt
    with pytest.raises(ValueError):
        cli_copy.install_task_start("bad id with spaces")


def test_distribution_is_native_and_account_provider_is_explicit() -> None:
    assert (
        cli_copy.CLI_RELEASES_URL == "https://github.com/ai-engineers-guild/ai-stp/releases/latest"
    )
    assert cli_copy.login("github") != cli_copy.login("google")
    assert "--provider github" in cli_copy.login("github")
