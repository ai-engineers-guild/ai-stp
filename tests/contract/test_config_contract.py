"""Retained Python oracle defaults; native document parity runs in verify.py."""

from urllib.parse import urlsplit

from ai_stp_cli.config import declared_fields


def test_the_shipped_catalogue_address_is_one_that_can_answer() -> None:
    field = next(item for item in declared_fields() if item.path == "catalog.url")
    assert isinstance(field.default, str)
    parsed = urlsplit(field.default)
    assert parsed.scheme == "https" and parsed.hostname is not None
    assert not parsed.hostname.endswith((".example", ".invalid", ".test", ".localhost"))
