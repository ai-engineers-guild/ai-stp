---
description: "Машинный контракт repository import, staff publication и публичного чтения статей."
last_verified: "2026-08-29"
---

# Публикация статей

`SPEC-054` владеет поведением, `ADR-0132` — архитектурным решением. Этот документ
владеет идентичностью, полями, API operations и стабильными ошибками публикации статей.

## Идентичность и происхождение

Article identity — строка `{type}:{slug}`. `type` принимает `article`,
`blog_post`, `changelog`, `release_notes`; `slug` соответствует
`^[a-z0-9]+(?:-[a-z0-9]+)*$` и не длиннее 120 символов.

`source_kind` принимает `repository` или `staff` и закрепляется при создании
Article. Repository revision содержит точный 40-hex `source_ref` и относительный
`source_path` внутри `apps/web/content/hub`; staff revision не публикует ID актора.

Локализованная revision имеет `revision_id` и `content_digest`. Canonical digest
покрывает `type`, `slug`, `locale`, `title`, `description`, `published_at`,
упорядоченные tags, тело Markdown и публичное происхождение. Active digest покрывает
точные RU/EN идентификаторы revisions одной Article.

## Общая localized entry

```text
type             = article | blog_post | changelog | release_notes
slug             = lowercase kebab-case, at most 120 characters
locale           = ru | en
title            = 1..160 characters
description      = длина 1..320 символов
published_at     = YYYY-MM-DD, not in the future
tags             = уникальный массив до 12 элементов длиной 1..40 символов
body             = safe Markdown, 1..200000 characters
content_digest   = canonical digest of all public revision fields
source_kind      = источник repository | staff
source_ref       = exact commit for repository, absent for staff
source_path      = repository-relative path for repository, absent for staff
```

Неизвестные поля request, повторяющиеся tags, неверные даты, raw HTML, опасные URL
и наборы locales кроме точной пары `ru` плюс `en` отклоняются.

## Repository snapshot v1

```text
schema_version       = 1
repository           = репозиторий ai-engineers-guild/ai-stp
commit               = exact 40-hex commit
snapshot_digest      = canonical digest repository, commit и sorted entries
expected_generation  = целое неотрицательное число
entries              = at most 10000 localized entries
```

Каждая entry добавляет `source_path`. Snapshot содержит только entries с
`draft=false`, является полным replacement repository-owned active set и не
содержит build timestamp, credential или host path.

`GET /v1/content/repository/state` возвращает текущие `generation`,
`snapshot_digest` и `commit` без entries. Operation требует import credential.

`POST /v1/content/repository/import` принимает snapshot. Ответ:

```text
schema_version   = 1
generation       = resulting generation
snapshot_digest  = принятый digest snapshot
created          = number of new localized revisions
activated        = number of changed active pointers
removed          = number of removed active pointers
unchanged        = число неизменившихся active pointers
```

Тот же snapshot digest при текущей generation возвращает `no_op` counts без
новых revisions или jobs. Несовпадение `expected_generation` возвращает
`AI_STP_CONTENT_STALE`.

## Staff publication v1

`PUT /v1/staff/content/{type}/{slug}` принимает:

```text
schema_version          = 1
expected_active_digest  = digest текущей RU/EN пары либо null при создании
translations            = точный объект {ru, en}
```

Каждый translation содержит `title`, `description`, `published_at`, `tags` и
`body`. Operation создаёт и активирует обе localized revisions одной
транзакцией. Ответ содержит `article_id`, `active_digest`, RU/EN `revision_id` и
public article representation.

`DELETE /v1/staff/content/{type}/{slug}` требует `expected_active_digest`, снимает
обе locales с публикации и сохраняет revisions. Повтор после успешного unpublish
возвращает тот же конечный результат.

Обе operations требуют session текущего account из staff allowlist и создают
private AuditEvent. Они не принимают `source_kind`, `source_ref`, `source_path`
или actor ID из request.

## Public reads v1

`GET /v1/content?locale={ru|en}` возвращает опубликованные repository- и
staff-owned entries одной locale, отсортированные сначала по убыванию
`published_at`, затем по возрастанию identity статьи.

`GET /v1/content/{type}/{slug}?locale={ru|en}` возвращает active detail либо
`AI_STP_NOT_FOUND`. Автоматический fallback locale отсутствует.

Краткий ответ содержит `type`, `slug`, `locale`, `title`, `description`,
`published_at`, `tags`, `revision_id`, `content_digest` и `source_kind`. Detail
добавляет Markdown `body`; для `repository` добавляются exact `source_ref` и
`source_path`. Public response не содержит inactive revisions, actor ID или
audit fields.

Оба ответа имеют public `ETag`, вычисленный из active generation/digest, и
допускают `Cache-Control: public`. Conditional GET возвращает `304` без body.

## Авторизация

Repository state/import принимает только отдельный bearer credential scope
`content_import`. Он не является пользовательской session и не разрешает staff
operations. Staff publication принимает только действующую session account ID из
операторской staff allowlist. Public reads anonymous.

## Stable errors

| Код | Условие |
|---|---|
| `AI_STP_CONTENT_INVALID` | Нарушена schema, limits, digest, locale parity или safe Markdown policy. |
| `AI_STP_CONTENT_SOURCE_CONFLICT` | Identity уже принадлежит другому source owner. |
| `AI_STP_CONTENT_STALE` | Expected generation или active digest не совпадает. |
| `AI_STP_CONTENT_IMPORT_FORBIDDEN` | Import credential отсутствует, недействителен или имеет другой scope. |
| `AI_STP_NOT_FOUND` | Active article или запрошенная locale отсутствует. |

Error response не возвращает Markdown body, snapshot entries, credential,
private actor или полный request.
