---
description: "Машинная граница серверной SEO-ревизии, discovery документов и model-enrichment."
last_verified: "2026-08-29"
---

# SEO publication projection

`SPEC-053` определяет поведение, `ADR-0131` — архитектурную границу. Этот документ
владеет полями и закрытыми словарями публичной SEO-проекции.

## Identity

SEO subject задаётся тройкой `subject_kind`, `subject_id`, `locale`.
`subject_kind` принимает `component`, `setup`, `article`, `service`, `country`.
`subject_id` использует canonical stable ID объекта, article identity
`{type}:{slug}`, registrable service domain либо ISO 3166-1 alpha-2 country code.

Snapshot identity включает `source_digest`. Revision identity дополнительно
включает вид и версию генератора; указатель active revision не входит в identity.

## Profile document v1

```text
schema_version        = 1
subject               = {kind, id, source_revision, source_digest}
locale                = ru | en
canonical_url         = absolute HTTPS URL
title                 = 1..160 characters
description           = 1..320 characters
heading               = 1..200 characters
summary               = safe Markdown
taxonomy_tags         = unique array, at most 12
search_intents        = unique presentation hints, at most 12
alternates            = map<locale, absolute HTTPS URL>
robots                = index,follow | noindex,follow
index_decision        = {eligible, reasons[]}
breadcrumbs           = ordered visible links
sections              = ordered kind-specific visible sections
internal_links        = unique canonical subject links
json_ld               = one schema.org @graph derived from visible facts
social                = {title, description, image_url, image_alt, locale}
published_at          = RFC 3339
modified_at           = RFC 3339
generator             = {kind, template_version, prompt_version?, model_alias?}
```

`generator.kind` принимает `template` или `model`. `model_alias` — операторский
alias LiteLLM, не имя upstream credential/account. `search_intents` и
`taxonomy_tags` помогают представлению и навигации; HTML `meta keywords` из них не
строится.

## Index decision reasons

Закрытый v1-набор: `eligible`, `not_public`, `blocked`, `hidden`, `deprecated`,
`missing_primary_content`, `missing_source`, `empty_collection`,
`duplicate_canonical`, `unavailable` и `materialization_pending`. Только пустой
список при `eligible=true`; значение `eligible` используется как positive audit
reason, но не смешивается с отрицательными reasons.

Решение вычисляется template builder и не принимается из model response.

## Kind-specific structured data

Каждый документ содержит `BreadcrumbList`. Primary entity выбирается из
`SoftwareSourceCode`, `SoftwareApplication`, `TechArticle`, `Article`, `WebSite`,
`CollectionPage` и `ItemList` по фактам subject. `Person`/`Organization`
добавляется только для опубликованного профиля. `FAQPage`, рейтинг, отзыв, offer
и price допустимы только после отдельного расширения контракта с visible source;
v1 их не генерирует.

## Маршруты обнаружения

| Маршрут | Документ |
|---|---|
| `/sitemap.xml` | Sitemap либо sitemap index текущей generation. |
| `/sitemaps/{kind}-{locale}-{page}.xml` | Не более 50 000 eligible canonical URLs. |
| `/llms.txt` | Короткий стабильный индекс продукта и discovery surfaces. |
| `/llms-full.txt` | Ограниченная справка продукта без полного каталога. |
| `/llms/catalog.ndjson` | Пагинируемый manifest active subjects. |
| `/llms/{kind}/{subject_id}.md` | Канонический Markdown активной SEO-ревизии. |
| `/og/{revision_id}.png` | Immutable 1200×630 social image. |

Human page, Markdown и catalog manifest ссылаются на один canonical URL. Machine
documents не заявляют canonical на себя. Private, preview и failed revisions не
попадают в discovery.

## Запрос и ответ enrichment

Worker отправляет LiteLLM system instruction version, public fact snapshot и
JSON Schema. Response v1 может содержать только `title`, `description`, `summary`,
`search_intents`, presentation body разрешённых sections и `social.title`,
`social.description`, `social.image_alt`.

Server игнорирует unknown fields и отклоняет весь response; частичное merge
запрещено. Canonical, alternates, links, identifiers, timestamps, numbers,
robots, факты JSON-LD и решение об индексации всегда пересобираются сервером после
приёма разрешённого текста.

До merge server также требует предметные title и description, несколько
естественных поисковых намерений и полный набор секций, применимый к доступным
фактам данного subject kind. Статья не получает model-generated sections:
модель улучшает только metadata и summary, а опубликованный текст остаётся
авторитетным содержимым. Rejected candidate можно исправить не более чем за пять
попыток одного job; base revision всё это время остаётся активной.
Service без собственного описания и source URL остаётся на `noindex` base:
связь с объектом каталога сама по себе не доказывает hosting, support или integration.
Модель может расшифровать общеизвестный инструмент или техническую категорию,
но не может добавлять неподтверждённое поведение конкретного объекта. Search snippet,
который лишь перефразирует машинное описание snapshot, отклоняется.
Для workflow/orchestration-компонентов факты о roles, topology и review должны
превратиться в понятное описание работы coding agents; отсутствие agent outcome
в title и search description является quality rejection.

## Cache and freshness

ETag активного profile равен digest profile document. Sitemap и LLM index ETag
включает SEO generation. OG asset адресуется immutable revision ID. Доменный
`lastmod` меняется только от source facts, видимого primary content или relations,
но не от повторной генерации тем же содержимым.
