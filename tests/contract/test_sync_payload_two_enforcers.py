"""One payload policy, two enforcers, one verdict.

The client refuses before it opens a socket, because a secret that left the
machine has already left it. The server refuses again, because a client is not
an authority about its own payload. Both refusals are the same rule, and the
last time it was written twice the copies diverged: only the client grew the
`required_env` carve-out, so a complete canonical passport passed the half that
was optional and was refused by the half that decides.

This runs the same corpus through both halves and requires them to agree. The
server's enforcement point is reached directly rather than through
`validate_event_document`, because everything else that function checks —
identity, parents, digests — is not the policy under test and would need
fixtures that say nothing about it.
"""

import pytest

from ai_stp_api.slices.sync.validation import SyncValidationError
from ai_stp_api.slices.sync.validation import (
    _scan_forbidden as server_refuses,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_contracts.first_party import versions
from ai_stp_contracts.sync_payload import SyncPayloadRejection, check_sync_payload


def _document(**fields: object) -> dict[str, object]:
    return {"schema_version": 1, "kind": "component", **fields}


#: Cases chosen where the two halves previously disagreed, plus the classes both
#: always refused. A corpus of only-refused cases would agree trivially.
CASES: tuple[tuple[str, dict[str, object], bool], ...] = (
    (
        "a declared environment variable",
        _document(required_env=[{"name": "T", "purpose": "p"}]),
        True,
    ),
    (
        "an environment value",
        _document(required_env=[{"name": "T", "purpose": "p", "value": "x"}]),
        False,
    ),
    ("a declared authorization class", _document(requires_authorization="none"), True),
    ("an invented authorization class", _document(requires_authorization="whatever"), False),
    ("a plain field", _document(summary="a component"), True),
    ("a secret by name", _document(github_token="x"), False),
    ("a nested secret", _document(nested=[{"api_key_value": "x"}]), False),
    ("an absolute path", _document(where="/home/someone/project"), False),
    ("binary bytes", _document(blob=b"bytes"), False),
    ("a session field", _document(session_ttl=60), False),
)


def _client_accepts(payload: dict[str, object]) -> bool:
    try:
        check_sync_payload(payload)
    except SyncPayloadRejection:
        return False
    return True


def _server_accepts(payload: dict[str, object]) -> bool:
    try:
        server_refuses(payload)
    except SyncValidationError:
        return False
    return True


@pytest.mark.parametrize(("name", "payload", "carried"), CASES, ids=[case[0] for case in CASES])
def test_both_halves_reach_the_same_verdict(
    name: str, payload: dict[str, object], carried: bool
) -> None:
    del name
    assert _client_accepts(payload) is carried
    assert _server_accepts(payload) is carried


def test_the_whole_first_party_corpus_crosses_both_halves() -> None:
    """The oracle is the launch corpus, not a sample.

    This is the case that was actually broken: `requires_authorization` is a
    closed three-value enum, the fragment `authorization` matched it, and the
    server refused every object the product ships — 120 of 120, not an edge.
    """
    corpus = versions()
    assert corpus, "an empty corpus would prove nothing"
    for item in corpus:
        payload = item.passport.model_dump(mode="json")
        assert _client_accepts(payload), item.passport.stable_id
        assert _server_accepts(payload), item.passport.stable_id
