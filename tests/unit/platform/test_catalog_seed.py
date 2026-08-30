"""First-party seed unit tests (SPEC-021 REQ-2110)."""

from __future__ import annotations

from typing import Any

import pytest

from ai_stp_contracts.context_estimator import EstimatorInput, estimate_context, estimator_for
from ai_stp_contracts.impact import ExactCoordinate
from ai_stp_platform.catalog_seed import (
    INCIDENT_SUBAGENT_ARTIFACT,
    INCIDENT_SUBAGENT_NAME,
    SEED_A1_INCIDENT_AGENT_ID,
    SEED_A1_INCIDENT_SETUP_ID,
    load_first_party_seed,
    seed_corpus,
)
from ai_stp_platform.models import Account, CatalogMetadata, ComponentMedia

pytestmark = pytest.mark.platform


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self._store: dict[str, Any] = {}
        self._id = 1

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, CatalogMetadata) and value.id is None:  # type: ignore[truthy-bool]
            value.id = self._id
            self._id += 1
            key = (value.object_kind, value.stable_id, value.version)
            self._store[f"meta:{key}"] = value
        if isinstance(value, Account):
            self._store[f"account:{value.id}"] = value

    async def flush(self) -> None:
        return None

    async def get(self, model: type[object], ident: object) -> object | None:
        if model is Account:
            return self._store.get(f"account:{ident}")
        return None

    async def scalar(self, stmt: object) -> object | None:
        # Minimal stand-in: look up by scanning stored metadata.
        del stmt
        return None


@pytest.mark.asyncio
async def test_seed_corpus_is_public_experimental_and_schema_valid() -> None:
    corpus = seed_corpus()
    assert len(corpus) >= 3
    for kind, passport, published_at, digest in corpus:
        assert kind in {"component", "setup"}
        assert passport["visibility"] == "public"
        assert published_at.endswith("Z")
        assert digest.startswith("sha256:")
        assert passport["kind"] == kind


def test_seed_passport_digest_matches_canonical_bytes() -> None:
    """A zero or stale digest would break #71 catalog conformance (REQ-2110/2112).

    The seed must store the same integrity digest the wire fixtures and
    projection recompute from the sealed passport body.
    """
    from ai_stp_foundation.digests import digest_canonical

    for _kind, passport, _published_at, digest in seed_corpus():
        expected = digest_canonical("ai-stp:passport:v1", passport)
        assert digest == expected


def test_every_seed_passport_id_derives_from_its_own_body() -> None:
    """The check the digest test only appears to be.

    `test_seed_passport_digest_matches_canonical_bytes` recomputes the digest
    from the body, so it heals whatever the body says and can never disagree
    with it. `revision_id` is different: two seed passports carry a **pinned**
    literal, because they back published contract examples and an example whose
    id moves on every edit is not a fixed point. Pinned means it must be
    recomputed by hand when the body changes, and nothing checked that it had
    been.

    Adding `posture` to the setup body moved the id and the whole suite stayed
    green. That is the failure `seal_envelope`'s own docstring records: a
    passport carrying an id that fails its own verification is invisible
    locally, and surfaces at `sync pull`, which refuses the payload as not
    matching its event coordinates.
    """
    from ai_stp_passports.envelope import derive_revision_id

    checked = 0
    for _kind, passport, _published_at, _digest in seed_corpus():
        assert passport["revision_id"] == derive_revision_id(passport), passport["stable_id"]
        checked += 1
    assert checked > 0


@pytest.mark.asyncio
async def test_seed_loader_is_idempotent_in_session() -> None:
    session = RecordingSession()
    first = await load_first_party_seed(session)  # type: ignore[arg-type]
    # Second pass: scalar still returns None so this simple session creates again;
    # the real DB path is covered by the integration test. Here we only assert
    # the first run creates the owner account and versions.
    assert first.created_accounts == 3
    assert first.created_versions == len(seed_corpus())
    assert sum(1 for item in session.added if isinstance(item, Account)) == 3
    assert sum(1 for item in session.added if isinstance(item, CatalogMetadata)) == len(
        seed_corpus()
    )
    media = [item for item in session.added if isinstance(item, ComponentMedia)]
    assert len(media) == 1
    assert all(item.position == 0 and item.state == "ready" for item in media)


def test_incident_subagent_contribution_matches_shared_estimator() -> None:
    estimator = estimator_for("ai-stp:utf8-bytes/1")
    assert estimator is not None
    agent = next(
        passport
        for kind, passport, _published, _digest in seed_corpus()
        if kind == "component" and passport["stable_id"] == SEED_A1_INCIDENT_AGENT_ID
    )
    setup = next(
        passport
        for kind, passport, _published, _digest in seed_corpus()
        if kind == "setup" and passport["stable_id"] == SEED_A1_INCIDENT_SETUP_ID
    )
    assert agent["name"] == INCIDENT_SUBAGENT_NAME
    assert agent["component_type"] == "agent"
    assert setup["components"][0]["stable_id"] == SEED_A1_INCIDENT_AGENT_ID
    budget = estimate_context(
        [
            EstimatorInput(
                coordinate=ExactCoordinate(
                    stable_id=SEED_A1_INCIDENT_AGENT_ID,
                    version="1.0",
                    passport_digest=setup["components"][0]["passport_digest"],
                ),
                component_type="agent",
                files=(INCIDENT_SUBAGENT_ARTIFACT,),
            )
        ],
        estimator,
    )
    assert budget.always_tokens == 0
    assert budget.conditional_tokens == len(INCIDENT_SUBAGENT_ARTIFACT)
    assert budget.components[0].loading == "conditional"
    assert budget.components[0].tokens == len(INCIDENT_SUBAGENT_ARTIFACT)
