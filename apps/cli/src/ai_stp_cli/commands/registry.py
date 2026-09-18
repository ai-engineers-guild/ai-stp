"""Public catalogue reads and exact local acquisition. Effects live in `application.catalog`."""

from ai_stp_cli.application import catalog as _service
from ai_stp_cli.application.catalog import (
    AcquiredCatalogVersion,
    acquire,
    acquire_version,
    endpoint,
    fetch,
    port_discover,
    port_import,
    port_inspect,
    port_plan,
    search,
    show,
    version,
)


def __getattr__(name: str) -> object:
    return getattr(_service, name)


__all__ = [
    "AcquiredCatalogVersion",
    "acquire",
    "acquire_version",
    "endpoint",
    "fetch",
    "port_discover",
    "port_import",
    "port_inspect",
    "port_plan",
    "search",
    "show",
    "version",
]
