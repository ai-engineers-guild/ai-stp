"""Public catalogue reads and exact local acquisition. Effects live in `application.catalog`."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.application import catalog as _service
from ai_stp_cli.application.catalog import AcquiredCatalogVersion
from ai_stp_contracts.machine_help import (
    CatalogArtifactView,
    CatalogKind,
    CatalogObjectView,
    CatalogSearchResult,
    CatalogSetupAcquisition,
    CatalogVersionView,
)
from ai_stp_contracts.store_ports import (
    StorePortDiscovery,
    StorePortImportPlan,
    StorePortImportResult,
    StorePortInspection,
)


def __getattr__(name: str) -> object:
    return getattr(_service, name)


def acquire(parameters: Mapping[str, object]) -> Answer[CatalogSetupAcquisition]:
    return _service.acquire(parameters)


def acquire_version(
    kind: CatalogKind,
    stable_id: str,
    number: str,
    *,
    offline: bool,
    include_private: bool = False,
) -> AcquiredCatalogVersion:
    return _service.acquire_version(
        kind, stable_id, number, offline=offline, include_private=include_private
    )


def fetch(parameters: Mapping[str, object]) -> Answer[CatalogArtifactView]:
    return _service.fetch(parameters)


def port_discover(parameters: Mapping[str, object]) -> Answer[StorePortDiscovery]:
    return _service.port_discover(parameters)


def port_inspect(parameters: Mapping[str, object]) -> Answer[StorePortInspection]:
    return _service.port_inspect(parameters)


def port_plan(parameters: Mapping[str, object]) -> Answer[StorePortImportPlan]:
    return _service.port_plan(parameters)


def port_import(parameters: Mapping[str, object]) -> Answer[StorePortImportResult]:
    return _service.port_import(parameters)


def search(parameters: Mapping[str, object]) -> Answer[CatalogSearchResult]:
    return _service.search(parameters)


def show(parameters: Mapping[str, object]) -> Answer[CatalogObjectView]:
    return _service.show(parameters)


def version(parameters: Mapping[str, object]) -> Answer[CatalogVersionView]:
    return _service.version(parameters)
