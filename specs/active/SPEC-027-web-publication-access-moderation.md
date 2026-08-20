---
description: "SPEC-027: Веб собственных объектов, публикации, прав, жалоб и минимальной модерации."
last_verified: "2026-08-08"
---

# SPEC-027: Веб собственных объектов, публикации, прав, жалоб и модерации

## Цель

`apps/web` даёт владельцу аккаунта безопасную авторизованную поверхность для
просмотра синхронизированных собственных объектов и их версий, подтверждения
серверного плана публикации, управления приглашениями и правами, создания и
отслеживания собственных жалоб, а platform staff — для минимального триажа и
аудируемых действий. Веб показывает серверную истину и вызывает единые сценарии
`/v1`; он не создаёт паспорт, не индексирует проект, не собирает сетап, не
исполняет проверку и не устанавливает объект.

Серверные правила публикации, grants, жалоб и staff принадлежат `SPEC-002`,
`SPEC-007`, `SPEC-016`, `SPEC-026` и их контрактам. Эта спецификация владеет
поведением веб-клиента и требованиями `REQ-27xx`.

## Границы

Входят: защищённые страницы собственных объектов и точных версий; отображение
состояния publication plan и подтверждение точного плана; owned invitations и
grants, их создание, принятие и отзыв; создание жалобы с предпросмотром и список
собственных случаев; минимальный staff worklist, триаж, lifecycle-действия и
выдача или отзыв `author_verified`; двуязычие, доступность, обработка типизированных
ошибок, защита приватных данных и отображение идентификаторов операций.

Не входят: браузерное создание или изменение паспортов, загрузка произвольных
артефактов, индексирование, подбор, сборка, проверки, установка, форк, синхронизация
как клиентский процесс, полный RBAC, организации, платежи, публичные обсуждения,
автоматическая блокировка по числу жалоб, удалённое отключение target, редактор
сетапов, отдельный BFF и ручные DTO. Веб не показывает полный паспорт устройства,
секреты, raw token приглашения, сырые attestations, закрытые байты или личность
репортёра за пределами разрешённой staff-поверхности.

Точные поля, параметры, маршруты и коды ответов принадлежат `packages/contracts`
и сгенерированному `schemas/v1/openapi.json`; смысл заголовков, cursor,
идемпотентности и конкуренции — `docs/contracts/http-api.md`. Дополнительные
авторизованные owner/staff read-модели, нужные этой поверхности, сначала вводятся
аддитивно в контракт и API, затем клиент генерируется заново. Веб не получает их,
собирая приватное состояние из `sync`-событий, публичного каталога или client store.

## Термины

- **Owner workspace** — авторизованная веб-поверхность текущего аккаунта, а не
  публичная проекция каталога.
- **Owner read model** — ограниченная server-side проекция собственных объектов,
  версий и их доступных действий; она не является паспортом и не даёт записи в
  объект.
- **Publication review** — показ неизменяемого `PublicationPlan`, его digest,
  effects, evidence, срока и состояния до отдельного подтверждения.
- **Grant inbox** — список invitations и grants, доступных текущему аккаунту по
  серверной авторизации; он не раскрывает существование других аккаунтов.
- **Staff worklist** — минимальная разрешённая проекция ожидающих cases и их
  контекста для account из server-side allowlist; это не клиентская роль.

## Требования

### Доступ и чтение собственных объектов

- `REQ-2701`: Каждый маршрут owner workspace и staff worklist читает серверную
  сессию до рендеринга. Неаутентифицированный пользователь перенаправляется без
  включения закрытых данных в HTML, RSC payload или клиентский bundle; клиентское
  состояние не является доказательством полномочия.
- `REQ-2702`: Owner workspace показывает только server-authorized owner read model
  текущего account: собственные private/public drafts, объекты и точные версии;
  полученный grant не превращает пользователя во владельца и не даёт запись в
  оригинал. Пагинация и порядок следуют непрозрачному cursor API.
- `REQ-2703`: Карточка собственной точной версии показывает доступные серверные
  факты о lifecycle, точном digest, публикации, двух независимых осях
  `author_verified` / `component_verified`, пригодности к новым установкам и
  evidence. Она различает platform execution и `author_attested`, не называет
  warning успехом и не выводит безопасность из author verification.
- `REQ-2704`: При отсутствии, сокрытии, отзыве права или недостатке полномочия веб
  показывает единый безопасный результат `not found` / permission denied,
  определённый API, без существования чужого private object, случая или staff
  worklist. Он не подменяет отказ данными из старого client cache.

### Публикация и её состояние

- `REQ-2705`: Начать publication review можно только для точной server-authorized
  версии, подготовленной CLI и доступной owner read model. Веб передаёт в единый
  publication scenario только контрактный intent и не формирует, не исправляет и
  не подписывает паспорт, digest, evidence или attestation.
- `REQ-2706`: Перед confirm веб показывает `plan_hash`, точные object/version/digest,
  policy version, effects, срок действия, состояние и доступные evidence
  `PublicationPlan`. Подтверждение требует явного действия пользователя; скрытая
  отправка при переходе страницы, повторном рендеринге или автоматическом retry
  запрещена.
- `REQ-2707`: Confirm отправляет новый idempotency key для одного логического
  пользовательского действия и повторяет его только после неопределённого
  транспортного результата. Веб показывает server-returned `operation_id` там, где
  он выдан, но не генерирует и не имитирует успешный результат.
- `REQ-2708`: После confirm публикация остаётся в наблюдаемом серверном состоянии.
  Веб перечитывает plan через ограниченное ожидание или явное обновление и честно
  показывает `validating`, `publish_planned`, `published`, `failed`, `stale`,
  истечение и отмену. Клиент не объявляет published до server response и не
  запускает validation/publish job сам.
- `REQ-2709`: `stale`, истёкший plan, изменённый digest, недействительное evidence
  и конфликт идемпотентности требуют нового либо перечитанного server plan. Веб
  сохраняет безопасный контекст выбора для повторного просмотра, но не переносит
  прежнее согласие на другой `plan_hash`.
- `REQ-2710`: Веб явно объясняет последствия lifecycle и evidence: потеря
  install eligibility блокирует только новые установки и обновления, а не удалённо
  отключает установленный target. Только server action staff может изменить
  `blocked` / `hidden` / restore; кнопка публикации не является таким действием.
- `REQ-2711`: Публичная и owner-карточки используют один порождённый типизированный
  клиент и server read models. Страница не добавляет отдельную политику видимости,
  доверия или расчёта пригодности и не читает ключ object store.

### Приглашения и права

- `REQ-2712`: Owner видит свои invitations и grants в server-authorized списке с
  объектом, major-линией, состоянием и допустимыми действиями. Создание invitation
  использует нормализованный email только как ввод API; одинаковый успех для
  зарегистрированного и незарегистрированного адреса не дополняется вебом
  диагностикой, подсказкой или различающим timing.
- `REQ-2713`: Создание, отзыв invitation и отзыв grant требуют явного подтверждения,
  reason только в разрешённой форме и idempotency key. Перед отзывом веб сообщает,
  что уже полученные байты, локальные форки и установленные targets не удаляются;
  после успеха он обновляет view серверным ответом, а не оптимистичной догадкой.
- `REQ-2714`: Принятие invitation доступно только авторизованному получателю.
  `Raw token` живёт кратко в памяти страницы и передаётся только в защищённом POST
  к общему API; он не помещается в путь, параметры запроса, серверный HTML,
  `referrer`, журналы, аналитику, уведомления, `audit payload`, хранилище браузера
  или историю. До `accept` invitation не показывается как grant и не открывает object.
- `REQ-2715`: Web UI не позволяет получателю изменять original object, выдавать
  право третьему лицу или считать grant доступом к следующей major-линии. Принятие,
  истечение, отзыв, неподтверждённый email и чужой token показываются только через
  типизированный безопасный ответ API.

### Жалобы и минимальная модерация

- `REQ-2716`: Жалоба из public или owner version page создаёт тот же `ReportCase`
  scenario, что и CLI. Точная object/version/digest берутся из показанной server
  версии; веб не принимает произвольный object id как доказательство доступа и не
  создаёт public GitHub issue.
- `REQ-2717`: Если пользователь добавляет diagnostics, форма ограничивает их
  контрактным размером, очищает доступные пути до относительных, показывает полный
  отправляемый preview и требует отдельное согласие после preview. Секреты,
  `.env`, исходный код, закрытые bytes, OAuth/session/invitation tokens и полные
  домашние пути не подставляются автоматически; текст не сохраняется в persistent
  browser storage.
- `REQ-2718`: После submit веб показывает только собственный `ReportCase` и его
  разрешённое состояние. Повтор с тем же idempotency key отображает тот же case;
  rate limit, недоступность и неопределённый transport result не создают ложный
  success. Подготовленная, но неотправленная форма остаётся доступной в памяти
  текущего экрана до явной отмены или ухода пользователя.
- `REQ-2719`: Staff worklist и case detail рендерятся только после server-side
  allowlist authorization. Наличие или отсутствие staff navigation не является
  полномочием: `403` не заменяется client-side ролью, а не-staff не получает число,
  идентификаторы или содержание cases.
- `REQ-2720`: Staff triage, lifecycle action (`block`, `hide`, `restore`) и выдача
  или отзыв `author_verified` требуют явное подтверждение, непустое reason и новый
  idempotency key. Экран показывает server-returned result и `operation_id` /
  request id для проверки аудита; количество жалоб никогда не предлагает и не
  запускает автоматическую блокировку.
- `REQ-2721`: Staff view не раскрывает автору объекта личность, email, diagnostics
  или окружение репортёра. `security_escalated` не попадает в обычные списки и не
  раскрывает детали уязвимости; веб направляет пользователя в безопасный
  server-defined outcome, не создавая публичное обсуждение.

### Качество веб-клиента и совместимость

- `REQ-2722`: Все новые пользовательские строки имеют эквивалентные `ru` и `en`
  сообщения. Формы, tabs, dialogs, статусы ожидания и ошибки доступны с клавиатуры,
  имеют видимый focus, корректные labels/roles и объявляют изменение состояния
  ассистивным технологиям.
- `REQ-2723`: Мутации реализуются Server Actions с CSRF-транспортом `ADR-0041` и
  обновляют RSC view через server truth. Единственное транспортное исключение —
  `accept` invitation по `REQ-2714`: клиентский компонент считывает token из URL
  fragment и отправляет его прямым same-origin POST с double-submit CSRF, не
  реализуя бизнес-правило в браузере.
- `REQ-2724`: Клиент использует только код, сгенерированный из актуального OpenAPI,
  и тонкие boundary adapters без ручных DTO. Новое поле сначала добавляется
  необязательным; unsupported schema, unknown response field и API/version mismatch
  обрабатываются по контракту без unsafe cast и без скрытого fallback.
- `REQ-2725`: Модульные, компонентные, контрактные и браузерные тесты покрывают
  матрицу owner/grantee/outsider/staff, все состояния publication plan, invitation
  fragment, очистку данных, предпросмотр жалобы, staff confirmation, паритет
  локалей и a11y. Тесты не используют реальные OAuth, Resend, object storage или
  browser secrets и не фиксируют токены, email или приватные bytes в снимках,
  трассах и fixtures.

## Состояния и ошибки

Состояния `publication plan`, `validation`, `invitation`, `grant`, `case` и
`lifecycle`
принадлежат `packages/contracts`, `SPEC-002`, `SPEC-007`, `SPEC-016` и `SPEC-026`.
Веб отображает их как server-provided values и не изобретает локальных переходов.
`AI_STP_AUTH_REQUIRED` переводит защищённый экран в logout; `AI_STP_DEVICE_REVOKED`
не даёт мутировать publication paths; `AI_STP_PERMISSION_DENIED` и
`AI_STP_NOT_FOUND` не раскрывают private resource; `AI_STP_PLAN_STALE`,
`AI_STP_PRECONDITION_FAILED`, `AI_STP_CONFLICT`, `AI_STP_RATE_LIMITED` и
`AI_STP_DEPENDENCY_UNAVAILABLE` имеют разные наблюдаемые сообщения и действия
повтора. Секретные значения не попадают в отображаемую ошибку.

## Безопасность и приватность

`Server session`, API authorization, CSRF и `transport cookie` наследуются из
`ADR-0041`; веб не хранит provider token или session token. Приватные RSC данные
не сериализуются в client props без необходимости, и после logout, revoke или
отказа в полномочии защищённое представление invalidируется. Действия с publication, grant,
report и staff используют server-issued IDs и idempotency; raw invitation token,
attestation signature, секреты, emails за разрешённой формой и закрытые bytes не
попадают в URL, хранилище браузера, телеметрию, журналы, audit или локализованные
сообщения.

## Совместимость и миграция

Перед реализацией owner/staff экранов контракт получает аддитивные read-модели и
соответствующие fixtures/OpenAPI. Существующие public catalog и CLI clients остаются
совместимыми; private fields не добавляются в анонимные responses. После обновления
контракта выполняется `api:generate`; generated client не правится вручную. Если
сервер ещё не поддерживает требуемую read model, веб показывает только явную
недоступность функции и не подменяет её sync-данными.

## Критерии приёмки

| Требование | Исполнимый способ проверки |
| --- | --- |
| `REQ-2701` | RSC/browser test проверяет redirect без protected HTML и client payload. |
| `REQ-2702` | Contract/API/browser matrix отделяет owner, grantee и outsider в list/detail. |
| `REQ-2703` | Component golden различает обе оси verification, evidence source и eligibility. |
| `REQ-2704` | Negative test не раскрывает private object/case через route, cursor или cache. |
| `REQ-2705` | Contract test отвергает publication intent, сформированный не из owner version. |
| `REQ-2706` | Browser test требует явный confirm после отображения digest, effects и expiry. |
| `REQ-2707` | Lost-response test повторяет один key и показывает один server operation. |
| `REQ-2708` | Mock/API scenario покрывает каждый terminal и transitional plan state. |
| `REQ-2709` | Stale plan test требует fresh plan и не переносит prior consent. |
| `REQ-2710` | UI test отличает eligibility warning от staff lifecycle action. |
| `REQ-2711` | Static/contract test исключает ручной trust policy и storage-key access. |
| `REQ-2712` | Known/unknown email tests имеют неотличимые web-visible result и timing budget. |
| `REQ-2713` | Dialog and API test подтверждают warning и server-truth refresh после revoke. |
| `REQ-2714` | Browser trace/history/source test не находит token вне fragment и POST body. |
| `REQ-2715` | Authz matrix запрещает re-grant, original write и next-major access. |
| `REQ-2716` | Contract test доказывает общий web/CLI report scenario без GitHub issue. |
| `REQ-2717` | Form test требует preview/consent и не находит sensitive fixture text в storage. |
| `REQ-2718` | Retry/rate-limit test сохраняет draft in-memory и не показывает false success. |
| `REQ-2719` | Non-staff browser/API test не получает staff route data, count или case ID. |
| `REQ-2720` | Staff scenario требует reason/confirm и проверяет audit correlation identifier. |
| `REQ-2721` | Redaction test скрывает reporter data and security case details from author/list. |
| `REQ-2722` | Locale and axe tests покрывают все routes, forms and dialogs in `ru` and `en`. |
| `REQ-2723` | Architecture test проверяет Server Actions и fragment-only accept exception. |
| `REQ-2724` | Generated-client gate and typecheck reject manual DTO/unsafe cast drift. |
| `REQ-2725` | CI inventory links every requirement to deterministic web/API test evidence. |
