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
    monkeypatch.setattr(network_launcher, "discover_launcher", lambda: (None, capability))

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
    monkeypatch.setattr(network_launcher, "discover_launcher", lambda: (launcher, capability))

    report = select.provider_network({}).payload

    assert report.network_enforcement == "enforced"
    assert report.local_actions_available
    assert report.launcher_id == "bubblewrap:/usr/bin/bwrap"


def test_the_report_answers_for_the_protocol_that_is_actually_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`provider network` described v2 only, and v3 is where the debt lives.

    This is the one output someone checks to find out whether a provider runs
    with the network denied. It reported protocol v2 — which nothing installs
    with any more — and said nothing at all about v3, where `#416` deliberately
    allows a local phase to run **unisolated** on a platform with no launcher,
    gated on a trusted release or an explicit `--unverified-provider`.

    On Windows without a proved AppContainer the report read `unavailable` /
    local actions `false`, which is true of v2 and the opposite of what a trusted
    v3 install then does. A debt whose only visible marker describes a different
    protocol is a debt nobody finds.

    What must not change, and does not: v2 enforcement is still `unavailable`
    and is never called `enforced`. The v3 terms are added beside it, named,
    rather than folded into the v2 answer.
    """
    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.UNAVAILABLE,
        os_name="windows",
        launcher_id=None,
        evidence=("Bubblewrap launcher is Linux-only",),
    )
    monkeypatch.setattr(network_launcher, "discover_launcher", lambda: (None, capability))

    report = select.provider_network({}).payload

    # Unchanged, and deliberately so.
    assert report.network_enforcement == "unavailable"
    assert not report.local_actions_available

    # Added: what a v3 local phase actually does here, and on what terms.
    assert report.v3_local_phase == "unisolated_by_trust"
    assert sorted(report.v3_local_phase_reasons) == [
        network_launcher.EXPLICIT_UNVERIFIED_PROVIDER,
        network_launcher.TRUSTED_RELEASE,
    ]


def test_a_platform_that_can_deny_the_network_says_so_for_v3_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux with a proved launcher grants no exception and needs none."""
    executable = Path("/usr/bin/bwrap")
    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
        os_name="linux",
        launcher_id=f"bubblewrap:{executable.as_posix()}",
        evidence=("sha256=" + "a" * 64, "IPv4/IPv6/DNS-UDP denied"),
    )
    launcher = network_launcher.BubblewrapLauncher(executable, capability)
    monkeypatch.setattr(network_launcher, "discover_launcher", lambda: (launcher, capability))

    report = select.provider_network({}).payload

    assert report.v3_local_phase == "network_denied"
    assert report.v3_local_phase_reasons == []


def test_linux_without_the_launcher_is_a_refusal_and_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A skipped capability and a missing one must not share an answer.

    On Linux the absence of `bwrap` is a missing dependency; on Windows it is a
    missing capability of the operating system. `unisolated_local_phase` refuses
    to be built on Linux for exactly that reason, and the report has to say the
    same thing rather than blur the two into one `unavailable`.
    """
    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.UNAVAILABLE,
        os_name="linux",
        launcher_id=None,
        evidence=("bwrap executable is absent",),
    )
    monkeypatch.setattr(network_launcher, "discover_launcher", lambda: (None, capability))

    report = select.provider_network({}).payload

    assert report.v3_local_phase == "refused"
    assert report.v3_local_phase_reasons == []
