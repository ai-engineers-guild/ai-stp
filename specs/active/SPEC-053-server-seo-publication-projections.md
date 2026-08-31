---
description: "SPEC-053: Server-side SEO revisions for components, setups, articles, services, and countries."
last_verified: "2026-08-29"
---

# SPEC-053: Server-side SEO pipeline for public entities

## Purpose

Every publication or substantive update of a public component, setup, article,
or service automatically creates a consistent rich page projection:
HTML metadata, JSON-LD, social preview, sitemap membership, internal links, and
an LLM-readable document. The deterministic version becomes available
independently of the model; optional AI enrichment improves only presentation
text.

## Scope

The scope includes server-side snapshots and SEO revisions, five subject kinds,
two job types, indexing decisions, locale variants, a sitemap index/shards,
Open Graph images, `llms.txt`/detail Markdown, repository article import,
service presentation metadata, a LiteLLM adapter, factual validation,
observability, migration, and rollback. The exact public format is owned by
`docs/contracts/seo-publication-projection.md`, and the architectural decision
is owned by `ADR-0131`.

The scope excludes a CMS, an article editor in web, keyword scraping, link
buying, automatic publication to social networks, search ranking guarantees,
model-generated domain facts, changes to the passport digest, and a separate
message broker.

## Terms

- **SEO subject** — a public entity of kind `component`, `setup`, `article`,
  `service`, or `country`.
- **SeoFactSnapshot** — an immutable set of public facts for an exact subject
  revision and locale, with a canonical digest.
- **SeoRevision** — an immutable presentation representation of a snapshot,
  with its own generator provenance and state.
- **Base revision** — a fully functional deterministic SEO revision without a
  model.
- **Enriched revision** — a candidate produced through LiteLLM that has passed
  mechanical and factual validation.
- **Index eligibility** — a server-side mechanical decision to include a
  canonical URL in the sitemap and return `index,follow`.

## Requirements

### Events and storage

- `REQ-5301`: Successful publication of a component/setup transactionally
  enqueues `seo_build` for the exact stable ID, version, locale, and source
  digest; repeated delivery with the same coordinates does not create a second
  snapshot or a duplicate active effect.
- `REQ-5302`: Activation or unpublication of an `ArticleRevision` under
  `SPEC-054` idempotently enqueues `seo_build` for the exact article
  revision/source digest; repository import and staff publication do not depend
  on completion of the SEO job.
- `REQ-5303`: Creation or modification of a public service, its countries, or
  its relationships with published objects computes a digest of the entire
  public aggregate and enqueues `seo_build` for the service and affected
  country pages.
- `REQ-5304`: `SeoFactSnapshot` stores subject kind/id/revision, locale,
  `source_digest`, schema version, public facts, and snapshot time;
  secret-bearing, private, and artifact-body fields are rejected before
  persistence.
- `REQ-5305`: `SeoRevision` stores the snapshot ID, state, profile document,
  template/prompt versions, generator kind, model alias when present,
  timestamps, and a safe error code; exactly one `SeoActiveRevision` exists per
  subject/locale.
- `REQ-5306`: Activation of a new revision and incrementing the SEO generation
  occur atomically; an incomplete or stale revision is never read as active.

### Base projection

- `REQ-5307`: As its first step, `seo_build` creates a base revision without
  network or model access, containing title, description, H1, canonical,
  locale alternates, robots, taxonomy tags, breadcrumbs, social metadata,
  JSON-LD, a section plan, internal links, image facts, and the indexing
  decision.
- `REQ-5308`: Unavailability of LiteLLM, CLIPROXY, or any model does not delay
  domain publication, activation of the base revision, sitemap generation, or
  rendering of the rich page.
- `REQ-5309`: The canonical belongs to the stable subject page; version pages
  and query variants do not become independent canonical URLs without a
  separate content contract.
- `REQ-5310`: A locale alternate is declared only for an existing active locale
  revision; a missing translation does not receive a fabricated hreflang URL.
- `REQ-5311`: JSON-LD and visible HTML are built from the same profile;
  structured data does not contain a hidden FAQ, rating, review, price,
  compatibility claim, or verification absent from the visible page and
  snapshot.
- `REQ-5312`: A component/setup profile shows purpose, compatibility,
  requirements, permissions, credentials, verification evidence, source,
  author, versions, and actual relations; an article profile shows
  author/dateModified/body/related subjects; a service/country profile shows
  only actually related public objects.

### Indexing, discovery, and social

- `REQ-5313`: `index_eligible` is computed without a model from lifecycle,
  visibility, HTTP availability, minimum completeness of kind-specific facts,
  canonical uniqueness, and the presence of unique content; a negative
  decision stores stable reasons.
- `REQ-5314`: A non-eligible page returns `noindex,follow` and is absent from all
  sitemap shards; an eligible canonical returns `index,follow` and appears
  exactly once.
- `REQ-5315`: `/sitemap.xml` is a sitemap index or the sitemap for the current
  small set and lists cacheable shards by subject kind/locale, absolute
  canonicals, actual `lastmod`, and existing alternates; no shard exceeds
  50,000 URLs.
- `REQ-5316`: Revision activation invalidates the generation-aware sitemap/LLM
  cache; no individual job appends to a shared XML or text file, and concurrent
  activations do not lose URLs.
- `REQ-5317`: The social profile contains Open Graph and Twitter title,
  description, canonical URL, locale, site name, image URL, and alt text; the
  image route is addressed by an immutable revision ID, returns a 1200×630
  asset, and permits long-lived public caching.
- `REQ-5318`: The root `/llms.txt` remains a compact index;
  `/llms-full.txt` describes the product and stable sections, while every
  active subject is available as a separate canonical Markdown document and
  through a paginated catalog manifest, without requiring the entire growing
  catalog to be placed in one file.
- `REQ-5319`: Public HTML contains crawlable `<a href>` links derived from
  stored relations; a search form and client event are not the only route to
  an indexable subject entity.

### Model enrichment

- `REQ-5320`: After base activation, configuration may enqueue `seo_enrich`;
  when disabled, the flow completes in the `base_active` state without error.
- `REQ-5321`: The worker calls only the configured OpenAI-compatible LiteLLM URL
  by model alias; routing to CLIPROXY and a fallback provider is not encoded in
  the job handler.
- `REQ-5322`: The model request contains a versioned instruction, a closed
  output schema, and the public `SeoFactSnapshot`; credentials, private
  profiles, raw artifacts, and validation finding bodies are not transmitted.
- `REQ-5323`: Model output may change only permitted presentation fields and
  cannot set canonical, robots, the indexing decision, lifecycle, trust,
  verification, source links, or numeric facts. The model may explain known
  public tools and technical categories from general knowledge, but
  object-specific claims must follow from the snapshot.
- `REQ-5324`: The candidate passes JSON Schema, limits, locale, URL allowlist,
  secret detection, unsupported-claim validation, duplicate similarity,
  title/description specificity, usefulness of search intents, mandatory
  coverage of available facts by sections for its subject kind, and exact
  source digest validation; failure stores a safe code and leaves the base
  active. The worker makes no more than five attempts to correct a rejected
  candidate using a safe rejection reason. A service without its own
  description and source URL does not receive model enrichment. A search
  description similar to the machine source description is considered
  rejected: enrichment must translate passport terms into the user's task.
  For a workflow/orchestration subject with facts about roles, topology, or
  review, the candidate must explicitly describe the agent outcome in the
  title or search description, rather than leaving internal terms unexplained
  or hiding the meaning only in the body.
- `REQ-5325`: A response for an old source digest receives `stale` and is not
  activated; a retry with the same snapshot/template/prompt/model uses one
  idempotency key.
- `REQ-5326`: An operator can disable enrichment and atomically return any
  subject to the latest valid base revision without changing the domain
  object.

### Cache, security, and operations

- `REQ-5327`: A public SEO read does not read session/cookies and follows the
  public cache boundary; preview/admin status is private and `no-store`.
- `REQ-5328`: HTML, JSON-LD, Markdown, and model text pass through the current
  safe Markdown/escaping profile; model output does not insert raw HTML or
  script.
- `REQ-5329`: The model credential exists only in the deployment secret for the
  worker; the job payload, DB, API response, structured log, metrics, and
  repository example do not contain it.
- `REQ-5330`: Metrics distinguish build/enrich latency and outcome, active
  base/enriched revisions, stale/rejected candidates, index eligibility
  reasons, sitemap generation, model requests/tokens/cost alias, and cache age,
  without the prompt, content body, or identifiers.
- `REQ-5331`: The public route preserves the latest active revision during a
  temporary API, worker, or model error; when no active revision exists, it
  uses the current server-side deterministic presenter with `noindex` until
  materialization, rather than a soft 404.
- `REQ-5332`: A rebuild for a new template/prompt version creates a new revision
  of the same snapshot in a bounded batch and does not change domain
  `updated_at` or sitemap `lastmod` while visible primary content remains
  unchanged.

## States and errors

An SEO revision passes through `building`, `base_ready`, `enriching`,
`validating`, `active`, `rejected`, `failed`, or `stale`. The active pointer
references only a `base_ready` revision or an enriched candidate that has
passed validation, which becomes `active` in the same transaction; the
previous active revision remains available for rollback.

Stable error codes: `AI_STP_SEO_FACTS_INVALID`, `AI_STP_SEO_OUTPUT_INVALID`,
`AI_STP_SEO_ENRICHMENT_UNAVAILABLE`, `AI_STP_SEO_SOURCE_STALE`, and
`AI_STP_SEO_RENDER_FAILED`. Model unavailability is a degradation of
enrichment, not an error in domain publication or the public page.

## Security and privacy

The snapshot is built as an allowlist projection of public fields. The model
boundary is considered external egress even with a local upstream: the endpoint
and credential belong to the operator, and HTTPS is mandatory outside the
internal compose network. Prompt injection in an article/component description
is treated as data, and the versioned instruction prohibits executing
instructions contained in it. The raw prompt/response is retained only in a
separate, disabled-by-default, redacted diagnostic mode without credentials or
private facts.

AI text has `model` provenance but does not receive evidence semantics. The
factual validator accepts only claims derivable from the snapshot; an unknown
claim causes the entire candidate to be discarded rather than published with a
warning.

## Compatibility and migration

Rollout follows expand/migrate/switch/contract: add tables and nullable service
presentation fields; enable dual reads with the current presenter; backfill
base revisions for existing public subjects; compare HTML/metadata; switch
web/sitemap/LLM reads; enable enrichment last. The old web image ignores the
new tables. When no active revision exists, the new web uses the fallback from
`REQ-5331`.

Article authoring, revisions, repository import, and public serving are owned
by `SPEC-054`; SEO accepts only the event for the exact active revision.
Rolling back enrichment restores the current presenter without changing the
active article set; the new SEO tables are retained until the end of the
compatibility window.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-5301` | An integration test repeatedly delivers a component/setup publication and obtains one snapshot and one active effect. |
| `REQ-5302` | An integration test obtains one SEO effect for a new active article revision and unpublication and preserves domain publication when the worker fails. |
| `REQ-5303` | A service relation change test enqueues a rebuild only for the service and affected country subjects with a new aggregate digest. |
| `REQ-5304` | A schema/property test accepts only a public allowlist snapshot and rejects secret/private/artifact body content. |
| `REQ-5305` | A migration test verifies revision fields and the unique active pointer per subject/locale. |
| `REQ-5306` | A concurrent activation test does not lose the generation and does not expose an incomplete or stale revision. |
| `REQ-5307` | A parameterized test for five subject kinds and two locales builds a complete base profile without network access. |
| `REQ-5308` | An E2E test with unavailable LiteLLM/CLIPROXY publishes the domain object, activates the base, and serves the sitemap/page. |
| `REQ-5309` | A web test verifies the stable canonical and the absence of an independent canonical for version/query variants. |
| `REQ-5310` | A locale matrix declares hreflang only for an existing active revision. |
| `REQ-5311` | A snapshot test compares visible HTML with JSON-LD and finds no hidden claims. |
| `REQ-5312` | Kind-specific fixtures show all mandatory sections using only snapshot facts. |
| `REQ-5313` | A lifecycle/fullness/availability matrix returns deterministic eligibility and stable reasons. |
| `REQ-5314` | Eligible and non-eligible fixtures verify consistency between robots and sitemap membership. |
| `REQ-5315` | The generator emits absolute canonicals, actual lastmod, existing alternates, and splits 50,001 URLs into two shards. |
| `REQ-5316` | Concurrent activations invalidate the shared generation cache without lost URLs or writes to a shared file from the handler. |
| `REQ-5317` | A web test reads OG/Twitter metadata and a 1200×630 immutable image with public cache headers. |
| `REQ-5318` | An E2E test proceeds from compact `llms.txt` through the manifest to detail Markdown without loading the entire catalog as one document. |
| `REQ-5319` | A crawler test reaches every eligible fixture from hubs using only server-rendered `<a href>` links. |
| `REQ-5320` | Disabled configuration does not enqueue enrichment and completes the flow with an active base revision without error. |
| `REQ-5321` | An HTTP contract test observes one call to the configured LiteLLM URL by alias and finds no upstream routing logic in the handler. |
| `REQ-5322` | The captured request conforms to the schema and contains no credential, private facts, artifact, or finding body. |
| `REQ-5323` | An adversarial response with canonical/trust/index fields is rejected in its entirety. |
| `REQ-5324` | A tabular corpus separately rejects an invalid schema/locale/URL, a secret, an unsupported claim, a duplicate, a boilerplate snippet, weak intents, and incomplete kind-specific coverage; an integration test accepts a corrected candidate after a bounded retry. |
| `REQ-5325` | A response for an old digest becomes `stale`, and repetition of the same coordinates uses one idempotency key. |
| `REQ-5326` | An operator test disables enrichment and atomically returns the subject to the latest base revision. |
| `REQ-5327` | A public read test does not access session/cookies and has public caching; private preview is `no-store`. |
| `REQ-5328` | An XSS/prompt-injection corpus does not produce raw HTML/script in HTML, JSON-LD, or Markdown. |
| `REQ-5329` | A secret scan of DB/job/log/API/repository and the CLI dependency closure finds no model credential/client. |
| `REQ-5330` | A metrics snapshot contains the listed aggregates without a prompt, body, subject ID, or job payload. |
| `REQ-5331` | A fault-injection test continues to serve the latest active revision, while pending materialization receives a `noindex` fallback rather than a soft 404. |
| `REQ-5332` | A bounded rebuild with a new generator version creates a revision and does not change domain `updated_at`/sitemap `lastmod` when visible content is unchanged. |
