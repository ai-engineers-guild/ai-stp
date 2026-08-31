---
description: "Решение о публичной read-model для beta-поддержки, evidence и freshness."
last_verified: "2026-08-31"
---

# ADR-0072: Публичная read-model beta-поддержки, evidence и freshness

Статус: принято. Реализовано в серверной support projection, фильтрах API и вебе.

## Контекст

Issue #193 требует показать в API и web beta-статус, текущие доказательства и их
свежесть после выполнения P11-01, P11-02 и P11-03 для Pi, OpenCode и Grok Build.

В проекте уже существуют независимые понятия:

- `primary`/`beta` как уровень поддержки харнесса;
- `trust_lane` как линия доверия опубликованного объекта;
- `author_verified` и `component_verified`;
- publication evidence с результатом и `expires_at`.

Смешивание этих понятий приведёт к ложному выводу, что beta provider является
experimental object, либо что проверенный паспорт доказывает сквозную поддержку
харнесса. Нужна отдельная публичная read-model, не создающая второй policy engine
в web.

## Варианты

### 1. Вычислять beta-статус в web

Просто реализовать, но нарушает `ADR-0018` и `SPEC-022`: web станет вторым
источником бизнес-логики, а API, CLI и разные локали могут показать разные
результаты.

### 2. Выводить статус из `trust_lane` или `component_verified`

Не требует новых данных, но семантически неверно. Эти поля отвечают за доверие к
конкретной версии объекта и полноту publication checks, а не за provider support.

### 3. Хранить support evidence отдельно и отдавать безопасную server projection

Требует нового read-model и аддитивного wire-контракта, зато сохраняет независимые
оси, exact provenance, единый расчёт freshness и безопасную публичную границу.

### 4. Публиковать сырые provider reports

Даёт больше деталей, но раскрывает внутренние логи, topology, credentials или
непроверенные ссылки и делает формат внешних репозиториев частью API.

## Решение

Принимается вариант 3.

### Отдельная support evidence projection

Платформа хранит или импортирует нормализованную запись support evidence отдельно
от паспорта объекта и publication evidence. Она привязана к:

- `harness_id`;
- provider release identity;
- exact commit или digest;
- operating system и architecture;
- policy version;
- check id и результату;
- `observed_at` и `expires_at`.

В публичный API выходит только безопасная projection. Сырые отчёты, подписи,
storage keys, credentials и внутренние логи не выходят.

### Канонический расчёт состояния

Сервер вычисляет support state по текущей policy:

```text
verified      все обязательные checks passed и evidence не истекло
stale         обязательное evidence истекло
missing       обязательное evidence отсутствует
not_verified  evidence не удовлетворяет policy
```

Freshness вычисляется по server time и сохранённым timestamps, а не во время
рендера web. Web получает готовое состояние и только отображает его.

### Независимые оси

Support tier/state не меняют:

- `trust_lane`;
- `author_verified`;
- `component_verified`;
- eligibility к установке.

`beta` означает продуктовый уровень поддержки. `experimental` означает линию
доверия объекта. Объект может быть beta и authoritative либо beta и experimental,
если остальные правила это допускают.

### Public catalog API

Поля support projection добавляются аддитивно к catalog summary/detail/version
ответам. Фильтры support tier/state являются request parameters API и не изменяют
request-scoped consent для `experimental`.

Старый клиент, не знающий новых полей, продолжает работать в пределах текущей
major-версии. Значение отсутствующего evidence — `missing`, а не `verified`.

### Источник provider evidence

P11-01, P11-02 и P11-03 поставляют evidence из публичных provider repositories.
Платформа принимает только evidence, связанное с exact release и проверенное по
действующей release policy. Наличие issue, README или произвольного текста не
является evidence.

## Последствия

- `packages/contracts` получает новые модели support projection и фильтров;
- `schemas/v1/openapi.json` и generated web client обновляются из моделей;
- API/platform получают единый расчёт support state и freshness;
- web показывает только server projection;
- появляется миграция или отдельный storage/read-model для support evidence;
- фикстуры покрывают `fresh`, `stale`, `missing`, `failed` и conflicting evidence;
- release evidence связывается с exact provider SHA;
- существующие catalog rows не переписываются и получают `missing` до импорта
  support evidence;
- beta evidence не блокирует первый MVP release;
- rollback может отключить projection и фильтры без удаления исторических данных.

## Безопасность

Public projection не является bearer credential и не содержит адресов, по которым
можно получить private artifact. Неизвестный, повреждённый или противоречивый
evidence не повышает статус. Ошибка parsing или provenance не должна быть
замаскирована под свежую проверку.

## Условия пересмотра

ADR пересматривается, если:

- provider evidence станет credentialed/private и потребует отдельной модели
  доступа;
- появится необходимость показывать сырые отчёты или интерактивные артефакты;
- support policy перестанет быть общей для provider releases;
- API потребует breaking change вместо аддитивной проекции;
- объём evidence потребует отдельного аналитического read-store, а не
  transactional projection.
