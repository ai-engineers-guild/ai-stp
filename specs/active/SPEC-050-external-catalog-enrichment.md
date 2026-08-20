---
description: "SPEC-050: Безопасное обогащение каталога наблюдаемыми метаданными внешних каталогов."
last_verified: "2026-08-16"
---

# SPEC-050: Внешнее обогащение каталога

## Цель

Platform дополняет точную публичную ревизию компонента ограниченными наблюдаемыми
метаданными `skills.sh`, Nori и `modelcontextprotocol.com`, не копируя артефакты и
не превращая внешний сигнал в паспорт, подтверждение или линию доверия.

## Границы

Спецификация охватывает server-owned metadata adapters, несколько внешних ссылок,
freshness и безопасную деградацию. Импорт bytes, публикация, установка, изменение
паспорта и сопоставление по похожему имени не входят. Общая authority-модель
принадлежит `SPEC-045` и `ADR-0083`, wire contract —
`docs/contracts/federated-sources.md`.

## Термины

- **Exact coordinate** — заранее сохранённая пара `provider` и `external_identifier`.
- **Metadata observation** — ограниченный allowlist внешних полей; не паспорт
  и не доказательство.
- **Policy gate** — сохранённые attribution, terms URL и разрешающий допуск до
  fetch и показа.

Канонические поля и freshness принадлежат `docs/contracts/federated-sources.md`.

## Требования

- `REQ-5001`: Поддерживаются только adapters `skills_sh`, `nori` и
  `modelcontextprotocol`; каждый возвращает общий metadata projection и сохраняет
  собственные attribution и terms reference.
- `REQ-5002`: Adapter принимает только закрытый allowlist полей из контракта,
  ограничивает размер ответа, глубину и число элементов JSON, длины строк и число
  references и не исполняет полученный content.
- `REQ-5003`: Связь создаётся только по заранее сохранённой exact coordinate.
  Имя, описание, URL или package name без provider namespace не создают связь.
- `REQ-5004`: Одна точная ревизия может иметь несколько независимых references.
  Deduplication выполняется только по provider и external identifier; отказ одной
  ссылки не меняет остальные.
- `REQ-5005`: Успех сохраняет `fetched_at`, `checked_at` и `expires_at`. После TTL
  последнее допустимое значение становится `stale`; безопасный fetch/parse failure
  даёт `unavailable`, не удаляя последнее допустимое наблюдение.
- `REQ-5006`: Cache ограничен числом записей и TTL; fetch имеет timeouts, запрет
  credentials и redirect escape, bounded response и per-provider rate limit.
- `REQ-5007`: Fetch и показ provider разрешены только при сохранённых attribution,
  terms URL и разрешающем policy gate. Запрет закрыто отключает adapter.
- `REQ-5008`: Внешние metadata всегда остаются observation и не меняют
  `author_verified`, `component_verified`, `trust_lane`, lifecycle, install
  eligibility или ranking без отдельной спецификации.
- `REQ-5009`: Fixtures и общий conformance suite каждого adapter покрывают happy
  path, oversized/poisoned/malformed payload, unknown fields, timeout/rate limit,
  stale/unavailable и exact-coordinate mismatch.

## Состояния и ошибки

Свежесть принимает `fresh`, `stale` или `unavailable`. Закрытый допуск политики,
несовпадение точной координаты, истечение времени, ограничение частоты и ошибка
разбора не создают связь и не удаляют последнее допустимое наблюдение. Отказ
одной ссылки не меняет остальные.

## Безопасность и приватность

Adapter не исполняет полученный content, не передаёт credentials и не копирует
artifact bytes. Fetch и показ закрыты, пока не сохранены attribution, terms URL
и разрешающий policy gate. Модель угроз принадлежит
`docs/engineering/federated-source-threat-model.md`.

## Совместимость и миграция

Отсутствие enrichment и выключенный adapter дают прежнюю публичную проекцию.
Откат скрывает additive поля без изменения паспортов, artifacts и coordinates.

## Критерии приёмки

| Требование | Исполнимое доказательство |
|---|---|
| `REQ-5001` | Contract и adapter tests подтверждают три provider и общий metadata projection. |
| `REQ-5002` | Bounded parser tests отклоняют oversized, poisoned, malformed payload и unknown fields. |
| `REQ-5003` | Tests подтверждают связь только по exact coordinate. |
| `REQ-5004` | Tests подтверждают несколько независимых references и изолированный отказ. |
| `REQ-5005` | Clock-controlled tests подтверждают TTL, stale и сохранение последнего допустимого значения. |
| `REQ-5006` | Tests подтверждают bounded cache, timeouts, запрет credentials и per-provider rate limit. |
| `REQ-5007` | Policy fixture запрещает fetch и projection без attribution/terms permission. |
| `REQ-5008` | Regression tests доказывают неизменность verification, trust и install eligibility. |
| `REQ-5009` | Общий conformance suite выполняется для fixtures всех трёх adapters. |
