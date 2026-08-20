---
description: "SPEC-045: Федеративные source descriptors и границы внешних наблюдений."
last_verified: "2026-08-16"
---

# SPEC-045: Federated source boundaries

## Цель

Один общий контракт различает локальный import port и сетевой metadata adapter,
сохраняет attribution и freshness каждого внешнего наблюдения и не смешивает его
с паспортом, доверием либо правом записи итогового target.

## Границы

Спецификация владеет shared source descriptor и conformance правилами. Конкретный
локальный import принадлежит SPEC-042, GitHub archive evidence — SPEC-044,
server-owned catalog enrichment — `SPEC-050`. Контракт не копирует
artifact bytes и не создаёт автоматическую публикацию либо установку.

## Термины

- **Local port** — bounded чтение явно названного локального snapshot и отдельный
  подтверждённый import private draft.
- **Metadata adapter** — read-only наблюдение внешнего сервиса без владения
  каноническим паспортом.
- **Source descriptor** — provider, вид источника, точная внешняя identity,
  attribution, provenance, freshness и закрытые полномочия.
- **Dedup key** — точная пара provider/external identity, а не похожее имя.

## Требования

- `REQ-4501`: `federated-source/1` имеет два различных source kind —
  `local_port` и `metadata_adapter` — и сохраняет provider, canonical URL,
  external identifier, время, freshness, provenance и attribution.
- `REQ-4502`: Descriptor всегда объявляет `authority=external_observation`,
  `author_verified=false`, `component_verified=false` и `target_write=false`.
  Популярность, рейтинг и внешнее заявление не изменяют эти значения.
- `REQ-4503`: Local port получает `freshness=local_snapshot`, exact snapshot
  digest, `checked_at` и только возможность подтверждённого импорта локального
  draft. Adapter не получает import capability, имеет `fresh`, `stale` или
  `unavailable` и сам владеет соблюдением remote rate limits.
- `REQ-4504`: Dedup разрешён только при полном совпадении provider и external
  identifier. Совпадение имени, URL другого provider либо observed metadata не
  сливает объекты; один ASTP object может хранить несколько отдельных references.
- `REQ-4505`: Stale и unavailable reference не удаляют паспорт, другой reference
  или локальный объект. Removal/archive остаётся внешним сигналом с attribution,
  а захват source либо смена immutable identity закрываются conflict.
- `REQ-4506`: Poisoned metadata ограничивается closed allowlist-моделью, размером
  и безопасным parser конкретного adapter. Внешний source не исполняет код, не
  пишет final target и не становится runtime dependency ядра.
- `REQ-4507`: Добавление provider, вида source, provenance или authority требует
  новой совместимой версии descriptor либо явной миграции и conformance fixture.

## Состояния и ошибки

Freshness принимает `local_snapshot`, `fresh`, `stale` или `unavailable`.
Identity collision, неизвестный kind/provider и противоречивые полномочия дают
типизированный отказ. Недоступность одного reference не меняет остальные.

## Безопасность и приватность

Descriptor не содержит секрет, локальный path, закрытые bytes, значение environment
или device identity. Canonical URL не содержит credential и query. Модель угроз
принадлежит `docs/engineering/federated-source-threat-model.md`.

## Совместимость и миграция

Существующие StorePortDescriptor и GitHubArchiveEvidence преобразуются в общий
descriptor без изменения их операционных контрактов. Platform может хранить тот
же descriptor позже; это не даёт локальному CLI account-wide полноту.

## Критерии приёмки

| Требование | Исполнимое доказательство |
|---|---|
| `REQ-4501` | Schema corpus и fixtures преобразуют SX port и GitHub observation в разные kind одного контракта. |
| `REQ-4502` | Модель отклоняет попытку повысить authority/verification или разрешить target write. |
| `REQ-4503` | Local snapshot и remote fresh/stale/unavailable сохраняют разные capabilities и freshness. |
| `REQ-4504` | Exact key дедуплицируется, а одинаковое имя другого provider остаётся отдельным reference. |
| `REQ-4505` | Stale/unavailable fixture сохраняет другие references; identity collision тест SPEC-044 закрывается отказом. |
| `REQ-4506` | Conformance ссылается на bounded parser tests SPEC-042 и SPEC-044, а descriptor не принимает content/path/secret fields. |
| `REQ-4507` | Закрытые Literal vocabulary и schema generation требуют явного изменения для нового provider или kind. |
