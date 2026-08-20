---
description: "Машинный контракт общих descriptors для local ports и metadata adapters."
last_verified: "2026-08-16"
---

# Federated sources

## Общая граница

`FederatedSourceDescriptor` версии `federated-source/1` проецирует внешний
источник без переноса его vendor schema в паспорт. `source_kind=local_port`
обозначает exact локальный snapshot; `metadata_adapter` — официальное удалённое
наблюдение. Оба вида имеют `authority=external_observation`, ложные verification
оси и `target_write=false`.

Поля и закрытые vocabulary принадлежат генерируемой схеме
`federated-source-descriptor`. `FederatedSourceSet` хранит несколько references
одного ASTP object и фиксирует `auto_merged=false`.

## Identity и deduplication

Dedup key равен точной паре provider/external identifier. Для SX/APM external
identifier — snapshot digest. Для доступного GitHub observation — immutable
repository id; до первого успешного наблюдения — точная source coordinate.
Похожее имя и наблюдаемые показатели другого provider не являются точным
совпадением identity.

## Полномочия

Local port может объявить только `confirmed_private_draft_import`: реальный import
остаётся отдельной digest-bound операцией с подтверждением. Metadata adapter имеет
`registry_effect=none`. Ни один descriptor не публикует объект, не изменяет
eligibility, verification, lifecycle или target.

## Freshness и расширение

Локальный snapshot имеет `local_snapshot`, фиксирует `checked_at` и не выдумывает
время сетевого fetch. Удалённое наблюдение имеет `fresh`, `stale` либо
`unavailable`; только unavailable не содержит `fetched_at`. `external_state`
переносит `present`, `archived` либо `unavailable` как наблюдение, а не решение
жизненного цикла ASTP. У локального порта нет сетевого ограничения частоты;
адаптер метаданных обязан соблюдать собственную политику TTL и ограничения
частоты. Добавление `provider` или `source_kind` меняет закрытый контракт и
требует спецификацию, генерацию схемы и проверочную фикстуру.

## Catalog metadata adapters

Server-owned adapters имеют provider `skills_sh`, `nori` или
`modelcontextprotocol`. Exact coordinate задаётся до fetch и содержит provider и
его immutable external identifier; ответ не может сам связать себя с ASTP object.
Один object хранит несколько таких descriptors.

Allowlist наблюдения: `display_name`, `summary`, `homepage_url`, `repository_url`,
`published_at`, `updated_at`, `popularity_count` и `external_state`. Поля
необязательны и bounded; неизвестные поля отбрасываются до persistence. Descriptor
отдельно хранит source URL, attribution, terms URL, `fetched_at`, `checked_at`,
`expires_at` и freshness. Artifact content, executable snippets, verification,
trust и install claims не входят.

Общие верхние границы: `256 KiB` response, JSON depth `16`, `100` collection
элементов, `4096` кодовых точек Unicode на строку, `8` references на ревизию, connect
timeout `2 s`, read timeout `5 s`, cache `1000` записей на provider и TTL `6 h`.
Лимит fetch — не более `60` запросов в минуту на provider и не выше опубликованного
ограничения источника. Более строгая provider policy всегда имеет приоритет.
