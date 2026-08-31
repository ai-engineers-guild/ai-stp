---
description: "Procedure for implementing the server-side SEO loop without mixing domain publication and model enrichment."
last_verified: "2026-08-29"
---

# Implementation Plan for the Server-Side SEO Loop

Regulatory owners: `SPEC-053`, `ADR-0131`, and `docs/contracts/seo-publication-projection.md`. The stage is considered completed only after `just docs-check`, `just back-static`, `just back-test`, `just web-check`, and review of the diff in the public checkout.

## 1. Expand: persistence and contracts

1. Add additive tables `seo_fact_snapshot`, `seo_revision`, and `seo_active_revision`, unique constraints for snapshot/revision identity and generation counter without deleting existing fields.
2. Add Pydantic/OpenAPI contracts profile v1, state/error enums and public read models; regenerate contract artifacts.
3. Add `seo_build` and `seo_enrich` to the private job registry and handler stubs,
which are not yet set in the production flow.
4. Connect active `ArticleRevision` via `SPEC-054` as the subject of the article; import, publication staff, and ownership of the source remain with the content publication.
5. Expand the curated service presentation with required fields for indexing: description and public source URL, while keeping existing readable records and `noindex` until data enrichment.

Rollback stage: old code ignores added tables and optional service fields.

## 2. Deterministic base

1. Implement allowlist fact collectors for five types of subject and canonical digest aggregate.
2. Implement one profile builder with kind-specific templates, index decision, links, social facts, and JSON-LD.
3. Set `seo_build` from component/setup publication, change active `ArticleRevision` via `SPEC-054`, and service mutation in a single transaction with
by changing the source; country rebuild to be derived from changed relations.
4. Activate base revision and generation atomically; repeat job and concurrent delivery should have a single effect.
5. Backfill existing public subjects with limited keyset batches; thin service/country subjects receive `noindex`, not an AI filler.

Exit: each fixture has an active base profile without network access.

## 3. Serving and discovery

1. Switch `generateMetadata` component/setup/service/country/article to a single public SEO reading model with the current presenter as a migration fallback.
2. Render visible rich sections and JSON-LD from a single profile revision; maintain current human/machine route semantics `ADR-0076`.
3. Replace static sitemap projection with generation-aware index/shards.
4. Add root/detail LLM routes and a pageable NDJSON manifest.
5. Add revision-addressed OG route and object-store/cache materialization.
6. Check HTTP 200/404, robots, canonical, hreflang, ETag, public cache, and absence of cookie/session on each discovery route.

Exit: the crawler can go from sitemap/hub via regular links to each eligible fixture, and metadata, HTML, JSON-LD, OG, and Markdown are consistent.

## 4. Optional enhancement via LiteLLM

1. Add a separate compose profile `seo_enrichment` with LiteLLM and optional CLIPROXY upstream; API and main worker start without it.
2. Add worker settings only for LiteLLM URL, process credentials, model alias, timeout, and enable flag; upstream credentials belong to the proxy deployment.
3. Implement versioned prompt, strict structured response, and fact checking.
4. Add stale guard before and after the call, bounded retry, and atomic activation
accepted candidate; refusal leaves the base active.
5. Compile a fixed RU/EN evaluation corpus for all types of subjects: accurate facts, prohibited statements, prompt injection, duplicates, incorrect JSON, timeout, and stale response. The choice of the local model is made according to this corpus; the model name is not fixed by a product contract.

Exit: shutting down/failure of both proxies does not change publication and serving; accepted output does not contain facts outside the snapshot.

## 5. Rollout and evidence

1. Deploy the schema and dual-read, perform base backfill, compare current and new HTML/metadata on a production-like corpus.
2. Switch reads to active SEO revisions; keep fallback on the rollback window.
3. Enable enrichment first for a small deterministic cohort and one locale, then expand only with acceptable rejection/cost/latency.
4. Register the sitemap in Google Search Console and Yandex Webmaster; remove crawl/index evidence without presenting submission as index success.
5. Observe the path publication→approval→sitemap→crawl→index→click→catalog action by aggregates of type subject and locale; the original query and subject ID are not needed for platform metrics.
6. After the compatibility window, remove fallback in a separate PR and migration contract phase; do not delete new tables in the rollback of the current rollout.

## Minimum Test Matrix

| Slice | Required Evidence |
|---|---|
| Platform | Exact snapshot, idempotent jobs, stale guard, atomic pointer, backfill resumption. |
| API contracts | Closed enums, public/private boundary, conditional fields, stable errors. |
| Web | Metadata, JSON-LD, HTML links, sitemap shards, LLM Markdown, OG dimensions/cache. |
| Security | Secret/private-field exclusion, prompt injection corpus, URL allowlist, safe Markdown. |
| Degradation | No model, timeout, malformed output, dead-letter, API outage and last-active serving. |
| Migration | Old web/new schema, new web/no active revision, rollback and resumed backfill. |

## Explicitly deferred

- keyword-volume providers and Search Console query ingestion — until there is a measured solution regarding data, access, and retention;
- automatic FAQ rich results — until a separate visible FAQ contract;
- social publication — SEO profile only prepares a preview;
- separate SEO microservice, broker, and vector database — until measurable load that platform/worker/PostgreSQL cannot handle;
- mass country×service×component landing pages — until proven unique intent and data for each page.
