---
description: "Решение хранить GitHub archived state как внешнее evidence, а не автоматический lifecycle."
last_verified: "2026-08-13"
---

# ADR-0082: GitHub archived state остаётся внешним evidence

Статус: принято.

## Контекст

Публичный GitHub repository может быть архивирован, переименован, перенесён или
снова открыт. Это полезный сигнал устаревания, но не решение автора или
модератора о lifecycle опубликованной версии. Автоматический `blocked` либо
удаление target смешали бы внешний факт с политикой и сделали сетевой сбой
основанием для необратимого действия.

## Решение

CLI читает официальный `GET /repos/{owner}/{repo}` только для source точной
локальной версии и сохраняет append-only observation. Устойчивая identity —
GitHub repository id; `full_name` является изменяемой координатой. Archived
создаёт датированное предложение `deprecated`, но не меняет lifecycle. Offline
ответ использует последнее успешное observation с TTL. Ошибки и отсутствие
доступа остаются `unavailable`.

Транспорт использует conditional request, не следует redirect и не имеет
credential surface. Поэтому первая версия получает только public metadata, а
private repository остаётся неразличимым `unavailable`.

## Последствия

История сохраняет archived и последующий unarchive. Rename/transfer не теряют
identity. Rate limit и outage не создают ложное устаревание. Platform/web могут
позже проецировать тот же общий контракт, но локальная реализация не изображает
account-wide полноту.

## Условия пересмотра

Решение пересматривается при добавлении другого forge, автоматического lifecycle
workflow, account-wide polling или server-owned cache. Каждое из них меняет
полномочия либо сетевую границу и требует отдельного контракта.
