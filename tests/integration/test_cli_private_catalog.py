"""Private HTTP acquisition, SQLite graph, native bundle, fork and revoked offline use."""

import json
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from tests.support.private_distribution import component_version, setup_version

from ai_stp_cli.cloud import catalog, private_access, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import component, registry, setup_compose, setup_publication
from ai_stp_cli.commands.select import compile_setup_version_bundle
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import acquired_trust, content, passports, revisions, versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.catalog import PrivateVersionResponse, PrivateVersionTrust
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport

pytestmark = pytest.mark.cli


def test_private_graph_acquires_compiles_forks_and_retains_bytes_after_revocation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    owner, recipient = new_id("account"), new_id("account")
    component_id, setup_id = new_id("component"), new_id("setup")
    component_document, component_bytes = component_version(owner, component_id, "1.0")
    setup_document, setup_bytes = setup_version(owner, setup_id, "1.0", component_document)
    documents = {component_id: component_document, setup_id: setup_document}
    artifacts = {component_id: component_bytes, setup_id: setup_bytes}
    held = session.Session(
        recipient,
        new_id("device"),
        "fixture-private-session",
        "fixture-refresh",
        session.expiry(3600),
    )
    secret_store, _warning = open_store()
    session.save(secret_store, held)
    passports.adopt(recipient)
    revoked = False
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if "authorization" not in request.headers:
            assert "cookie" not in request.headers
            return httpx.Response(404, json={"error": {"code": "AI_STP_NOT_FOUND"}})
        assert request.headers["authorization"] == f"Bearer {held.access_token}"
        if revoked:
            return httpx.Response(403, json={"error": {"code": "AI_STP_PERMISSION_DENIED"}})
        stable_id = path.split("/")[4]
        document = documents[stable_id]
        if path.endswith("/artifact"):
            return httpx.Response(200, content=artifacts[stable_id])
        response = PrivateVersionResponse(
            passport=document,
            passport_digest=digest_canonical("ai-stp:passport:v1", document),
            lifecycle="active",
            trust=PrivateVersionTrust(
                trust_lane="local_owner_or_pinned", author_verified=False, component_verified=False
            ),
            published_at=str(document["created_at"]),
        )
        return httpx.Response(200, json=response.model_dump(mode="json"))

    endpoint = Endpoint(
        "https://private.test", max_attempts=1, transport=httpx.MockTransport(serve)
    )
    monkeypatch.setattr(registry, "endpoint", lambda: endpoint)
    monkeypatch.setattr(setup_publication, "endpoint", lambda: endpoint)
    with pytest.raises(CliFailure) as public_only:
        catalog.version(endpoint, "setup", setup_id, "1.0")
    assert public_only.value.code == "AI_STP_NOT_FOUND"
    assert len(requests) == 1
    parameters = {"id": setup_id, "version": "1.0", "private": True}
    acquired = registry.acquire(parameters).payload
    assert acquired.passport_digest == digest_canonical("ai-stp:passport:v1", setup_document)
    assert len(acquired.components) == 1 and acquired.components[0].stable_id == component_id
    assert any(request.url.path.endswith("/private") for request in requests)
    assert any(request.url.path.endswith("/artifact") for request in requests)
    assert all("/access/" not in request.url.path for request in requests)
    manifest = tmp_path / "private-composition.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Private recipient setup",
                "description": "A private setup using an exact granted component.",
                "harness_id": "claude-code",
                "tags": ["private"],
                "components": [
                    {
                        "source": {
                            "kind": "catalog",
                            "stable_id": component_id,
                            "version": "1.0",
                            "passport_digest": digest_canonical(
                                "ai-stp:passport:v1", component_document
                            ),
                        }
                    }
                ],
            }
        )
    )
    composed = setup_compose.plan({"manifest": str(manifest)}).payload
    frozen = setup_compose.apply(
        {
            "manifest": str(manifest),
            "id": composed.setup_id,
            "created-at": composed.created_at,
            "expected-plan-digest": composed.plan_digest,
        }
    ).payload
    with closing(open_readonly(configured_path())) as db:
        record = versions.held(db, frozen.setup_id, frozen.version)
        assert record is not None
        revision = revisions.get(db, record.revision_id)
        assert revision is not None
        private_setup = SetupVersionPassport.model_validate(
            revision.envelope.model_dump(mode="json")
        )
        assert private_setup.visibility == "private"
        assert private_setup.components[0].stable_id == component_id
        assert compile_setup_version_bundle(
            db, frozen.setup_id, frozen.version, expected_harness="claude-code"
        ).archive
    publication = setup_publication.plan({**parameters, "visibility": "private"}).payload
    assert all(
        member.already_published and member.visibility == "private"
        for member in publication.members
    )
    replay = setup_publication.plan({**parameters, "visibility": "private"}).payload
    assert replay.set_digest == publication.set_digest
    with closing(open_readonly(configured_path())) as db:
        native = compile_setup_version_bundle(db, setup_id, "1.0", expected_harness="claude-code")
        assert native.archive
        original = versions.held(db, component_id, "1.0")
        assert original is not None
        original_revision = original.revision_id
        verdict = acquired_trust.verdicts(db)[(component_id, "1.0")]
        assert verdict.trust_lane == "local_owner_or_pinned" and not verdict.component_verified
    forked = component.fork({"id": component_id, "version": "1.0"}).payload
    assert forked.stable_id != component_id
    with closing(open_readonly(configured_path())) as db:
        fork = revisions.head(db, forked.stable_id)
        assert fork is not None and fork.envelope.owner_id == recipient
        assert fork.envelope.visibility == "private"
        original = versions.held(db, component_id, "1.0")
        assert original is not None and original.revision_id == original_revision
    revoked = True
    with pytest.raises(CliFailure) as denied:
        registry.acquire(parameters)
    assert denied.value.code == "AI_STP_PERMISSION_DENIED"
    before_offline = len(requests)
    cached = registry.acquire({**parameters, "offline": True}).payload
    assert cached.source == "cache" and len(requests) == before_offline
    with closing(open_readonly(configured_path())) as db:
        assert (
            content.get(
                db, ComponentVersionPassport.model_validate(component_document).artifact.digest
            )
            == component_bytes
        )
    session.save(secret_store, replace(held, account_id=new_id("account")))
    with pytest.raises(CliFailure) as missing:
        private_access.cached_version(endpoint, "setup", setup_id, "1.0")
    assert missing.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    session.save(secret_store, held)
    with pytest.raises(CliFailure) as missing:
        private_access.cached_version(
            replace(endpoint, base_url="https://another.test"), "setup", setup_id, "1.0"
        )
    assert missing.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


@pytest.mark.parametrize("defect", ["coordinate", "schema"])
def test_private_version_refuses_a_different_passport_inside_the_requested_envelope(
    defect: str,
) -> None:
    account = new_id("account")
    requested = new_id("component")
    other, _artifact = component_version(account, new_id("component"), "1.0")
    if defect == "schema":
        other["stable_id"] = requested
        other["component_type"] = "unknown"
    held = session.Session(
        account, new_id("device"), "fixture-access", "fixture-refresh", session.expiry(3600)
    )
    secret_store, _warning = open_store()
    session.save(secret_store, held)
    response = PrivateVersionResponse(
        passport=other,
        passport_digest=digest_canonical("ai-stp:passport:v1", other),
        lifecycle="active",
        trust=PrivateVersionTrust(
            trust_lane="local_owner_or_pinned", author_verified=False, component_verified=False
        ),
        published_at=str(other["created_at"]),
    )
    endpoint = Endpoint(
        "https://private.test",
        max_attempts=1,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=response.model_dump(mode="json"))
        ),
    )
    with pytest.raises(CliFailure) as refused:
        private_access.version(endpoint, "component", requested, "1.0")
    assert refused.value.code == "AI_STP_CATALOG_INTEGRITY"
    with pytest.raises(CliFailure) as missing:
        private_access.cached_version(endpoint, "component", requested, "1.0")
    assert missing.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
