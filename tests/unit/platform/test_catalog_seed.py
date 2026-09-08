"""First-party seed unit tests (SPEC-021 REQ-2110)."""

from __future__ import annotations

import pytest
from tests.support.catalog_seed import (
    INCIDENT_SUBAGENT_ARTIFACT,
    INCIDENT_SUBAGENT_NAME,
    SEED_A1_INCIDENT_AGENT_ID,
    SEED_A1_INCIDENT_SETUP_ID,
    seed_corpus,
)

from ai_stp_contracts.context_estimator import EstimatorInput, estimate_context, estimator_for
from ai_stp_contracts.impact import ExactCoordinate

pytestmark = pytest.mark.platform


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
