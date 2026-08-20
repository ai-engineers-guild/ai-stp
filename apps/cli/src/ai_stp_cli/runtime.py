"""Installed CLI runtime identity shared by commands and local evidence."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

DISTRIBUTION = "ai-stp-cli"
UNKNOWN_VERSION = "0.0.0+unknown"


def cli_version() -> str:
    """Return the installed distribution version without inventing one."""
    try:
        return package_version(DISTRIBUTION)
    except PackageNotFoundError:
        return UNKNOWN_VERSION
