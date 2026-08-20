---
description: "Правила Python, Node, external tools и provider dependencies."
last_verified: "2026-08-15"
---

# Политика зависимостей

Новая dependency требует конкретный capability gap, основной источник и владельца выпуска, закреплённую версию и lock, проверку лицензии и безопасности, поддержку платформ, модель timeout и failure, тест, владельца обновлений и план удаления или замены.

Внешний LSP, scanner или tool устанавливается в изолированный набор инструментов и запускается по точному пути. Сценарии установки пакета отключаются, если их необходимость не доказана.

Источник Git закрепляется точным commit. Зависимость из реестра пакетов имеет точную версию и проверку целостности. Произвольный URL запрещён.

## Одобренные зависимости `apps/api` (issue #80, ADR-0041)

Каждая запись ниже является sign-off на добавление в `apps/api/pyproject.toml` и корневой `uv.lock`. Точная версия закрепляется lock-файлом при `uv lock` / `uv sync`.

### authlib

| Поле | Значение |
|---|---|
| Capability gap | OAuth 2.0 / OIDC client для Google и GitHub: authorize redirect, token exchange, PKCE `S256`, привязка `state` к инициировавшей сессии (`RFC 6749 §10.12`). Без библиотеки пришлось бы вручную реализовать CSRF/`state`/PKCE. |
| Источник | PyPI `authlib`; основной upstream — <https://github.com/authlib/authlib>. Владелец выпуска — maintainers Authlib. |
| Версия | `>=1.6.6` (CSRF-фикс для state в кэше); pin в lock на актуальную 1.7.x при добавлении. |
| Лицензия / security | BSD-3-Clause. Следить за advisory GitHub/PyPI; минимальная 1.6.6 обязательна. |
| Платформы | Pure Python; Python 3.10–3.14; Windows / Linux / macOS. |
| Timeout / failure | HTTP к провайдеру через httpx с таймаутом клиента; сбой обмена токена → типизированная `AI_STP_AUTH_REQUIRED` / `AI_STP_DEPENDENCY_UNAVAILABLE` без утечки секретов. |
| Тест | OAuth callback/link/conflict/replay; state/PKCE negatives (`SPEC-002` REQ-202/203). |
| Владелец обновлений | platform / `apps/api`. |
| План удаления | Заменить на другой OAuth client только новым ADR; удалить `slices/auth` OAuth-адаптер и зависимость после миграции. |

### cryptography

| Поле | Значение |
|---|---|
| Capability gap | Проверка Ed25519-подписи устройства на сервере (`Ed25519PublicKey.verify`), включая авторское подтверждение публикации. Собственная реализация криптопримитивов запрещена. |
| Источник | PyPI `cryptography`; upstream <https://github.com/pyca/cryptography>. Владелец выпуска — Python Cryptographic Authority. |
| Версия | Актуальная стабильная (50.x) закрепляется в lock. |
| Лицензия / security | Apache-2.0 OR BSD-3-Clause. Критичные advisory закрываются внеочередным bump. |
| Платформы | Колёса для win/linux/macos x86_64 и arm64; Python 3.10+. |
| Timeout / failure | Локальная verify-only операция; неверная подпись → `AI_STP_VALIDATION_ERROR` / отказ регистрации без исключения с ключом в логе. |
| Тест | Регистрация устройства: valid/invalid signature, idempotency, attach-to-other denied (`SPEC-002` REQ-204). Bind attestation: настоящая подпись принимается, `"s" * 16` и чужой ключ отклоняются (`SPEC-026` REQ-2605). |
| Владелец обновлений | platform / `apps/api`. |
| План удаления | Только вместе со сменой схемы device key (параллельное чтение старого/нового формата по SPEC-002); иначе зависимость остаётся. |

### itsdangerous

| Поле | Значение |
|---|---|
| Capability gap | (1) Подпись cookie `SessionMiddleware` Starlette для транзиентного OAuth state; (2) stateless signed nonce challenge устройства с TTL. Без неё SessionMiddleware Starlette всё равно требует пакет, а challenge нуждался бы в таблице и cleanup. |
| Источник | PyPI `itsdangerous`; upstream <https://github.com/pallets/itsdangerous> (Pallets). |
| Версия | 2.2.x закрепляется в lock. |
| Лицензия / security | BSD (OSI Approved). |
| Платформы | Pure Python; все целевые ОС MVP. |
| Timeout / failure | Истёкший или подделанный nonce → отказ регистрации; без side-channel по содержимому секрета. |
| Тест | Challenge freshness, replay of stale nonce, device register path. |
| Владелец обновлений | platform / `apps/api`. |
| План удаления | При отказе от SessionMiddleware и stateless challenge — новый ADR и удаление прямого import; транзитивная нужда Starlette рассматривается отдельно. |

## Одобренные зависимости `apps/web` (issue #82/#83, ADR-0043)

`apps/web` — первое Node-приложение репозитория и отдельное Node-workspace со своим
`package.json` и `bun.lock`, изолированное от корневого `uv.lock`. Менеджер пакетов —
`bun`; точная версия каждого пакета закрепляется `bun.lock` при добавлении. Источник —
npm-реестр с проверкой целостности lock; произвольный URL и Git-источник без точного
commit запрещены (общее правило выше). Каждая строка ниже — sign-off на добавление в
`apps/web/package.json` и `bun.lock` по `ADR-0043`. Владелец обновлений всех строк —
platform / `apps/web`; план удаления любой библиотеки — только новым ADR с заменой,
без правки по месту.

### Runtime

| Пакет | Capability gap | Версия / lock | Лицензия |
|---|---|---|---|
| `next` | App Router, RSC, Server Actions, серверная граница и маршрутизация по `ADR-0043`; фронтенд закреплён `tech-stack.md`. | Актуальная стабильная major; pin в `bun.lock`. | MIT |
| `react`, `react-dom` | Рантайм UI, требуемый Next.js. | Совместимая с выбранным Next.js; pin в lock. | MIT |
| `next-intl` | Двуязычие `ru`/`en` с первого маршрута для App Router/RSC по `ADR-0035` (`REQ-2203`, `REQ-2311`); без неё пришлось бы вручную решать локализованную маршрутизацию и серверные переводы. | Актуальная стабильная; pin в lock. | MIT |
| `@hey-api/openapi-ts` (+ `@hey-api/client-fetch`) | Порождение типов и типизированного клиента из `schemas/v1/openapi.json` (`REQ-2211`); запрещает второй DTO-набор рядом с `#71`. | Как проверено в `jira_timesheet`; pin в lock. | MIT |
| `zustand` | Клиентский стор тонкими слайсами по `ADR-0043` (замена глобального кэша запросов); серверная истина не дублируется на клиенте. | Актуальная стабильная; pin в lock. | MIT |
| `tailwindcss` (4.x) | Стили и токенизированная тема на CSS-переменных по `ADR-0043` (`REQ-2214`); совместим со стандартным `shadcn/ui`. | 4.x; pin в lock. | MIT |
| `class-variance-authority`, `clsx`, `tailwind-merge` | Утилиты вариантов и слияния классов для `shadcn/ui`. | Актуальные стабильные; pin в lock. | MIT |
| `shadcn` (CLI/реестр) + примитивы `radix-ui` | Стандартные доступные компоненты по `ADR-0043`, организованные по atomic design; код компонентов версионируется в `apps/web`, а не тянется как runtime-зависимость. Дополнительные реестры анимаций не добавляются. | Актуальные стабильные; pin в lock. | MIT |
| `react-hook-form`, `@hookform/resolvers`, `zod` | Формы, валидация полей профиля, переменных окружения и внешних данных на границе (`REQ-2201`, `REQ-2303`). | Актуальные стабильные; pin в lock. | MIT |
| `js-yaml`, `@types/js-yaml` | Bounded parsing repository-owned `features.yaml` и Markdown frontmatter по `SPEC-038`; JSON schema отключает implicit timestamps, Zod остаётся окончательной границей. | `js-yaml` 4.3.1, types 4.0.9; exact pin в manifest и lock. | MIT |
| `lucide-react`, `sonner` | Иконки и уведомления безопасной обратной связи (`REQ-2309`). | Актуальные стабильные; pin в lock. | ISC / MIT |

Timeout / failure для runtime-набора: сетевые вызовы идут через порождённый клиент с
ограниченным таймаутом; недоступный API даёт наблюдаемое состояние ошибки
(`REQ-2205`), а не пустую или частичную страницу; секреты и значения токенов в
клиентский код, логи браузера и видимые ошибки не попадают (`ADR-0041`, `ADR-0043`).

### Dev и тесты

| Пакет | Capability gap | Версия / lock | Лицензия |
|---|---|---|---|
| `typescript` (7.x) | Основной typecheck-гейт `apps/web` нативным компилятором в strict-режиме по `ADR-0043`. | 7.x; pin в lock. | Apache-2.0 |
| `typescript` (6.x, боковой) + `typescript-eslint` | Type-aware линт (полный запрет `any`, запрет небезопасного структурного доступа): `typescript-eslint` не работает на TS7 до стабильного API, поэтому TS6 стоит рядом только для линта и удаляется при выходе TS7.1 (`ADR-0043`). | TS6 `>=6.0 <6.1`; pin в lock. | Apache-2.0 / MIT |
| `eslint` (flat config) + `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y`, `eslint-plugin-import` | Линт как гейт: правила React/hooks, доступности, импортных границ atomic-слоёв и запрета god-объектов (`coding-rules.md`, `REQ-2213`). | Актуальные стабильные; pin в lock. | MIT |
| `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom` | Unit и компонентные тесты состояний, темы и доступности (`REQ-2202`, `REQ-2213`, `REQ-2214`). | Актуальные стабильные; pin в lock. | MIT |
| `@playwright/test` | Browser smoke `landing → search → detail` и потоков входа/отзыва (`REQ-2213`, `REQ-2311`). | Актуальная стабильная; pin в lock. | Apache-2.0 |
| `msw` | Mock-first разработка и тесты против фикстур `#71` до готовности `#80`/`#81`. | Актуальная стабильная; pin в lock. | MIT |
| `prettier` | Форматирование фронтенд-кода. | Актуальная стабильная; pin в lock. | MIT |
| `storybook` + `@storybook/react-vite` + `@storybook/addon-essentials` + `@storybook/addon-a11y` + `@storybook/addon-themes` + `vite` + `@vitejs/plugin-react` + `@tailwindcss/vite` | UI kit / design-token Storybook для foundations и atomic компонентов; dev-only, не runtime. Позволяет менять тему (токены) без смешения с product routes. | Storybook 8.x; pin в `bun.lock`. | MIT |

Платформы всего набора: Node LTS на Windows / Linux / macOS через `bun`; тест
`run_conformance`-аналога на стороне веба — контрактный тест происхождения типов из
`schemas/v1/openapi.json`. Тест каждой библиотеки покрыт критериями приёмки `SPEC-022`
и `SPEC-023`.
