---
description: "How to measure catalog search latency on PostgreSQL 16 without a new harness."
last_verified: "2026-09-04"
---

# Catalog search benchmark

Catalog search is PostgreSQL-native (`ADR-0151`). There is no separate
benchmark framework. Use `EXPLAIN (ANALYZE, BUFFERS)` on a representative
database and time the HTTP handler.

## Targets

Server-side, measured, not claimed:

| Path | p95 |
| ---- | --- |
| Filter-only listing | ≤ 40 ms |
| Text search (`q`) | ≤ 70 ms |
| Full `/v1/catalog/components` or `/setups` | ≤ 100 ms |

## Preconditions

- PostgreSQL 16 with migrations at head, including `0040_catalog_search_projection`
- `catalog_search_projection` rebuilt (`rebuild_catalog_search_projection`)
- A corpus on the order of production (thousands of latest public objects, not
  the fixture dozen)

## Plans to capture

Run each statement with `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)`. Expect
index use on `ix_catalog_search_projection_fts` for `q`, array GIN for tags
and harnesses, and the partial B-tree indexes for `updated_at` / `likes`
sorts on `lifecycle_state = 'active'`. A sequential scan of
`catalog_search_projection` on a large corpus is a miss.

Filter-only, likes descending:

```sql
SELECT object_kind, stable_id
FROM catalog_search_projection
WHERE object_kind = 'component'
  AND lifecycle_state = 'active'
ORDER BY likes_count DESC, updated_at DESC, stable_id DESC
LIMIT 21;
```

Text search:

```sql
SELECT object_kind, stable_id,
       ts_rank_cd(search_vector, plainto_tsquery('simple', 'python')) AS rank
FROM catalog_search_projection
WHERE object_kind = 'component'
  AND lifecycle_state = 'active'
  AND (
    search_vector @@ plainto_tsquery('simple', 'python')
    OR strpos(search_text, 'python') > 0
  )
ORDER BY rank DESC, updated_at DESC, stable_id DESC
LIMIT 21;
```

## HTTP timing

Against a local API with the same database:

```text
python -m pytest tests/api/platform/test_catalog_search.py -k sql_path --no-cov
```

For wall-clock p95, repeat `GET /v1/catalog/components?page_size=20` and
`GET /v1/catalog/components?q=python&page_size=20` with `include_experimental`
as required by the corpus, from a client that records status and elapsed time.
Do not treat a fixture-sized database as evidence that the budget passed.
