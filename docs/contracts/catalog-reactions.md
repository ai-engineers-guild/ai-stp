---
description: "Приватные reactions аккаунта на публичные компоненты и сетапы каталога."
last_verified: "2026-08-17"
---

# Catalog reactions

Reaction — приватная idempotent связь текущего аккаунта с публичным `component`
или `setup`. Публичные catalog projections возвращают только неотрицательный
aggregate `likes_count`; account IDs и список отреагировавших не публикуются.

Аутентифицированная HTTP-поверхность:

- `GET /v1/account/catalog-reactions` возвращает `CatalogReactionList`;
- `PUT /v1/account/catalog-reactions/{object_kind}/{stable_id}` создаёт reaction;
- `DELETE /v1/account/catalog-reactions/{object_kind}/{stable_id}` удаляет reaction.

`object_kind` принимает только `component` или `setup`, а `stable_id` обязан
соответствовать выбранному виду. Невидимый или отсутствующий объект отвечает
`AI_STP_NOT_FOUND`; отсутствие сессии — `AI_STP_AUTH_REQUIRED`. Повторный `PUT`
и повторный `DELETE` не меняют результат сверх требуемого состояния.

`CatalogReactionState` содержит `schema_version`, `liked` и `likes_count`.
`CatalogReactionList` содержит `schema_version` и `items`; каждый item содержит
`object_kind` и соответствующий публичный `ComponentSummary` или `SetupSummary`.
Список принадлежит только текущему аккаунту и не раскрывает чужие reactions.
