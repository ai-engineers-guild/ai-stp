---
description: "Decision to materialize SEO as a server-side projection of published facts and permit optional model enrichment only after deterministic publication."
last_verified: "2026-08-29"
---

# ADR-0131: SEO is a server-side projection; the model is an optional editor

Status: proposed. Refines `ADR-0022`, `ADR-0038`, `ADR-0076`, `ADR-0088`,
`ADR-0089`, and `ADR-0095`.

## Context

The public catalog already has server-rendered pages for components, setups,
services, and countries, while the repository content hub has article pages.
Articles receive their own metadata and JSON-LD, but the sitemap lists only
static routes and articles; the remaining public entities inherit shared
metadata and do not form a complete search surface. Creating a service changes
mutable catalog metadata, while an article becomes available only as part of a
new web image, so these two sources have no common publication event.

The SEO representation depends simultaneously on immutable published data and
mutable public relationships: the author's profile, external services,
countries, media, and current availability state. Writing SEO fields into a
passport would change its digest without changing the installable object;
building every field on each web request would make the result unstable and
unauditable.

`ADR-0022` prohibits `ai_stp` from invoking a model interface so that the local
CLI, passports, selection, validation, and installation do not depend on a key,
account balance, network, or nondeterministic response. A different boundary
exists for a public editorial projection: the server already operates
asynchronously and can degrade to a mechanically complete result without
affecting the object's trust or fitness.

## Options

1. **Build metadata only in Next.js from the current API response.** A small
   diff, but the sitemap, OG, LLM documents, and HTML would duplicate rules, and
   the result could not be tied to an exact set of source facts.
2. **Store SEO fields in the passport or article Markdown.** The form is clear
   to the author, but presentation becomes mixed with immutable domain identity,
   while services and derived regional pages still lack a shared mechanism.
3. **Block publication on a synchronous model call.** This immediately produces
   one text variant, but catalog availability and correctness become dependent
   on an external nondeterministic system.
4. **Materialize a deterministic server-side projection and improve it with an
   optional background model call.** Accepted: every object immediately gets a
   correct page, while the AI result is enabled only after validation and an
   atomic switch of the active revision.

## Decision

The platform stores immutable `SeoFactSnapshot` and `SeoRevision` objects, and
the `SeoActiveRevision` pointer selects one active revision for each
subject/locale pair. Subject is a closed set: `component`, `setup`, `article`,
`service`, or `country`. A snapshot contains only public facts and their
aggregate digest; SEO does not change the passport, trust, lifecycle, or source
article.

Every publication event or change to public facts transactionally enqueues an
idempotent `seo_build` in the existing PostgreSQL queue. The handler first
creates and activates a deterministic base revision. Unavailability of any
model-serving path does not delay this transition or change index eligibility.

After the base revision, `seo_enrich` is optionally enqueued. The worker calls
one OpenAI-compatible LiteLLM endpoint; model selection, fallback, and upstream
CLIPROXY belong to LiteLLM. No credential or full model prompt enters the job,
snapshot, log, or database. A response is accepted only against a closed JSON
Schema, passes validation of length, URL, language, claim provenance, secrets,
and exact `source_digest`, after which the new revision is activated in one
transaction.

This refines `ADR-0022`: the CLI, agent-facing core, passports, selection,
validation, domain-object publication, and installation still do not invoke a
model and do not require a model credential. Only server-side presentation
enhancement after a completed base revision may call the operator's LiteLLM;
disabling that path leaves the entire product function intact except for
editorial text enhancement.

The web, sitemap, Open Graph image, JSON-LD, and LLM documents read one active
SEO revision. Sitemap and LLM indexes are cacheable projections, not files
appended by every job. Their generation changes when a revision is activated;
an immutable OG asset is addressed by revision ID.

Article authoring, repository import, staff publication, and active serving
belong to `ADR-0132`; SEO receives the exact active `ArticleRevision` and does
not change its lifecycle or body. A service remains separate from passport
catalog metadata under `ADR-0088`, but index eligibility requires a public
description and verifiable source URL, and every change to its aggregate creates
a new SEO snapshot.

## Consequences

- A new server-side domain projection and two job types appear; no external
  broker or separate SEO service is needed.
- `LiteLLM` and `CLIPROXY` are deployed in a separate optional compose profile
  and do not enter the CLI dependency closure or mandatory API/worker startup.
- Redelivery is safe by subject, locale, source digest, template, and prompt
  version; a superseded model response is stored as `stale` but not activated.
- A model response is never evidence and cannot define canonical, lifecycle,
  trust, verification, or `index_eligible`.
- Rollback disables enrichment and returns the pointer to the latest base
  revision; deletion of the new tables before the compatibility window ends is
  prohibited.
- Changing the template, prompt, or model does not change the domain object; an
  explicit rebuild creates a new SEO revision of the same snapshot.

## Reconsideration conditions

- The deterministic base profile measurably fails to publish a useful page
  without a model.
- Sitemap volume exceeds the limit of one file or generation becomes expensive;
  only the shard/cache strategy then changes.
- Several independent consumers of domain events appear; the PostgreSQL queue
  is then reevaluated against an outbox relay/broker.
- Model enrichment begins to affect domain publication, validation, or trust;
  that requires a separate decision and is not an extension of this ADR.
