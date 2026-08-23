---
description: "Категории cookies и правило запуска необязательных интеграций Web."
last_verified: "2026-08-22"
---

# Web cookie consent

| Cookie или storage | Категория | Назначение | До согласия |
| --- | --- | --- | --- |
| server session | necessary | Аутентифицированная сессия | разрешён |
| CSRF token | necessary | Защита изменяющих запросов | разрешён |
| `ai_stp_consent` | necessary | Сохранённый выбор категорий | разрешён |
| analytics integration | analytics | Агрегированные продуктовые метрики | запрещён |
| marketing integration | marketing | Будущие маркетинговые интеграции | запрещён |

Отклонение необязательных категорий не удаляет и не отключает necessary cookies.
Analytics и marketing не загружаются до положительного выбора и не записывают
cookies или localStorage при отказе. Google Analytics (`@next/third-parties`) и
официальный счётчик Яндекс Метрики `https://mc.yandex.ru/metrika/tag.js`
подключаются только после согласия с категорией analytics и только при заданных
`NEXT_PUBLIC_GA_MEASUREMENT_ID` / `NEXT_PUBLIC_YANDEX_METRIKA_COUNTER_ID`
(пустой идентификатор — этот вендор выключен). `NEXT_PUBLIC_ANALYTICS_ENABLED=false`
выключает оба счётчика даже при заданных id. Баннер можно отключить для
deployment без tracking через `NEXT_PUBLIC_COOKIE_CONSENT_ENABLED=false`; это не
включает необязательные интеграции автоматически.

Server-side detail/download counters по `catalog-usage-metrics.md` относятся к
necessary anti-abuse: они не ставят cookie, не запускают browser tracker и не
требуют analytics consent. Это не разрешает cohort analytics или стабильный
visitor identifier.
