"""Relation filter union for catalog country and service search."""

import pytest

from ai_stp_contracts.catalog import CATALOG_UNSPECIFIED_FILTER
from ai_stp_platform.catalog_search import (
    merge_relation_filters,
    plan_relation_filter,
    relation_filter_signature,
)

pytestmark = pytest.mark.platform


def test_merge_relation_filters_unions_singleton_and_multi_values() -> None:
    domains, unspecified_service, countries, unspecified_country = merge_relation_filters(
        service_domain="Kaspi.KZ",
        country_code="kz",
        service_domains=["example.com", CATALOG_UNSPECIFIED_FILTER],
        country_codes=["US", "unspecified"],
    )
    assert domains == frozenset({"kaspi.kz", "example.com"})
    assert countries == frozenset({"KZ", "US"})
    assert unspecified_service is True
    assert unspecified_country is True


def test_relation_filter_signature_includes_unspecified_tokens() -> None:
    service_sig, country_sig = relation_filter_signature(
        service_domain=None,
        country_code=None,
        service_domains=["example.com", "unspecified"],
        country_codes=["unspecified"],
    )
    assert service_sig == "example.com,unspecified"
    assert country_sig == "unspecified"


def test_plan_relation_filter_ands_unspecified_service_with_a_concrete_country() -> None:
    empty = plan_relation_filter(
        service_domain=None,
        country_code=None,
        service_domains=[CATALOG_UNSPECIFIED_FILTER],
        country_codes=["KZ"],
    )
    assert empty.active is True
    assert empty.empty is True
    assert empty.include_unlinked is False
    assert empty.query_linked is False

    unlinked_and_unspecified_country = plan_relation_filter(
        service_domain=None,
        country_code=None,
        service_domains=[CATALOG_UNSPECIFIED_FILTER],
        country_codes=[CATALOG_UNSPECIFIED_FILTER],
    )
    assert unlinked_and_unspecified_country.empty is False
    assert unlinked_and_unspecified_country.include_unlinked is True
    assert unlinked_and_unspecified_country.query_linked is False

    same_row = plan_relation_filter(
        service_domain="kaspi.kz",
        country_code="KZ",
        service_domains=[],
        country_codes=[],
    )
    assert same_row.query_linked is True
    assert same_row.domains == frozenset({"kaspi.kz"})
    assert same_row.countries == frozenset({"KZ"})
    assert same_row.include_unlinked is False


def test_plan_country_unspecified_is_a_country_less_service_not_an_unlinked_object() -> None:
    plan = plan_relation_filter(
        service_domain=None,
        country_code=None,
        service_domains=[],
        country_codes=[CATALOG_UNSPECIFIED_FILTER],
    )
    assert plan.active is True
    assert plan.empty is False
    assert plan.include_unlinked is False
    assert plan.query_linked is True
    assert plan.include_country_less is True

    service_unspecified = plan_relation_filter(
        service_domain=None,
        country_code=None,
        service_domains=[CATALOG_UNSPECIFIED_FILTER],
        country_codes=[],
    )
    assert service_unspecified.include_unlinked is True
    assert service_unspecified.query_linked is False
