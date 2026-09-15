"""Installed CLI runtime identity shared by commands and local evidence."""

import json
from importlib.metadata import PackageNotFoundError, distribution
from importlib.metadata import version as package_version
from typing import Literal

DISTRIBUTION = "ai-stp-cli"
UNKNOWN_VERSION = "0.0.0+unknown"

Installation = Literal["distribution", "source"]


def cli_version() -> str:
    """Return the installed distribution version without inventing one."""
    try:
        return package_version(DISTRIBUTION)
    except PackageNotFoundError:
        return UNKNOWN_VERSION


def installation() -> Installation:
    """Whether this process loaded a published wheel or this checkout.

    An editable or path install still reports a version string. Direct URL
    metadata is what distinguishes that from a registry wheel, which is the
    lie `capabilities` used to tell when two builds shared one version.
    """
    try:
        dist = distribution(DISTRIBUTION)
    except PackageNotFoundError:
        return "source"
    origin = dist.read_text("direct_url.json")
    if origin is None:
        return "distribution"
    try:
        payload = json.loads(origin)
    except json.JSONDecodeError:
        return "source"
    if isinstance(payload, dict) and "dir_info" in payload:
        return "source"
    return "distribution"
