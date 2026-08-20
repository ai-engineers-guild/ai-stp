from ai_stp_platform.external_catalog import COUNTRY_CODES, canonical_external_url


def test_external_url_deduplicates_by_registrable_domain() -> None:
    assert canonical_external_url("https://api.example.co.in/docs") == (
        "https://api.example.co.in/docs",
        "example.co.in",
    )


def test_external_url_rejects_deep_or_unsafe_urls() -> None:
    assert canonical_external_url("http://example.com") is None
    assert canonical_external_url("https://example.com/a/b") is None
    assert canonical_external_url("https://user@example.com") is None
    assert canonical_external_url("https://127.0.0.1/shop") is None
    assert canonical_external_url("https://[::1]/shop") is None


def test_external_url_strips_query_fragment_and_trailing_slash() -> None:
    assert canonical_external_url("https://KASPI.KZ/shop/?utm_source=x#offer") == (
        "https://kaspi.kz/shop",
        "kaspi.kz",
    )


def test_country_codes_are_pinned_iso_alpha_two_values() -> None:
    assert {"KZ", "IN", "PK", "CN", "RU", "BR"} <= COUNTRY_CODES
    assert all(len(code) == 2 and code.isupper() for code in COUNTRY_CODES)
