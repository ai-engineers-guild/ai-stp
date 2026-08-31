---
description: "ADR-0095: Разделить public cacheable и private request-scoped web fetch policy."
last_verified: "2026-08-31"
---

# ADR-0095: Split public and private web fetch policy

Статус: принято. Реализовано отдельными public/private HTTP clients и cache tests.

## Контекст

Locale layout принудительно делает всё дерево dynamic. Одновременно общий
`apiRequest` читает `cookies()` и ставит `cache: "no-store"` даже для анонимного
каталога. Это не позволяет Next.js безопасно кэшировать публичные RSC reads,
создаёт лишнюю server work на navigation и смешивает две разные trust boundaries.
Catalog page дополнительно содержит последовательные независимые загрузки, а
явный prefetch запускает дорогие RSC routes до намерения пользователя.

## Варианты

1. Оставить единый helper и добавить флаг `public/cache`. Изменение компактно,
   но default легко выбрать неверно, а credential-bearing options остаются рядом
   с shared cache и делают ошибку приватности слишком дешёвой.
2. Кэшировать весь locale tree. Это даёт высокий hit rate, но несовместимо с
   request-dependent projection и private routes.
3. Разделить типизированные точки входа и кэшировать только подтверждённые публичные GET-вызовы,
   оставив dynamic state в минимальных boundaries. Больше явного кода, зато
   cacheability и credential boundary становятся проверяемыми.

## Решение

Выбран вариант 3.

- Ввести отдельный public GET helper без доступа к cookies/session и отдельный
  private request helper с `no-store`.
- Public helper использует одну короткую именованную `revalidate` policy только
  для подтверждённых anonymous catalog/public-profile callers. Не применять
  cache к private, mutation, binary и operation-meta paths.
- Удалить общий `force-dynamic`; projection/canonical request state оставить в
  минимальной динамической границе, не заражающей caching policy data pages.
- Параллелить независимые catalog reads; fan-out publisher profiles ограничить
  уникальными IDs и контролируемым параллелизмом/дедупликацией.
- Не форсировать prefetch тяжёлых, приватных и высококардинальных routes. Явный
  prefetch разрешён только для небольшого стабильного navigation allowlist.

## Последствия

Публичный каталог может быть устаревшим не дольше принятого короткого TTL;
`revalidatePath` после public mutations остаётся ускоренным convergence path.
Private UI остаётся request-scoped. Новые public endpoints должны явно пройти
проверку приватности перед использованием public helper. Тесты обязаны фиксировать
список разрешённых путей, TTL, отсутствие учётных данных, параллелизм и вывод гидратации.

Миграция данных не требуется. Rollback состоит в возврате public callers на
private/no-store helper и dynamic override; wire contracts не меняются.

## Условия пересмотра

Решение пересматривается, если API добавит персонализированный catalog response,
Next.js изменит cache/dynamic semantics используемой runtime baseline, появится
tag-based invalidation contract либо измерения покажут, что выбранный TTL нарушает
product freshness SLO.
