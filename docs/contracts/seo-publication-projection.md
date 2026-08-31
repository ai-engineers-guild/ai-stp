---
description: "Machine boundary for server-side SEO revisions, discovery documents, and model enrichment."
last_verified: "2026-08-29"
---

# SEO publication projection

`SPEC-053` defines behavior; `ADR-0131` defines the architectural boundary. This
document owns the fields and closed vocabularies of the public SEO projection.

## Identity

An SEO subject is defined by the `subject_kind`, `subject_id`, `locale` triple.
`subject_kind` accepts `component`, `setup`, `article`, `service`, or `country`.
`subject_id` uses the object's canonical stable ID, article identity
`{type}:{slug}`, registrable service domain, or ISO 3166-1 alpha-2 country code.

Snapshot identity includes `source_digest`. Revision identity additionally
includes the generator kind and version; the active revision pointer is not part
of identity.

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

`generator.kind` accepts `template` or `model`. `model_alias` is an operator
LiteLLM alias, not an upstream credential or account name. `search_intents` and
`taxonomy_tags` support presentation and navigation; they are not used to build
HTML `meta keywords`.

## Index decision reasons

The closed v1 set is `eligible`, `not_public`, `blocked`, `hidden`, `deprecated`,
`missing_primary_content`, `missing_source`, `empty_collection`,
`duplicate_canonical`, `unavailable`, and `materialization_pending`. The reasons
list is empty only when `eligible=true`; `eligible` is used as a positive audit
reason but is not mixed with negative reasons.

The decision is computed by the template builder and is not accepted from the model response.

## Kind-specific structured data

Every document contains `BreadcrumbList`. The primary entity is selected from
`SoftwareSourceCode`, `SoftwareApplication`, `TechArticle`, `Article`, `WebSite`,
`CollectionPage`, and `ItemList` based on subject facts. `Person`/`Organization`
is added only for a published profile. `FAQPage`, ratings, reviews, offers, and
prices are allowed only after a separate contract extension with a visible
source; v1 does not generate them.

## Discovery routes

| Route | Document |
|---|---|
| `/sitemap.xml` | Sitemap or sitemap index for the current generation. |
| `/sitemaps/{kind}-{locale}-{page}.xml` | At most 50,000 eligible canonical URLs. |
| `/llms.txt` | Short stable product index and discovery surfaces. |
| `/llms-full.txt` | Bounded product reference without the full catalog. |
| `/llms/catalog.ndjson` | Paginated manifest of active subjects. |
| `/llms/{kind}/{subject_id}.md` | Canonical Markdown for the active SEO revision. |
| `/og/{revision_id}.png` | Immutable 1200×630 social image. |

The human page, Markdown, and catalog manifest reference one canonical URL.
Machine documents do not declare themselves canonical. Private, preview, and
failed revisions do not enter discovery.

## Enrichment request and response

The worker sends the LiteLLM system instruction version, public fact snapshot,
and JSON Schema. The v1 response may contain only `title`, `description`,
`summary`, `search_intents`, presentation bodies for allowed sections, and `social.title`,
`social.description`, `social.image_alt`.

The server does not silently ignore unknown fields: it rejects the entire response;
partial merge is prohibited. Canonical URL, alternates, links, identifiers, timestamps,
numbers, robots, JSON-LD facts, and the indexing decision are always rebuilt by
the server after allowed text is accepted.

Before merge, the server also requires subject-specific title and description,
several natural search intents, and the complete section set applicable to the
available facts for that subject kind. An article receives no model-generated
sections: the model improves only metadata and summary, while published text
remains authoritative content. A rejected candidate may be repaired in at most
five attempts within one job; the base revision remains active throughout.
A service without its own description and source URL remains on the `noindex`
base: association with a catalog object alone does not prove hosting, support,
or integration. The model may explain a well-known tool or technical category
but may not add unverified behavior for a specific object. A search snippet that
merely paraphrases the snapshot's machine description is rejected. For
workflow/orchestration components, facts about roles, topology, and review must
become a clear description of how coding agents work; absence of the agent
outcome from the title and search description is a quality rejection.

## Cache and freshness

The active profile ETag equals the profile document digest. The ETag for the sitemap
and LLM index includes the SEO generation. An OG asset is addressed by immutable
revision ID. Domain `lastmod` changes only with source facts, visible primary
content, or relations, not when the same content is regenerated.
