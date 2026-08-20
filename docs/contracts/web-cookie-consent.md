---
description: "Категории cookies и правило запуска необязательных интеграций Web."
last_verified: "2026-08-16"
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
cookies или localStorage при отказе. Баннер можно отключить для deployment без
tracking через `NEXT_PUBLIC_COOKIE_CONSENT_ENABLED=false`; это не включает
необязательные интеграции автоматически.

Server-side detail/download counters по `catalog-usage-metrics.md` относятся к
necessary anti-abuse: они не ставят cookie, не запускают browser tracker и не
требуют analytics consent. Это не разрешает cohort analytics или стабильный
visitor identifier.
