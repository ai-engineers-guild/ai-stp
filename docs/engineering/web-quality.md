---
description: "Эксплуатационные правила web: SEO, machine discovery, browser storage, selectors и quality gates."
last_verified: "2026-08-29"
---

# Качество web-поверхности

## Human и Machine

Human и Machine являются двумя режимами отображения одной серверной истины. Human использует светлую читаемую подачу. Machine использует отдельную тёмную техническую проекцию: текстовый индекс сайта, Markdown-подобные заголовки, ссылки с видимыми URL и отсутствие декоративных медиа. Формы, маршруты, данные и серверная авторизация остаются теми же. Переключатель хранит только строку `light` или `dark` под ключом `ai_stp_display_mode`; доменные данные и права от режима не зависят.

## Machine discovery и SEO

Публичная поверхность отдаёт `robots.txt`, `sitemap.xml`, web manifest, locale-aware metadata, Open Graph и Twitter summary. Для LLM-клиентов доступны `/llms.txt`, `/llms-full.txt` и `/agents.md`. Эти файлы являются навигацией и кратким контекстом, но не вторым контрактом: поля и перечисления принадлежат `docs/contracts/` и `schemas/v1/`.

Приватные маршруты запрещены в `robots.txt` и не включаются в sitemap. Это не является security boundary: авторизация и отсутствие приватных данных в HTML обеспечиваются сервером.

## Cookies и browser storage

- `ai_stp_session` — подписанная или серверная opaque session, `HttpOnly`, `SameSite=Lax`, `Secure` в production.
- `ai_stp_csrf` — читаемый браузером double-submit token, `SameSite=Lax`, `Secure` в production; доменные данные в нём отсутствуют.
- `sessionStorage` применяется только для временного preview публичного профиля внутри вкладки.
- `localStorage` применяется только библиотекой темы для `ai_stp_display_mode`.
- Хранить секреты, токены OAuth, закрытые ключи и закрытые метаданные объектов в браузерных хранилищах запрещено.

## Стабильные selectors

Единый каталог находится в `apps/web/src/lib/ui-selectors.ts`. Значения используются через `data-ui`; классы и локализованный текст не являются API для browser tests. Реальные `id` остаются у landmarks, form controls и anchor targets, где они нужны семантике HTML. Новое значение selector должно быть уникальным, читаемым и пройти `apps/web/tests/unit/ui-selectors.test.ts`.

## Клавиатура, touch и motion

- Интерактивные элементы в компактном mobile header сохраняют hit-area не меньше `44×44px`, даже если подпись скрыта ради ширины; доступное имя остаётся через `aria-label`.
- Глобальные shortcuts `C`, `P` и `Ctrl+K`/`Cmd+K` не срабатывают при вводе в `input`, `textarea`, `select` или `contenteditable`. Однобуквенные shortcuts также игнорируются с модификаторами.
- При `prefers-reduced-motion: reduce` непрерывные и декоративные animation останавливаются, а переходы сокращаются без отключения видимых focus, hover и state changes.

## Quality gates

Из `apps/web` выполняются `bun run lint`, `bun run type-check`, `bun run test`, `bun run build`, `bun run test:e2e` и `bun run audit`. Визуальная проверка включает desktop/mobile, клавиатуру, reduced motion и отсутствие перекрытия footer. Lighthouse запускается против production build, а не dev server.
