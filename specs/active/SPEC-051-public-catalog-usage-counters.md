---
description: "SPEC-051: Приватные события и публичные счётчики просмотров и загрузок каталога."
last_verified: "2026-08-16"
---

# SPEC-051: Публичные счётчики использования каталога

## Цель

Показать на card и detail сопоставимые агрегаты просмотров публичной detail-страницы
и успешных выдач artifact download, не создавая пользовательскую историю и не
выдавая download за успешную установку.

## Границы

Считаются только разрешённый public detail read и завершённая сервером выдача
байтов артефакта. `CLI install success`, телеметрия харнесса, аналитика аккаунта,
уникальные пользователи и публичные сырые события не входят. Точный контракт
принадлежит `docs/contracts/catalog-usage-metrics.md`.

## Термины

- **Detail view** — успешный публичный ответ detail-страницы.
- **Artifact download** — успешная серверная выдача bytes артефакта; не
  install success.
- **Keyed digest** — краткоживущий HMAC-признак окна; raw IP, user-agent,
  account и device не хранятся.

Проводная семантика принадлежит `docs/contracts/catalog-usage-metrics.md`;
архитектурное решение — `ADR-0097`.

## Требования

- `REQ-5101`: Public projection содержит `detail_views_count` и
  `artifact_downloads_count`; card, detail и API используют один server aggregate.
- `REQ-5102`: View засчитывается после успешного public detail response. Download
  засчитывается после успешной передачи bytes; попытка, redirect, preflight, ошибка
  и metadata request не увеличивают счётчик.
- `REQ-5103`: Download означает выдачу bytes, отличается от install success и не
  меняет install eligibility, verification или trust.
- `REQ-5104`: Anti-abuse использует краткоживущий keyed digest от минимального
  сетевого признака, object/action и окна. Raw IP, user-agent, account/device
  identity и стабильный cross-window identifier не сохраняются; secret ротируется.
- `REQ-5105`: Dedup rows удаляются по короткому документированному retention;
  агрегаты не позволяют восстановить посетителя, event rows не публичны.
- `REQ-5106`: Necessary server-side fraud prevention не требует analytics consent
  и не загружает tracker; optional analytics остаётся consent-gated.
- `REQ-5107`: Feature flag отключает запись и показ обоих counters; выключенное
  состояние сохраняет старые поверхности без ложных нулей.
- `REQ-5108`: Конкурентные повторы в одном окне дают один atomic increment;
  разные окна и действия независимы.
- `REQ-5109`: Compact responsive UI показывает два подписанных значения; RU/EN,
  screen-reader labels и card/detail parity покрыты tests.

## Состояния и ошибки

Выключенный флаг оставляет поле `usage_metrics` пустым; отсутствие значения
не равно нулю. Попытка, перенаправление, предварительный запрос, ошибка и
запрос только метаданных не увеличивают счётчик загрузки. Повторы в одном
окне дают одно атомарное увеличение.

## Безопасность и приватность

Защита от злоупотреблений не сохраняет исходный адрес, строку клиента, учётную
запись, устройство или стабильный межоконный идентификатор. Строки дедупликации
живут короткий срок. Необходимая серверная защита не требует согласия на
аналитику и не загружает внешний наблюдатель.

## Совместимость и миграция

Поля additive и nullable при выключенном feature. Откат выключает запись/показ и
сохраняет агрегаты до отдельного управляемого удаления.

## Критерии приёмки

| Требование | Исполнимое доказательство |
|---|---|
| `REQ-5101` | API и component tests подтверждают card/detail/API parity одного aggregate. |
| `REQ-5102` | Tests подтверждают increment только после успешного detail response и выдачи bytes. |
| `REQ-5103` | Tests подтверждают отличие download от install success и неизменность eligibility. |
| `REQ-5104` | Privacy tests не находят raw identifiers и стабильный cross-window identifier. |
| `REQ-5105` | Tests подтверждают короткий retention dedup rows и отсутствие публичных event rows. |
| `REQ-5106` | Tests подтверждают no-consent и no-tracker behavior necessary anti-abuse. |
| `REQ-5107` | Feature-profile tests подтверждают отсутствие записи и полей при выключении. |
| `REQ-5108` | PostgreSQL concurrency test подтверждает один increment на окно. |
| `REQ-5109` | RU/EN component tests подтверждают compact accessible UI. |
