"""Apply one reviewed catalog request from the server; no HTTP surface."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.reports import CountryRequest, ServiceRequest
from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.external_catalog import COUNTRY_CODES, canonical_external_url
from ai_stp_platform.models import (
    CountryLocale,
    ExternalProduct,
    ExternalProductCountry,
    ExternalProductLocale,
    ReportCase,
)
from ai_stp_platform.seo.enqueue import (
    enqueue_seo_build,
    enqueue_service_and_countries,
    mutation_digest,
)
from ai_stp_platform.settings import DatabaseSettings


async def apply_case(session: AsyncSession, case_id: str) -> tuple[str, str]:
    """Apply one request and enqueue localized SEO in the same transaction."""
    case = await session.scalar(
        select(ReportCase).where(ReportCase.id == case_id).with_for_update()
    )
    if case is None or case.topic not in {"service_request", "country_request"}:
        raise ValueError("catalog request case not found")
    if case.state == "resolved":
        return case.id, case.topic
    if case.state == "security_escalated":
        raise ValueError("security-escalated case cannot be applied")

    if case.topic == "service_request":
        request = ServiceRequest.model_validate(case.payload)
        canonical = canonical_external_url(request.primary_url)
        if canonical is None:
            raise ValueError("request contains an invalid service URL")
        primary_url, domain = canonical
        invalid = sorted(set(request.country_codes) - COUNTRY_CODES)
        if invalid:
            raise ValueError(f"unknown country codes: {','.join(invalid)}")
        product = await session.scalar(
            select(ExternalProduct).where(ExternalProduct.canonical_domain == domain)
        )
        if product is None:
            product = ExternalProduct(
                canonical_domain=domain,
                primary_url=primary_url,
                name=request.name,
                description=request.description_en,
                source_url=request.source_url,
            )
            session.add(product)
            await session.flush()
        else:
            product.primary_url = primary_url
            product.name = request.name
            product.description = request.description_en
            product.source_url = request.source_url
        for locale, description in (
            ("ru", request.description_ru),
            ("en", request.description_en),
        ):
            await session.execute(
                insert(ExternalProductLocale)
                .values(
                    external_product_id=product.id,
                    locale=locale,
                    name=request.name,
                    description=description,
                    source_url=request.source_url,
                )
                .on_conflict_do_update(
                    constraint="uq_external_product_locale_identity",
                    set_={
                        "name": request.name,
                        "description": description,
                        "source_url": request.source_url,
                    },
                )
            )
        await session.execute(
            delete(ExternalProductCountry).where(
                ExternalProductCountry.external_product_id == product.id
            )
        )
        for code in sorted(set(request.country_codes)):
            session.add(ExternalProductCountry(external_product_id=product.id, country_code=code))
        await enqueue_service_and_countries(
            session,
            domain=domain,
            country_codes=request.country_codes,
            extra=f"{request.description_ru}:{request.description_en}:{request.source_url}",
        )
    else:
        request = CountryRequest.model_validate(case.payload)
        if request.code not in COUNTRY_CODES:
            raise ValueError("unknown ISO country code")
        for locale, name in (("ru", request.name_ru), ("en", request.name_en)):
            await session.execute(
                insert(CountryLocale)
                .values(country_code=request.code, locale=locale, name=name)
                .on_conflict_do_update(
                    constraint="uq_country_locale_identity",
                    set_={"name": name},
                )
            )
        await enqueue_seo_build(
            session,
            kind="country",
            subject_id=request.code,
            source_digest=mutation_digest(
                "country", request.code, request.name_ru, request.name_en
            ),
        )

    case.state = "resolved"
    case.payload = {
        **case.payload,
        "applied_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    return case.id, case.topic


async def _run(case_id: str) -> dict[str, str]:
    engine = make_engine(DatabaseSettings())  # pyright: ignore[reportCallIssue]
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session, session.begin():
            applied_id, topic = await apply_case(session, case_id)
    finally:
        await engine.dispose()
    return {"case_id": applied_id, "topic": topic, "state": "resolved"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply one reviewed catalog request case.")
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.case_id)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
