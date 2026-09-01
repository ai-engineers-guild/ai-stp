"""The per-address budget is charged to the caller, not to the proxy in front of it."""

from __future__ import annotations

from starlette.requests import Request

from ai_stp_api.rate_limit import CLIENT_ADDRESS_HEADER, UNKNOWN_PEER, client_key


def _request(*, peer: str | None, stated: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if stated is not None:
        headers.append((CLIENT_ADDRESS_HEADER.encode(), stated.encode()))
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "path": "/v1/health/live",
        "headers": headers,
        "client": None if peer is None else (peer, 51234),
    }
    return Request(scope)


def test_the_edge_stated_address_is_the_key() -> None:
    """Behind the proxy the peer is the proxy, and it is the same for everyone."""
    assert client_key(_request(peer="172.18.0.4", stated="203.0.113.9")) == "203.0.113.9"


def test_two_callers_behind_one_proxy_get_two_keys() -> None:
    """The defect this closes: one shared bucket for every anonymous reader."""
    first = client_key(_request(peer="172.18.0.4", stated="203.0.113.9"))
    second = client_key(_request(peer="172.18.0.4", stated="198.51.100.7"))
    assert first != second


def test_an_absent_header_falls_back_to_the_transport_peer() -> None:
    """Local development has no proxy, and there the peer is the caller."""
    assert client_key(_request(peer="127.0.0.1")) == "127.0.0.1"


def test_a_value_that_is_not_an_address_falls_back() -> None:
    """A key of the sender's own choosing would be a way around the budget."""
    for invented in ("not-an-address", "203.0.113.9; DROP", "", "   "):
        assert client_key(_request(peer="172.18.0.4", stated=invented)) == "172.18.0.4"


def test_an_address_is_normalised_before_it_becomes_a_key() -> None:
    """Two spellings of one address must not buy two budgets."""
    compact = client_key(_request(peer="172.18.0.4", stated="2001:db8::1"))
    expanded = client_key(_request(peer="172.18.0.4", stated="2001:0db8:0000::0001"))
    assert compact == expanded


def test_no_peer_and_no_header_is_still_a_key() -> None:
    assert client_key(_request(peer=None)) == UNKNOWN_PEER
