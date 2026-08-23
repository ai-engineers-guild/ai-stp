"""What the API says about itself must be true of the build that is running."""

from __future__ import annotations

from importlib.metadata import version as installed_version

from ai_stp_api.settings import ServiceSettings


def test_the_advertised_version_is_the_installed_one() -> None:
    """`/v1/system/version` must not name a release that does not exist.

    The default used to be the literal `0.1.0` while every package in the
    workspace was `0.0.1`, so the deployed API advertised a version nothing had
    ever built — observed live at `https://nddev.asia/v1/system/version`.
    Nothing kept the two in step and no test compared them.
    """
    assert ServiceSettings().version == installed_version("ai-stp-api")
