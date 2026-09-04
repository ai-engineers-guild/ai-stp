---
description: "Public catalog search is a PostgreSQL projection compiled from Catalog QL."
last_verified: "2026-09-04"
---

# ADR-0151: PostgreSQL catalog search projection

Status: accepted.

## Context

Catalog listing scanned public `catalog_metadata` rows in Python, collapsed
latest versions in process, and applied Catalog QL, structural filters, and
sorts after the fetch. Cursor mode walked publication order rather than the
requested sort. Equivalent query strings produced different cursor signatures
when list order or singular-versus-list filter forms differed. A production
special case treated `q=pytest` as a hit on the fixture component.

`ADR-0073` already chose a bounded AST, mutually exclusive cursor and page
modes, and in-database indexes. It did not choose an execution engine. Adding
Elasticsearch, OpenSearch, or Redis would add an operational system, a second
consistency domain, and a new dependency without removing PostgreSQL.

## Options

1. Keep the Python scan and add caches. Latency stays linear in catalog size
   and cursor/sort bugs remain in application code.
2. Introduce an external search engine. This violates the existing platform
   stack (`ADR-0009`) and the task constraint against new search dependencies.
3. Maintain one row per `(object_kind, stable_id)` in PostgreSQL, compile the
   allowlisted AST to parameterized SQLAlchemy, and execute latest selection,
   filters, ranking, totals, and keyset pagination in SQL.

## Decision

Option 3 is accepted.

Public catalog search reads `catalog_search_projection`, not a Python walk of
every published version. The projection is one row for the latest public
version of each object, compared as numeric `X.Y`, and is written in the same
transaction as publication, lifecycle, likes, and relation changes. A
deterministic rebuild reconstructs the table from `catalog_metadata`.

Catalog QL remains the parser in `catalog_query_language`. The compiler emits
SQLAlchemy expressions bound as parameters. Plain terms match the stored
search document; field predicates use columns and arrays. `AND`/`OR`/`NOT`/
`IN`/`NOT IN` keep their typed meaning. Input is never interpolated into SQL.

Text search uses a stored weighted `tsvector` with a GIN index. Ranking uses
deterministic discrete field scores plus `ts_rank_cd` on that vector, then
`updated_at` and `stable_id`. Arbitrary substring matching is deliberately not
part of the text predicate: it would force a scan unless `pg_trgm` becomes an
explicit platform dependency. Name fragments remain a ranking signal after
the indexed text predicate has selected candidates.

Cursor keys are the selected sort keys plus `stable_id`, truncated to
millisecond time resolution. The filter signature canonicalizes `q` (trim;
blank is absent), sorts unique multi-value filters, and merges singular
`harness_id`/`component_type` with list forms using OR. Relationship facets
keep AND-between / OR-within semantics, including same-product AND for
service and country, via SQL `EXISTS` rather than independent arrays.

Trust, lifecycle, and public-visibility rules are unchanged. Experimental
rows still require request-scoped consent. Default listing still hides
non-`active` rows. Hidden and private objects are absent from the projection.

No Elasticsearch, OpenSearch, Redis, or other search dependency is added.

## Consequences

- Alembic grows a reversible `catalog_search_projection` migration with GIN
  and partial B-tree indexes.
- Publication, owner lifecycle, likes, seed, and relation attach/detach call
  the same upsert. Operators rebuild with the documented function after a
  repair.
- Existing cursors that lack sort keys fail as an unsupported version rather
  than silently walking the wrong order.
- Web harness facets are generated from `HARNESS_ID_ORDER` so `cursor` and
  `antigravity` cannot drop out of the filter source.
- Rollback drops the projection table and restores the previous Python scan
  only by reverting this change; published passports are untouched.

## Revisit conditions

Revisit if measured filter-only p95 exceeds 40 ms, text-search p95 exceeds
70 ms, or API p95 exceeds 100 ms on a representative PostgreSQL 16 corpus
after indexes are used; if exact page totals no longer fit the budget; or if
product policy moves catalog search off PostgreSQL.
