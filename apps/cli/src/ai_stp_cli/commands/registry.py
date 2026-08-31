"""Public catalogue reads and exact local acquisition (issues #76 and #294).

Catalogue observation needs no account. Acquisition writes only verified,
immutable passports and bytes to the local registry; it never touches a target.

The catalogue can be switched off entirely (`catalog.enabled`), and then these
commands say so rather than reaching out anyway — offline is a supported
configuration, not a fault.
"""

import json
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from ai_stp_cli import config, identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import catalog
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    acquired_trust,
    cache,
    components,
    content,
    revisions,
    store_ports,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_cli.local.passports import moment
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.http import PAGE_SIZE_MAX
from ai_stp_contracts.machine_help import (
    AcquiredComponentVersion,
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
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ArtifactRef, ComponentVersionPassport, SetupVersionPassport

KINDS: tuple[CatalogKind, ...] = ("component", "setup")


def port_discover(parameters: Mapping[str, object]) -> Answer[StorePortDiscovery]:
    """Find compatible local setup-store snapshots without changing state."""
    return Answer(store_ports.discover(_port_root(parameters)))


def port_inspect(parameters: Mapping[str, object]) -> Answer[StorePortInspection]:
    """Show exact mappings, omissions and preserved metadata without importing."""
    return Answer(store_ports.inspect(_port_root(parameters), _port_adapter(parameters)))


def port_plan(parameters: Mapping[str, object]) -> Answer[StorePortImportPlan]:
    """Bind a local-only import preview to the exact manifest bytes."""
    return Answer(store_ports.plan(_port_root(parameters), _port_adapter(parameters)))


def port_import(parameters: Mapping[str, object]) -> Answer[StorePortImportResult]:
    """Apply one exact still-current plan to the local registry only."""
    expected = parameters.get("expected-plan-digest")
    if expected is None:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "the exact setup-store import plan digest is required",
            next_actions=[
                "registry port import --adapter <adapter> --root <path> "
                "--expected-plan-digest <digest> --json"
            ],
        )
    current, _warning = identity.load_or_create()
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        return Answer(
            store_ports.apply(
                connection,
                _port_root(parameters),
                _port_adapter(parameters),
                str(expected),
                device_id=current.device_id,
            )
        )


def _port_root(parameters: Mapping[str, object]) -> Path:
    value = parameters.get("root")
    if value is None:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "a setup-store root is required")
    return Path(str(value))


def _port_adapter(parameters: Mapping[str, object]) -> str:
    value = parameters.get("adapter")
    if value is None:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "a setup-store adapter is required")
    return str(value)


def endpoint() -> Endpoint:
    """Where the catalogue is, refusing to reach out when it is switched off."""
    report = config.effective_config()
    values = {value.path: value.value for value in report.values}
    if not values["catalog.enabled"]:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the public catalogue is switched off in this configuration",
            details={"field": "catalog.enabled"},
            next_actions=["config show --json"],
        )
    return Endpoint(str(values["catalog.url"]))


def _kind(raw: object) -> CatalogKind:
    if raw is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a catalogue kind is required",
            details={"allowed": ", ".join(KINDS)},
            next_actions=["registry search --kind component --json"],
        )
    value = str(raw)
    if value not in KINDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"unknown catalogue kind: {value}",
            details={"allowed": ", ".join(KINDS)},
        )
    return value  # pyright: ignore[reportReturnType]


def _limit(value: object) -> int | None:
    """Bound `--limit` here, and refuse in the words a person used.

    It travelled to the platform unchecked, so an out-of-range value came back
    as `a supplied value is not valid for this command: page_size` — a field
    that appears in no help text and on no command line. `PAGE_SIZE_MAX` is a
    published contract constant, so the answer is available locally and costs no
    round trip that can only fail.
    """
    if value is None:
        return None
    try:
        found = int(str(value))
    except ValueError as error:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--limit must be a whole number") from error
    if not 1 <= found <= PAGE_SIZE_MAX:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"--limit must be between 1 and {PAGE_SIZE_MAX}; "
            "walk the pages with --cursor to read more",
            details={"limit": str(found)},
        )
    return found


def search(parameters: Mapping[str, object]) -> Answer[CatalogSearchResult]:
    """One page of public results, in a stable order and without duplicates.

    Not cached: a page is a view over a moving collection, and serving
    yesterday's page as today's would break the one property pagination has to
    keep — that walking the cursors visits each object once.
    """
    query = parameters.get("query")
    limit = _limit(parameters.get("limit"))
    return Answer(
        catalog.search(
            endpoint(),
            _kind(parameters.get("kind")),
            query=None if query is None else str(query),
            cursor=None if parameters.get("cursor") is None else str(parameters["cursor"]),
            page_size=limit,
            include_experimental=bool(parameters.get("include-experimental")),
        )
    )


def version(parameters: Mapping[str, object]) -> Answer[CatalogVersionView]:
    """One exact version and its passport, verified against the published digest.

    A passport offered under a digest that does not describe it is a truncated
    download or a substituted body, and both are refused rather than cached.
    """
    stable_id = parameters.get("id")
    number = parameters.get("version")
    if stable_id is None or number is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an object identifier and a version are both required",
            next_actions=["registry show --kind component --id <id> --json"],
        )
    return Answer(
        catalog.version(endpoint(), _kind(parameters.get("kind")), str(stable_id), str(number))
    )


def show(parameters: Mapping[str, object]) -> Answer[CatalogObjectView]:
    """One object with its versions, from the platform or from the local cache.

    A cached answer says `source: cache` and carries the moment it was true.
    An answer the platform actually gave — including "no such object" — is never
    served from the cache, because that would resurrect something the catalogue
    has stopped offering.
    """
    stable_id = parameters.get("id")
    if stable_id is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an object identifier is required",
            next_actions=["registry search --kind component --json"],
        )
    return Answer(catalog.show(endpoint(), _kind(parameters.get("kind")), str(stable_id)))


def fetch(parameters: Mapping[str, object]) -> Answer[CatalogArtifactView]:
    """Fetch the exact bytes of one version into the local cache, verified.

    The expected digest and size come from the version's own passport, which
    this reads first. Verifying against the passport rather than against the
    response is the whole point: headers from the server that sent the bytes
    cannot attest to them, and without an independent expectation a public
    catalogue is a demonstration rather than something to install from.

    A second call with the same version does not use the network: the cache is
    addressed by content, so a file that is present is known to be the right one.
    """
    stable_id = parameters.get("id")
    number = parameters.get("version")
    if stable_id is None or number is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an object identifier and a version are both required",
            next_actions=["registry show --kind component --id <id> --json"],
        )
    kind = _kind(parameters.get("kind"))
    view = catalog.version(endpoint(), kind, str(stable_id), str(number))
    expected = _artifact_of(view)
    held = cache.stored_version_artifact(expected.digest)
    path = catalog.fetch_artifact(endpoint(), kind, str(stable_id), str(number), expected)
    return Answer(
        CatalogArtifactView(
            kind=kind,
            source="cache" if held is not None else "online",
            checked_at=view.checked_at,
            stable_id=str(stable_id),
            version=str(number),
            digest=expected.digest,
            size_bytes=expected.size_bytes,
            path=redact_home(path),
        )
    )


@dataclass(frozen=True)
class AcquiredCatalogVersion:
    view: CatalogVersionView
    passport: ComponentVersionPassport | SetupVersionPassport
    artifact: bytes


def acquire(parameters: Mapping[str, object]) -> Answer[CatalogSetupAcquisition]:
    """Materialize one published setup and its complete exact graph atomically."""
    stable_id = str(parameters.get("id") or "")
    number = str(parameters.get("version") or "")
    offline = bool(parameters.get("offline"))
    if not stable_id or not number:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a setup identifier and exact version are both required",
            next_actions=["registry search --kind setup --json"],
        )

    setup = acquire_version("setup", stable_id, number, offline=offline)
    assert isinstance(setup.passport, SetupVersionPassport)
    _validate_setup_definition(setup)

    acquired: dict[str, AcquiredCatalogVersion] = {}
    pending = list(setup.passport.components)
    pinned: dict[str, tuple[str, str]] = {}
    while pending:
        reference = pending.pop(0)
        exact = (reference.version, reference.passport_digest)
        previous = pinned.get(reference.stable_id)
        if previous is not None:
            if previous != exact:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "the published setup graph pins two versions of one component",
                    details={"stable_id": reference.stable_id},
                )
            continue
        pinned[reference.stable_id] = exact
        item = acquire_version("component", reference.stable_id, reference.version, offline=offline)
        if item.view.passport_digest != reference.passport_digest:
            raise CliFailure(
                "AI_STP_CATALOG_INTEGRITY",
                "a component passport differs from the exact setup reference",
                details={
                    "stable_id": reference.stable_id,
                    "expected": reference.passport_digest,
                    "found": item.view.passport_digest,
                },
            )
        assert isinstance(item.passport, ComponentVersionPassport)
        if item.passport.harness_id != setup.passport.harness_id:
            raise CliFailure(
                "AI_STP_CATALOG_INTEGRITY",
                "a component in the setup graph belongs to another harness",
                details={"stable_id": reference.stable_id},
            )
        acquired[reference.stable_id] = item
        pending.extend(item.passport.requires_components)

    current, _warning = identity.load_or_create()
    at = moment()
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        for item in [*acquired.values(), setup]:
            stored_artifact = content.put(connection, item.artifact, at=at)
            if stored_artifact.digest != item.passport.artifact.digest:
                raise CliFailure(
                    "AI_STP_CATALOG_INTEGRITY",
                    "verified catalogue bytes changed before local materialization",
                )
            document = cast(dict[str, JsonValue], item.passport.model_dump(mode="json"))
            document.pop("revision_id", None)
            stored = revisions.commit(connection, document, device_id=current.device_id)
            versions.record(
                connection,
                stable_id=item.passport.stable_id,
                version=item.passport.version,
                passport_digest=item.view.passport_digest,
                revision_id=stored.revision_id,
                at=at,
            )
            # What the catalogue said about this version, recorded here because
            # this is the only moment it is known. Without it every acquired
            # object reads as the user's own work (`#447`).
            acquired_trust.record(
                connection,
                stable_id=item.passport.stable_id,
                version=item.passport.version,
                passport_digest=item.view.passport_digest,
                verdict=acquired_trust.Verdict(
                    trust_lane=item.view.trust.trust_lane,
                    author_verified=item.view.trust.author_verified,
                    component_verified=item.view.trust.component_verified,
                ),
                at=at,
            )

    source = (
        "cache"
        if all(item.view.source == "cache" for item in [*acquired.values(), setup])
        else "online"
    )
    return Answer(
        CatalogSetupAcquisition(
            source=source,
            checked_at=setup.view.checked_at,
            stable_id=setup.passport.stable_id,
            version=setup.passport.version,
            passport_digest=setup.view.passport_digest,
            artifact_digest=setup.passport.artifact.digest,
            harness_id=setup.passport.harness_id,
            components=[
                AcquiredComponentVersion(
                    stable_id=item.passport.stable_id,
                    version=item.passport.version,
                    passport_digest=item.view.passport_digest,
                    artifact_digest=item.passport.artifact.digest,
                )
                for item in acquired.values()
            ],
        )
    )


def acquire_version(
    kind: CatalogKind, stable_id: str, number: str, *, offline: bool
) -> AcquiredCatalogVersion:
    view = (
        catalog.cached_version(kind, stable_id, number)
        if offline
        else catalog.version(endpoint(), kind, stable_id, number)
    )
    model = ComponentVersionPassport if kind == "component" else SetupVersionPassport
    try:
        passport = model.model_validate(view.passport)
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY",
            "the published passport is not a complete version passport",
            details={"kind": kind, "stable_id": stable_id, "version": number},
        ) from error
    if passport.stable_id != stable_id or passport.version != number:
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY",
            "the published passport identity does not match the requested version",
            details={"kind": kind, "stable_id": stable_id, "version": number},
        )
    # Seal is over the published document. A model dump injects later default
    # fields and is not what `revision_id` hashed.
    if view.passport.get("revision_id") != derive_revision_id(view.passport):
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY",
            "the published passport identity does not match the requested version",
            details={"kind": kind, "stable_id": stable_id, "version": number},
        )
    expected = passport.artifact
    held = cache.stored_version_artifact(expected.digest)
    if held is None and offline:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the exact version artifact is not available in the verified cache",
            details={"kind": kind, "stable_id": stable_id, "version": number},
            next_actions=[f"registry acquire --id {stable_id} --version {number} --json"],
        )
    path = held or catalog.fetch_artifact(endpoint(), kind, stable_id, number, expected)
    artifact = Path(path).read_bytes()
    if (
        len(artifact) != expected.size_bytes
        or digest_bytes("ai-stp:artifact:v1", artifact) != expected.digest
    ):
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY",
            "the cached version artifact no longer matches its published passport",
            details={"kind": kind, "stable_id": stable_id, "version": number},
        )
    if isinstance(passport, ComponentVersionPassport):
        component_document = cast(dict[str, JsonValue], passport.model_dump(mode="json"))
        components.expand(artifact, str(component_document.get("artifact_format") or ""))
    return AcquiredCatalogVersion(view, passport, artifact)


def _validate_setup_definition(acquired: AcquiredCatalogVersion) -> None:
    assert isinstance(acquired.passport, SetupVersionPassport)
    try:
        document = cast(dict[str, JsonValue], json.loads(acquired.artifact))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY", "the setup definition artifact is not canonical JSON"
        ) from error
    expected_refs = acquired.view.passport.get("components")
    if (
        canonize(cast(JsonValue, document)) != acquired.artifact
        or document.get("stable_id") != acquired.passport.stable_id
        or document.get("version") != acquired.passport.version
        or document.get("harness_id") != acquired.passport.harness_id
        or document.get("components") != expected_refs
    ):
        raise CliFailure(
            "AI_STP_CATALOG_INTEGRITY",
            "the setup definition does not match its published passport",
            details={"stable_id": acquired.passport.stable_id},
        )


def _artifact_of(view: CatalogVersionView) -> ArtifactRef:
    """The artifact this version declares, refusing a passport that declares none.

    A published version without an artifact reference cannot be installed and
    cannot be verified; saying so here is better than downloading bytes nothing
    can be checked against.
    """
    held = view.passport.get("artifact")
    if not isinstance(held, dict):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this version's passport declares no artifact",
            details={"version": view.passport_digest},
            next_actions=["registry version --json"],
        )
    try:
        return ArtifactRef.model_validate(held)
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "this version's passport declares an artifact this build cannot read",
            next_actions=["registry version --json"],
        ) from error
