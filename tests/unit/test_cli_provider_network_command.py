"""The CLI reports observed provider-network capability without optimism."""

from pathlib import Path

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.provider import network_launcher, protocol_v2


def test_unavailable_network_capability_remains_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.UNAVAILABLE,
        os_name="darwin",
        launcher_id=None,
        evidence=("no verified macOS launcher",),
    )
    monkeypatch.setattr(network_launcher, "discover_bubblewrap", lambda: (None, capability))

    report = select.provider_network({}).payload

    assert report.network_enforcement == "unavailable"
    assert not report.local_actions_available
    assert report.launcher_id == ""
    assert report.evidence == ["no verified macOS launcher"]


def test_enforced_capability_names_the_exact_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = Path("/usr/bin/bwrap")
    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
        os_name="linux",
        launcher_id=f"bubblewrap:{executable.as_posix()}",
        evidence=("sha256=" + "a" * 64, "IPv4/IPv6/DNS-UDP denied"),
    )
    launcher = network_launcher.BubblewrapLauncher(executable, capability)
    monkeypatch.setattr(network_launcher, "discover_bubblewrap", lambda: (launcher, capability))

    report = select.provider_network({}).payload

    assert report.network_enforcement == "enforced"
    assert report.local_actions_available
    assert report.launcher_id == "bubblewrap:/usr/bin/bwrap"
