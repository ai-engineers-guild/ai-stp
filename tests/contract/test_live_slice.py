"""The live-slice evidence script refuses rather than produces false evidence."""

import inspect
from typing import Any, cast

import pytest
from release_scripts import _evidence, verify_live_slice


def test_an_entry_without_an_exact_version_is_not_evidence() -> None:
    """A listed object whose version is unknown proves nothing about parity."""
    rows: list[Any] = [{"stable_id": "component_1", "latest_version": "1.0"}]
    assert verify_live_slice._identifiers(rows, "test") == {  # pyright: ignore[reportPrivateUsage]
        "component_1": "1.0"
    }

    for broken in ([{"stable_id": "component_1"}], [{"latest_version": "1.0"}], ["component_1"]):
        with pytest.raises(_evidence.EvidenceError):
            verify_live_slice._identifiers(  # pyright: ignore[reportPrivateUsage]
                cast(list[Any], broken), "test"
            )


def test_both_catalogue_kinds_are_paired_with_the_collection_the_web_reads() -> None:
    # The parity check is the point: one surface rendering an object the other
    # does not is exactly what this script exists to catch, and it cannot catch
    # it for a kind that is not listed here.
    assert verify_live_slice.COLLECTIONS == {"component": "components", "setup": "setups"}


def test_an_unreachable_environment_fails_loudly_rather_than_silently(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Port 9 on loopback refuses immediately, so the failure path is exercised
    # without a network and without waiting out a timeout.
    assert verify_live_slice.main(["--origin", "https://127.0.0.1:9"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "live-slice:" in captured.err


def test_the_origin_is_required_rather_than_defaulted() -> None:
    """No default environment. A default is how the wrong one gets proved."""
    with pytest.raises(SystemExit):
        verify_live_slice.main([])


def test_the_scenarios_no_machine_can_run_are_named_rather_than_omitted() -> None:
    """`not_verified` is a verdict; silence reads as coverage.

    `docs/engineering/release-evidence.md` gives a skipped line `not_verified`
    rather than success. An artefact that simply omits the interactive login
    scenarios claims more than it proved, which is the failure mode this test
    exists to prevent — the keys are read out of the source so that removing
    one breaks the test rather than quietly shrinking the disclosure.
    """
    body = inspect.getsource(verify_live_slice.verify_live_slice)
    assert '"not_verified"' in body
    for scenario in (
        "google_login_and_device_registration",
        "github_login_on_an_isolated_account",
        "device_revocation_and_relogin",
    ):
        assert scenario in body, scenario


def test_a_page_that_names_one_version_may_carry_only_one_digest() -> None:
    """Two digests beside one version is refused, not resolved.

    `#371` is the live case: a machine projection naming `1.2` while showing
    the digest of `1.0`. Picking one of several here would decide by accident
    which release the evidence describes, so the ambiguity is the failure.
    """
    real = "sha256:" + "a" * 64
    other = "sha256:" + "b" * 64

    assert (
        verify_live_slice._single_digest(  # pyright: ignore[reportPrivateUsage]
            f"<p>Version 1.2</p><code>{real}</code>", "1.2", "url"
        )
        == real
    )

    with pytest.raises(_evidence.EvidenceError, match="does not name"):
        verify_live_slice._single_digest(  # pyright: ignore[reportPrivateUsage]
            f"<p>Version 1.0</p><code>{real}</code>", "1.2", "url"
        )
    with pytest.raises(_evidence.EvidenceError, match="no digest"):
        verify_live_slice._single_digest(  # pyright: ignore[reportPrivateUsage]
            "<p>Version 1.2</p>", "1.2", "url"
        )
    with pytest.raises(_evidence.EvidenceError, match="different digests"):
        verify_live_slice._single_digest(  # pyright: ignore[reportPrivateUsage]
            f"<p>Version 1.2</p><code>{real}</code><code>{other}</code>", "1.2", "url"
        )


def test_the_machine_projection_is_the_surface_an_agent_reads() -> None:
    # Checked against the API is necessary and not sufficient: both surfaces
    # read the same API and can still render it differently, which is `#371`.
    assert "/ai/" in verify_live_slice.MACHINE_PROJECTION
    assert "{collection}" in verify_live_slice.MACHINE_PROJECTION
    assert "{stable_id}" in verify_live_slice.MACHINE_PROJECTION
