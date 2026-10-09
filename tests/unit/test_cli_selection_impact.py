"""Context, capability and local blast-radius reports (issue #307)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, impact, revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import versions as corpus_versions
from ai_stp_contracts.impact import ComponentTokenMeasurement, ExactCoordinate
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports import SetupVersionPassport
from ai_stp_passports.envelope import seal_envelope, verify_revision_id

AT = "2026-08-13T12:00:00.000Z"


def _shared_corpus() -> tuple[FirstPartyVersion, FirstPartyVersion, FirstPartyVersion]:
    """One component, and two local setups that both pin it.

    The corpus used to carry twelve role setups per pair of harnesses, six of
    them sharing components, so this could be found by search. Rebuilt from the
    live setup systems it carries exactly one setup per harness, and the shape
    this exercises — two selections overlapping on one component — is a property
    of the local registry rather than of the published catalogue.

    So the second setup is derived here instead of hunted for: the same members
    minus the last one, resealed under a new identifier. Nothing about the
    report under test depends on where the second selection came from, and a
    fixture that says what it needs does not go stale when somebody else's
    builder tree changes.
    """
    corpus = corpus_versions()
    base = max(
        (item for item in corpus if item.passport.kind == "setup"),
        key=lambda item: len(
            SetupVersionPassport.model_validate(item.passport.model_dump(mode="json")).components
        ),
    )
    base_passport = SetupVersionPassport.model_validate(base.passport.model_dump(mode="json"))
    assert len(base_passport.components) > 1, "the derivation needs a member to drop"
    kept = base_passport.components[:-1]

    body = base.passport.model_dump(mode="json")
    body.pop("revision_id")
    body["stable_id"] = "setup_01J0000000000000000000000A"
    body["name"] = f"{body['name']} (subset)"
    body["components"] = [item.model_dump(mode="json") for item in kept]
    sealed = SetupVersionPassport.model_validate(seal_envelope(body).model_dump(mode="json"))
    assert verify_revision_id(sealed)
    derived = FirstPartyVersion(
        kind="setup",
        passport=sealed,
        passport_digest=digest_bytes(
            "ai-stp:passport:v1", canonize(cast(JsonValue, sealed.model_dump(mode="json")))
        ),
        artifact=base.artifact,
        artifact_format=base.artifact_format,
        source_tree=base.source_tree,
    )
    component = next(
        item
        for item in corpus
        if item.passport.kind == "component" and item.passport.stable_id == kept[0].stable_id
    )
    return component, derived, base


def _materialize(*setups: FirstPartyVersion) -> None:
    corpus = corpus_versions()
    wanted = {
        ref.stable_id
        for setup in setups
        for ref in SetupVersionPassport.model_validate(
            setup.passport.model_dump(mode="json")
        ).components
    }
    # The setups are recorded as given rather than looked up: one of them is
    # derived here and is deliberately not a member of the published corpus.
    selected = [
        *setups,
        *(
            item
            for item in corpus
            if item.passport.kind == "component" and item.passport.stable_id in wanted
        ),
    ]
    with (
        closing(open_registry(configured_path(), create=True)) as connection,
        transaction(connection),
    ):
        for item in selected:
            content.put(connection, item.artifact, at=AT)
            document = item.passport.model_dump(mode="json")
            document.pop("revision_id")
            stored = revisions.commit(connection, document, device_id="device_test")
            versions.record(
                connection,
                stable_id=item.passport.stable_id,
                version=item.passport.version,
                passport_digest=item.passport_digest,
                revision_id=stored.revision_id,
                at=AT,
            )


def test_report_has_absolute_delta_local_estimator_and_no_implicit_price() -> None:
    _component, baseline, candidate = _shared_corpus()
    _materialize(baseline, candidate)

    report = select.impact_report(
        {
            "setup-id": candidate.passport.stable_id,
            "setup-version": candidate.passport.version,
            "against-setup-id": baseline.passport.stable_id,
            "against-setup-version": baseline.passport.version,
        }
    ).payload

    assert report.freshness == "local_snapshot"
    assert report.estimator.profile == "ai-stp:unicode-chars-div4/1"
    assert report.estimator.local_only is True
    assert report.candidate_context.conditional_tokens > 0
    assert report.baseline_context is not None
    assert report.baseline_source == "explicit"
    assert report.context_delta is not None
    assert report.context_delta.conditional_tokens == (
        report.candidate_context.conditional_tokens - report.baseline_context.conditional_tokens
    )
    assert report.capability_delta is not None
    assert report.token_cost.status == "unavailable"
    assert report.token_cost.reason == "price_profile_not_supplied"


def test_explicit_stale_price_is_labelled_and_never_used(tmp_path: Path) -> None:
    _component, setup, _other = _shared_corpus()
    _materialize(setup)
    price = tmp_path / "price.json"
    price.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "test-price-1",
                "tokenizer_profile": "ai-stp:unicode-chars-div4/1",
                "model": "test-model",
                "currency": "USD",
                "input_per_million": "2.50",
                "source": "https://example.test/pricing",
                "fetched_at": "2025-01-01T00:00:00.000Z",
                "expires_at": "2025-02-01T00:00:00.000Z",
            }
        ),
        encoding="utf-8",
    )

    report = select.impact_report(
        {
            "setup-id": setup.passport.stable_id,
            "setup-version": setup.passport.version,
            "price-profile": str(price),
        }
    ).payload

    assert report.token_cost.status == "stale"
    assert report.token_cost.amount is None
    assert report.token_cost.source == "https://example.test/pricing"


def test_project_baseline_uses_the_current_local_selection() -> None:
    _component, baseline, candidate = _shared_corpus()
    _materialize(baseline, candidate)
    project_id = "project_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    with closing(open_registry(configured_path())) as connection, transaction(connection):
        assert isinstance(baseline.passport, SetupVersionPassport)
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
            (project_id, AT),
        )
        connection.execute(
            """
            INSERT INTO selected_version
                (project_id, harness_id, stable_id, version, state, selected_at)
            VALUES (?, ?, ?, ?, 'pending_install', ?)
            """,
            (
                project_id,
                baseline.passport.harness_id,
                baseline.passport.stable_id,
                baseline.passport.version,
                AT,
            ),
        )

    report = select.impact_report(
        {
            "setup-id": candidate.passport.stable_id,
            "setup-version": candidate.passport.version,
            "project-id": project_id,
        }
    ).payload

    assert report.baseline_source == "selected"
    assert report.baseline_setup is not None
    assert report.baseline_setup.stable_id == baseline.passport.stable_id
    assert report.context_delta is not None


def test_blast_radius_returns_every_shared_local_setup_without_effects() -> None:
    component, first, second = _shared_corpus()
    _materialize(first, second)

    report = select.blast_radius(
        {
            "component-id": component.passport.stable_id,
            "component-version": component.passport.version,
            "scenario": "advisory",
        }
    ).payload

    assert report.authority_boundary == "local_registry"
    assert report.action == "none"
    assert {item.stable_id for item in report.setup_versions} == {
        first.passport.stable_id,
        second.passport.stable_id,
    }
    assert report.projects == []
    assert report.devices == []
    assert report.installed_targets == []


def test_invalid_exact_graph_is_refused_instead_of_partially_reported() -> None:
    _component, setup, _other = _shared_corpus()
    _materialize(setup)
    with closing(open_registry(configured_path())) as connection, transaction(connection):
        connection.execute(
            "UPDATE object_version SET passport_digest = ? WHERE stable_id = ?",
            (
                "sha256:" + "0" * 64,
                SetupVersionPassport.model_validate(setup.passport.model_dump(mode="json"))
                .components[0]
                .stable_id,
            ),
        )

    with pytest.raises(CliFailure) as failure:
        select.impact_report(
            {"setup-id": setup.passport.stable_id, "setup-version": setup.passport.version}
        )
    assert failure.value.code == "AI_STP_CONFLICT"


def test_measurement_contract_separates_exact_estimated_and_unavailable() -> None:
    coordinate = ExactCoordinate(
        stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        version="1.0",
        passport_digest="sha256:" + "1" * 64,
    )
    exact = ComponentTokenMeasurement(
        component=coordinate,
        component_type="instruction",
        loading="always",
        status="exact",
        tokens=12,
        utf8_bytes=12,
    )
    estimated = exact.model_copy(update={"status": "estimated", "tokens": 3})
    unavailable = exact.model_copy(
        update={"status": "unavailable", "tokens": None, "reason": "content_is_not_utf8"}
    )

    assert (exact.status, estimated.status, unavailable.status) == (
        "exact",
        "estimated",
        "unavailable",
    )
    with pytest.raises(ValueError, match="omit tokens"):
        ComponentTokenMeasurement(
            component=coordinate,
            component_type="skill",
            loading="conditional",
            status="unavailable",
            tokens=1,
            utf8_bytes=1,
        )


def test_imported_component_envelope_is_decoded_and_corruption_is_refused() -> None:
    files = impact._files(  # pyright: ignore[reportPrivateUsage]
        b'{"files":[{"content_base64":"aGVsbG8=","path":"AGENTS.md"}],'
        b'"format":"ai-stp-imported-component/1"}',
        impact.IMPORTED_COMPONENT_FORMAT,
    )
    assert [(item.path, item.content) for item in files] == [("AGENTS.md", b"hello")]

    with pytest.raises(CliFailure) as corrupt:
        impact._files(  # pyright: ignore[reportPrivateUsage]
            b'{"files":[{"content_base64":"***","path":"AGENTS.md"}],'
            b'"format":"ai-stp-imported-component/1"}',
            impact.IMPORTED_COMPONENT_FORMAT,
        )
    assert corrupt.value.code == "AI_STP_CONFLICT"


def _adopted_draft(
    connection: sqlite3.Connection, suffix: str, *, component_type: str = "skill"
) -> tuple[str, str]:
    """A component exactly as `component adopt` leaves it, released to `1.0`.

    Kind, content and source facts and nothing else: no name, no description,
    no licence, no tags, no projection kind. This is the state every adopted
    component is in, and the state `propose → confirm → install` accepts.
    """
    from ai_stp_cli.local import cache, passports

    stable_id = f"component_01J0000000000000000000000{suffix}"
    artifact = content.put(connection, b"# adopted skill\n", at=AT)
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, AT),
    )

    def fact(value: JsonValue) -> JsonValue:
        return {"value": value, "origin": "observed", "confirmation": "none", "observed_at": AT}

    document: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": passports.owner().account_id,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            "harness_id": fact("claude-code"),
            "component_type": fact(component_type),
            "content_digest": fact(artifact.digest),
            "content_format": fact("ai-stp-component-file/1"),
            "source_name": fact("probe"),
            "native_ids": fact(["probe"]),
            "required_env": fact([{"name": "PROBE_TOKEN", "sensitive": True}]),
        },
    }
    stored = revisions.commit(connection, document, device_id="device_test")
    digest = cache.digest_of(stored.envelope.model_dump(mode="json"))
    versions.record(
        connection,
        stable_id=stable_id,
        version="1.0",
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=AT,
    )
    return stable_id, digest


def _confirmed_over(
    connection: sqlite3.Connection, root: Path, stable_id: str, digest: str
) -> tuple[str, str]:
    """A private SetupVersion pinning exactly that adopted component."""
    from ai_stp_cli.local import passports, project_passport, selection

    passports.init_developer(connection, device_id="device_test")
    passports.ensure_device(connection, device_id="device_test")
    found = project_passport.scan(connection, root)
    project_passport.record(connection, found, device_id="device_test")
    developer_id = passports.developer_stable_id(connection)
    device_id = passports.device_stable_id(connection)
    assert developer_id is not None and device_id is not None
    developer = revisions.head(connection, developer_id)
    device = revisions.head(connection, device_id)
    project = revisions.head(connection, found.stable_id)
    assert developer is not None and device is not None and project is not None
    context = selection.Context(
        project_id=found.stable_id,
        harness_id="claude-code",
        developer_revision=developer.revision_id,
        device_revision=device.revision_id,
        project_revision=project.revision_id,
        policy_version="selection-policy/1;result_limit=20",
    )
    member = selection.Member(stable_id, "1.0", digest, "local_owner_or_pinned", "own")
    proposal = selection.propose(
        connection,
        context=context,
        members=(member,),
        at=AT,
        expires_at="2099-01-01T00:00:00.000Z",
    )
    confirmed = selection.confirm(
        connection,
        proposal.proposal_id,
        context=context,
        owner_id=passports.owner().account_id,
        device_id="device_test",
        at=AT,
    )
    connection.commit()
    return confirmed.stable_id, confirmed.version


def test_a_locally_adopted_draft_is_reported_without_publication_fields(tmp_path: Path) -> None:
    """`#66`: two read-only reports demanded what the install path does not.

    A component adopted and released locally goes through `propose → confirm
    → install plan → apply`. The same version was refused by `select impact`
    and `select blast-radius` with `AI_STP_CONFLICT` naming `description,
    license, name, projection_kind, tags` — publication metadata that neither
    report reads. Both answer now, from the draft's own facts.
    """
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id, digest = _adopted_draft(connection, "B")
        setup_id, setup_version = _confirmed_over(connection, tmp_path, stable_id, digest)

        radius = impact.blast_radius(
            connection,
            component_id=stable_id,
            component_version="1.0",
            scenario="update",
            at=AT,
        )
        report = impact.selection_report(
            connection,
            setup_id=setup_id,
            setup_version=setup_version,
            baseline_id="",
            baseline_version="",
            project_id="",
            estimator_profile="ai-stp:unicode-chars-div4/1",
            price_profile_path=None,
            at=AT,
        )

    assert radius.component.stable_id == stable_id
    assert [item.stable_id for item in radius.setup_versions] == [setup_id]
    assert report.candidate_context.conditional_tokens > 0
    # The access facts the draft does carry are read, not defaulted away.
    label = f"{stable_id}@1.0"
    assert report.candidate_capabilities.credential_requirements == [label]


def test_a_draft_without_its_kind_names_the_missing_fact(tmp_path: Path) -> None:
    """What a report genuinely cannot do without is a precondition, not a conflict."""
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id, _digest = _adopted_draft(connection, "C", component_type="")

        with pytest.raises(CliFailure) as raised:
            impact.blast_radius(
                connection,
                component_id=stable_id,
                component_version="1.0",
                scenario="update",
                at=AT,
            )

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert raised.value.details["field"] == "component_type"
    assert raised.value.next_actions == [f"component passport show --id {stable_id} --json"]


def test_impact_reads_the_target_projection_and_preserves_scope_uncertainty(tmp_path: Path) -> None:
    from tests.unit.test_cli_setup_recast import (
        DEVICE,
        _record_setup,  # pyright: ignore[reportPrivateUsage]
        _release_component,  # pyright: ignore[reportPrivateUsage]
    )

    from ai_stp_cli.local import cache
    from ai_stp_passports import ComponentVersionPassport, adaptation_for, seal_adaptation

    source_bytes = b"# Source instruction\n"
    target_bytes = "# Target instruction\nReview the Unicode boundary: café.\n".encode()
    price = tmp_path / "price.json"
    price.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "test-price-1",
                "tokenizer_profile": "ai-stp:utf8-bytes/1",
                "model": "test-model",
                "currency": "USD",
                "input_per_million": "2.50",
                "source": "https://example.test/pricing",
                "fetched_at": "2026-01-01T00:00:00.000Z",
                "expires_at": "2027-01-01T00:00:00.000Z",
            }
        ),
        encoding="utf-8",
    )
    with closing(open_registry(configured_path(), create=True)) as connection:
        target = content.put(connection, target_bytes, at=AT)

        def extra(scope: str) -> dict[str, JsonValue]:
            return {
                "harness_id": "codex",
                "content_digest": target.digest,
                "content_format": "ai-stp-component-file/1",
                "managed_paths": ["AGENTS.md"],
                "scope": scope,
                "projection_kind": "native_files",
                "declared_key": "",
                "source_locator": "",
                "native_ids": [],
            }

        member = _release_component(
            connection,
            component_type="instruction",
            harness_id="claude-code",
            payload=source_bytes,
            managed_path="CLAUDE.md",
            extra_adaptations=[extra("global")],
        )
        setup_id, _ = _record_setup(connection, harness_id="codex", member=member)

        def report(selected_id: str):
            before = tuple(connection.iterdump())
            result = impact.selection_report(
                connection,
                setup_id=selected_id,
                setup_version="1.0",
                baseline_id=setup_id,
                baseline_version="1.0",
                project_id="",
                estimator_profile="ai-stp:utf8-bytes/1",
                price_profile_path=price,
                at=AT,
            )
            assert tuple(connection.iterdump()) == before
            return result

        measured = report(setup_id)
        assert measured.candidate_context.always_tokens == len(target_bytes)
        assert measured.candidate_context.unavailable_components == 0
        assert measured.context_delta is not None
        assert measured.context_delta.always_tokens == 0
        assert measured.token_cost.status == "available"

        held = versions.held(connection, member[0], member[1])
        assert held is not None
        stored = revisions.get(connection, held.revision_id)
        assert stored is not None
        passport = ComponentVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
        adaptation = adaptation_for(passport, "codex")
        adaptation.scope_adaptations.append(
            adaptation.scope_adaptations[0].model_copy(update={"scope": "project"})
        )
        adaptation_index = passport.adaptations.index(adaptation)

        def record(version: str) -> str:
            passport.adaptations[adaptation_index] = seal_adaptation(
                adaptation.model_dump(mode="json")
            )
            document = passport.model_dump(mode="json")
            document.pop("revision_id")
            document["version"] = version
            released = revisions.commit(connection, document, device_id=DEVICE)
            ComponentVersionPassport.model_validate(released.envelope.model_dump(mode="json"))
            released_digest = cache.digest_of(released.envelope.model_dump(mode="json"))
            versions.record(
                connection,
                stable_id=member[0],
                version=version,
                passport_digest=released_digest,
                revision_id=released.revision_id,
                at=AT,
            )
            return _record_setup(
                connection, harness_id="codex", member=(member[0], version, released_digest)
            )[0]

        ambiguous_setup = record("1.1")
        uncertain = report(ambiguous_setup)
        assert uncertain.candidate_context.unavailable_components == 1
        measurement = uncertain.candidate_context.components[0]
        assert measurement.status == "unavailable"
        assert measurement.tokens is None
        assert measurement.reason == "adaptation_selection_required"
        assert uncertain.context_delta is None
        assert uncertain.capability_delta is not None
        assert uncertain.token_cost.status == "unavailable"
        assert uncertain.token_cost.amount is None
        assert uncertain.token_cost.reason == "context_budget_unavailable"

        # A valid passport with a false projection declaration must become a
        # typed conflict, including when scope selection is still ambiguous.
        scope = adaptation.scope_adaptations[-1]
        adaptation.scope_adaptations[-1] = scope.model_copy(
            update={
                "projection_artifact": scope.projection_artifact.model_copy(
                    update={"size_bytes": scope.projection_artifact.size_bytes + 1}
                )
            }
        )
        damaged_setup = record("1.2")
        before = tuple(connection.iterdump())
        with pytest.raises(CliFailure) as refused:
            report(damaged_setup)
        assert refused.value.code == "AI_STP_CONFLICT"
        assert refused.value.message == "the stored component artifact is corrupt"
        assert tuple(connection.iterdump()) == before

        document = passport.model_dump(mode="json")
        document.pop("revision_id")
        document["version"] = "1.3"
        document["adaptations"][adaptation_index]["adaptation_id"] = passport.adaptations[
            0
        ].adaptation_id
        malformed = revisions.commit(connection, document, device_id=DEVICE)
        versions.record(
            connection,
            stable_id=member[0],
            version="1.3",
            passport_digest=cache.digest_of(malformed.envelope.model_dump(mode="json")),
            revision_id=malformed.revision_id,
            at=AT,
        )
        before = tuple(connection.iterdump())
        with pytest.raises(CliFailure) as refused:
            impact.blast_radius(
                connection,
                component_id=member[0],
                component_version="1.3",
                scenario="update",
                at=AT,
            )
        assert refused.value.code == "AI_STP_CONFLICT"
        assert refused.value.message == "the recorded component passport is invalid"
        assert tuple(connection.iterdump()) == before
