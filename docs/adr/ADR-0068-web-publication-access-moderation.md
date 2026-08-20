---
description: "Решение о web owner-read models и безопасных потоках публикации, прав и модерации."
last_verified: "2026-08-08"
---

# ADR-0068: Веб собственных объектов, публикации, прав и модерации

Статус: принято.

## Контекст

`ADR-0018` отдал вебу управление аккаунтом и публикацией, но оставил создание
паспортов, индексирование, сборку, проверки и установку за CLI и агентом.
`ADR-0043` выбрал RSC, Server Actions и generated OpenAPI client, а `ADR-0041`
зафиксировал server session и double-submit CSRF. `#181` материализовал серверные
сценарии publication, grants, reports и staff actions по `ADR-0067`.

После этого в `apps/web` уже есть landing, публичный каталог, вход, аккаунт и
устройства, но нет owner workspace. Кроме того, существующие API write-paths не
составляют достаточной и безопасной read-поверхности: анонимный catalog намеренно
не видит закрытые объекты, `sync` — журнал ревизий для клиента CLI, а маршруты
staff не дают рабочего списка. Попытка собрать экран в браузере из этих источников
дублировала бы политику видимости, раскрывала бы закрытые метаданные и превращала Zustand в
неверный источник истины.

Есть отдельная угроза invitation accept: wire-контракт требует одноразовый token,
но query/path, server-rendered page, referrer, browser history и telemetry не
должны получить его. Обычная Server Action принимает form data на сервере, поэтому
она не подходит как безусловный транспорт для сырого invitation token.

## Варианты

1. Построить экраны на публичном catalog, локальном `sync` ledger и уже имеющихся
   write-маршрутах. Быстро, но private owner data неполна, policy дублируется на
   клиенте, а sync получает не принадлежащую ему роль web read model.
2. Добавить в `apps/web` отдельный BFF/GraphQL, который агрегирует database и API.
   Даёт удобные экраны, но вводит вторую авторизацию, второй DTO-contract и второй
   application layer вопреки `ADR-0018` и `ADR-0043`.
3. Расширить `/v1` минимальными account-scoped owner/staff read-моделями в
   `packages/contracts`, использовать RSC и Server Actions для обычных мутаций, а
   invitation token передавать только fragment-to-same-origin POST.

## Решение

Принимается вариант 3.

### 1. Owner workspace читает отдельные server read-модели

`#183` вводит web owner workspace для собственных объектов и точных версий,
publication plan, invitations/grants, своих reports и минимальных staff cases.
Нужные owner/staff read-модели проектируются сначала в `packages/contracts`,
fixtures и OpenAPI, затем реализуются вертикальными API-слайсами `ADR-0037` и
только после этого попадают в generated client `apps/web`.

Каждая server read-модель проверяет владельца, действующий grant или staff allowlist
на сервере. Она возвращает только сведения, нужные экрану, а не полный паспорт,
журнал ревизий, ключ хранилища, исходное attestation или закрытые bytes. Публичный
catalog, grant и owner views могут указывать на одну точную версию, но не
взаимозаменяемы и не сливаются клиентом.

Точные маршруты, поля, cursor и ошибки не фиксируются этой записью: ими владеют
`packages/contracts`, `schemas/v1/openapi.json` и `docs/contracts/http-api.md`.
Изменение остаётся аддитивным внутри поддерживаемой основной версии API.

### 2. Один API и server truth

RSC читает owner/staff data на сервере после проверки server session. Обычные
мутации — создание и подтверждение publication plan, выдача и отзыв приглашения,
жалоба и staff action — идут через тонкие Next Server Actions с существующим CSRF
transport; после ответа они invalidируют и перечитывают server view. Zustand хранит
только короткое UI-состояние, не permission, lifecycle, grant или публикационную
истину.

Клиент не вычисляет пригодность к установке, линию доверия, переход жизненного
цикла, доступ к закрытому object или разрешение staff. Он показывает типизированный
результат общего `/v1` scenario, который также доступен CLI, и отображает
возвращённые request/operation IDs. Это сохраняет запрет второй бизнес-логики
`ADR-0018`.

### 3. Invitation token: fragment и прямой POST

Письмо ведёт на локализованную invitation page с идентификатором invitation и raw
token только в URL fragment. Fragment не отправляется HTTP-серверу, не попадает в
referrer и не сохраняется в history как query/path. Точечный client component
считывает fragment, держит token только в памяти и отправляет его прямым
same-origin `POST /v1` с credentials и double-submit CSRF header. После отправки
он удаляет fragment через `history.replaceState` и показывает server outcome.

Это исключение из предпочтения Server Actions является записанной transport-причиной
безопасности по `SPEC-010` `REQ-1011`. Компонент не проверяет token, email, expiry
или grant; это остаётся единым API scenario. Token никогда не передаётся в RSC props,
Server Action, путь, параметры запроса, журналы, аналитику, уведомление, audit или
постоянное хранилище браузера.

### 4. Минимальная модерация не является клиентской ролью

Staff navigation допустима как удобство, но не является границей доступа. Staff
рабочий список, карточку и mutations возвращает API только account из server allowlist
`SPEC-026`; web не держит список staff и не пытается различить отсутствие case от
закрытого case для не-staff. Рабочий список ограничен триажем, lifecycle actions и
`author_verified`; полный RBAC, поиск всех аккаунтов, организация и универсальный
audit explorer не вводятся.

Каждое staff-действие требует явного подтверждения и reason, а сервер пишет
append-only audit. UI показывает безопасную корреляцию действия, но не копирует
audit в самостоятельное клиентское хранилище. Личность репортёра и security details
остаются в границах `SPEC-016` / `ADR-0031`.

## Последствия

- Появляется `SPEC-027` с требованиями веб-слоя и исполнимыми критериями;
  продуктовые правила `SPEC-002`, `SPEC-007`, `SPEC-016` и server materialization
  `SPEC-026` не переписываются.
- До экранов добавляются аддитивные owner/staff read-модели, fixtures, OpenAPI и
  generated client; `apps/web` не получает ручные DTO, BFF или доступ к database.
- Новые страницы располагаются в существующем locale-aware App Router и наследуют
  `ru`/`en`, RSC privacy boundary, Server Actions и UI-kit `ADR-0043`.
- Приглашение получает отдельный fragment-only web transport; требуется browser
  test на отсутствие token в URL, referrer, HTML, истории, хранилище и trace.
- Требуются matrix-тесты owner/grantee/outsider/staff, redaction, publication
  states, idempotency, locale/a11y и отсутствие второй бизнес-логики.
- Если API read-модель отсутствует, экран не строит её из sync или public catalog:
  функция остаётся явно недоступной до contract-first реализации.

## Условия пересмотра

Решение пересматривается, если появится доказанная необходимость browser editor,
если необходимая owner read-модель не выражается аддитивным `/v1` контрактом, если
приём invitation нельзя безопасно выполнить same-origin fragment POST, либо если
staff allowlist перерастёт минимальную поверхность и потребует полноценной модели
ролей и делегирования.
