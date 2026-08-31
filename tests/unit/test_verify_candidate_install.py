"""Cross-platform installation evidence reads the environment uv actually creates."""

from pathlib import Path

import pytest
from release_scripts import verify_candidate_install


@pytest.mark.parametrize(
    "relative",
    (Path("ai-stp-cli/lib/python3.14/site-packages"), Path("ai-stp-cli/Lib/site-packages")),
)
def test_direct_provenance_accepts_posix_and_windows_site_packages(
    tmp_path: Path, relative: Path
) -> None:
    site_packages = tmp_path / relative
    record = site_packages / "ai_stp_cli-0.0.10.dist-info" / "direct_url.json"
    record.parent.mkdir(parents=True)
    wheel = tmp_path / "ai_stp_cli-0.0.10-py3-none-any.whl"
    wheel.write_bytes(b"candidate-wheel")
    record.write_text(
        '{"url":"' + wheel.as_uri() + '","archive_info":{}}',
        encoding="utf-8",
    )

    observed = verify_candidate_install._direct_wheel_provenance(  # pyright: ignore[reportPrivateUsage]
        tmp_path, {"ai-stp-cli": wheel}
    )

    assert set(observed) == {"ai-stp-cli"}


def test_direct_provenance_refuses_an_ambiguous_environment(tmp_path: Path) -> None:
    (tmp_path / "ai-stp-cli/lib/python3.14/site-packages").mkdir(parents=True)
    (tmp_path / "ai-stp-cli/Lib/site-packages").mkdir(parents=True)

    with pytest.raises(verify_candidate_install.InstallVerificationError, match="unique"):
        verify_candidate_install._direct_wheel_provenance(  # pyright: ignore[reportPrivateUsage]
            tmp_path, {}
        )


def test_network_report_option_names_the_pre_removal_evidence_path() -> None:
    options = verify_candidate_install._parser().parse_args(  # pyright: ignore[reportPrivateUsage]
        ["candidate", "--network-report", "evidence/network.json"]
    )

    assert options.network_report == Path("evidence/network.json")
