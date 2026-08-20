---
description: "SPEC-048: Быстрый RSC-каталог, явные public/private fetch boundaries и управляемый prefetch."
last_verified: "2026-08-15"
---

# SPEC-048: Web RSC cache and fetch boundaries

## Цель

Ускорить публичный web-каталог и устранить устаревшие либо лишние RSC-переходы:
публичные данные получают короткий ограниченный кэш, приватные запросы остаются
строго request-scoped, независимые загрузки выполняются параллельно, а router
prefetch не создаёт тяжёлые RSC-запросы без явной пользовательской пользы.

## Границы

Входит issue #354:

- удаление общего `force-dynamic` из locale layout;
- явное разделение public и private server API helpers;
- короткий кэш `fetch` в Next.js для анонимных чтений каталога;
- параллельная загрузка независимых catalog resources и publisher profiles;
- отключение лишнего prefetch для тяжёлых, приватных и высококардинальных ссылок;
- регрессионные тесты для политики кэша, изоляции сессии, параллелизма и навигации.

Не входит изменение API schemas, доменной свежести catalog records, CDN policy,
редизайн каталога, новый client-side data layer или ослабление authorization.

## Термины

- **Public fetch** — server-side GET к документированному анонимному endpoint,
  который не читает cookies, не пересылает session/CSRF и допускает общий cache.
- **Private fetch** — запрос, зависящий от account/session либо изменяющий данные;
  он всегда выполняется с `no-store` и никогда не разделяется между запросами.
- **Короткий catalog cache** — ограниченный `revalidate` для публичных catalog
  reads; точное значение задаётся одной именованной константой и покрывается тестом.
- **Тяжёлый prefetch** — автоматический RSC-prefetch маршрута, который запускает
  catalog search, private read или другую многоресурсную server-side загрузку.

## Требования

- `REQ-4801`: Общий locale layout не объявляет `dynamic = "force-dynamic"`.
  Request-dependent projection/canonical state изолируется в минимальной
  dynamic boundary так, чтобы публичные страницы сами определяли caching mode.

- `REQ-4802`: Public и private API helpers имеют разные типизированные entrypoints.
  Public helper принимает только `GET`, не вызывает `cookies()`, не принимает
  session token, Cookie, Authorization или CSRF headers. Private helper сохраняет
  request-scoped headers и `cache: "no-store"`; mutation/binary/meta paths остаются private.

- `REQ-4803`: Только подтверждённые анонимные catalog/public-profile GET endpoints
  используют короткий cache через `next.revalidate` и стабильные cache semantics.
  Auth/account/devices/objects/grants/reports/staff и любые mutations не кэшируются.

- `REQ-4804`: Catalog page запускает независимые reads одновременно. Components
  и setups при `resource=all`, external products и последующая пачка уникальных
  publisher profiles не образуют искусственную последовательную waterfall.
  Частичный отказ сохраняет существующую безопасную UI-семантику.

- `REQ-4805`: Явный router prefetch остаётся только для дешёвых, ограниченных и
  вероятных переходов. Ссылки на private pages, high-cardinality object/version
  pages и catalog filter/pagination routes задают `prefetch={false}` либо не
  форсят prefetch согласно одному документированному правилу.

- `REQ-4806`: Cache invalidation после публикации и изменения public presentation
  не обещает мгновенную глобальную консистентность: текущие `revalidatePath`
  сохраняются, а публичная выдача сходится не позднее короткого TTL. Private UI
  после mutation не получает cached response.

- `REQ-4807`: Изменение не создаёт hydration warnings и stale cross-account UI.
  Production build, unit/component tests и browser smoke не содержат новых
  hydration mismatch сообщений; два разных session contexts не разделяют data.

## Состояния и ошибки

- `public_fresh` — public fetch обслужен сетью либо валидным коротким cache;
- `public_revalidating` — истёкший entry обновляется средствами Next.js;
- `public_unavailable` — сохраняется существующий типизированный API/UI error;
- `private_ready` — ответ относится к текущему request/session;
- `private_unauthorized` — сохраняется non-enumeration/auth error без cache fallback.

Public cache не превращает transport failure в успешный пустой каталог. Private
helper не делает fallback на public helper.

## Безопасность и приватность

- Cache key никогда не содержит и cache entry никогда не сохраняет Cookie,
  Authorization, CSRF, account-scoped response или private object existence.
- Public helper отклоняет credential-bearing options на уровне TypeScript API и
  проверяется negative tests.
- Разделение helpers не меняет server-side authorization и non-enumeration.
- Логи и test fixtures не содержат значения session/cookie.

## Совместимость и миграция

Изменение не меняет wire contracts и не требует data migration. Rollout:
сначала вспомогательные функции и тесты политики, затем перевод подтверждённых публичных вызовов,
после этого удаление общего dynamic override, параллелизация и prefetch cleanup.
Rollback возвращает callers на private/no-store helper и общий dynamic rendering;
данные и API остаются совместимыми.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-4801` | Static source test запрещает общий `force-dynamic`; production build успешно собирает public и private route trees. |
| `REQ-4802` | Unit tests доказывают отсутствие `cookies()` и credential headers в public path и `no-store` в private/mutation paths. |
| `REQ-4803` | Fetch-spy tests проверяют единую короткую `revalidate` policy только для allowlisted anonymous endpoints. |
| `REQ-4804` | Deferred-promise test доказывает одновременный старт component/setup/services reads и bounded parallel profile reads. |
| `REQ-4805` | Component/source tests проверяют `prefetch={false}` на тяжёлых/private/high-cardinality ссылках и отсутствие forced prefetch без allowlist. |
| `REQ-4806` | Mutation tests сохраняют нужные `revalidatePath`; cache-policy test фиксирует TTL convergence и private no-store. |
| `REQ-4807` | `just web-check` и browser smoke каталога/login-account переходов проходят без hydration mismatch; isolation test использует два session contexts. |
