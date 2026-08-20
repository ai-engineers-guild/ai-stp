---
description: "Решение хранить оформление компонента отдельно от immutable passport и безопасно доставлять media."
last_verified: "2026-08-10"
---

# ADR-0075: Component media gallery и reactions

Статус: принято.

## Контекст

Immutable passport версии уже владеет source repository и техническими фактами,
но gallery, preview choice и like меняются независимо. Включение их в паспорт
создавало бы новую версию компонента при каждом оформительском изменении.

## Решение

Хранить component presentation как ревизуемую object-level проекцию с максимум
пятью ordered media records. Owner upload идёт через
`POST /v1/owner/objects/component/{stable_id}/presentation/media` (allowlist
JPEG/PNG/WebP/GIF/MP4/WebM до 25 MiB) и выдаётся как
`/v1/media/component/{media_id}`; GitHub reference закрепляется commit SHA;
YouTube представлен validated ID. Preview задаётся явным `position = 0`.
Public catalog соединяет только ready projection.

Individual likes хранятся отдельной unique reaction `(account_id, object_kind,
stable_id)`, а `catalog_metadata.likes_count` остаётся публичным агрегатом.
Жалобы остаются в существующем report-case контуре.

## Последствия

Нужны таблицы media/presentation/reaction, owner mutation API и worker job для
нормализации, политика кэша для signed URL, публичная проекция галереи и web-
редактор. Удаление media сначала снимает его с projection, затем асинхронно
удаляет blob после retention window.

## Условия пересмотра

Решение пересматривается при появлении собственного video streaming, media
moderation service или юридической обязанности хранить исходные файлы дольше.
