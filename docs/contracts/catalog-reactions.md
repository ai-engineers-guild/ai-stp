---
description: "Private account reactions to public catalog components and setups."
last_verified: "2026-08-17"
---

# Catalog reactions

A reaction is a private idempotent association between the current account and a
public `component` or `setup`. Public catalog projections return only the
non-negative aggregate `likes_count`; account IDs and the list of reacting
accounts are not published.

The authenticated HTTP surface:

- `GET /v1/account/catalog-reactions` returns `CatalogReactionList`;
- `PUT /v1/account/catalog-reactions/{object_kind}/{stable_id}` creates a reaction;
- `DELETE /v1/account/catalog-reactions/{object_kind}/{stable_id}` removes a reaction.

`object_kind` accepts only `component` or `setup`, and `stable_id` must match the
selected kind. An invisible or absent object responds with `AI_STP_NOT_FOUND`;
an absent session responds with `AI_STP_AUTH_REQUIRED`. Repeated `PUT` and
`DELETE` calls do not change the result beyond the requested state.

`CatalogReactionState` contains `schema_version`, `liked`, and `likes_count`.
`CatalogReactionList` contains `schema_version` and `items`; each item contains
`object_kind` and the corresponding public `ComponentSummary` or `SetupSummary`.
The list belongs only to the current account and does not disclose other
accounts' reactions.
