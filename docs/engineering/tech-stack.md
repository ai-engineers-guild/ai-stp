---
description: "Целевой стек MVP и правила выбора зависимостей."
last_verified: "2026-08-05"
---

# Стек

## Приложение

| Область | Выбор |
|---|---|
| Язык | Python 3.12 и 3.14 — обе проверяются в CI |
| Управление зависимостями | uv и один корневой `uv.lock` после bootstrap кода |
| CLI | Click по `ADR-0057`; machine JSON обязателен |
| Ключ устройства и секреты | Ed25519 через `cryptography`; `keyring` с закрытым перечнем доверенных backend'ов по `ADR-0058` |
| Локальный реестр | стандартный `sqlite3` с WAL и собственным раннером миграций по `ADR-0059`; Alembic и SQLAlchemy не используются в CLI |
| Облачный клиент CLI | `httpx` с ограниченными таймаутами и повторами; транспорт — часть `Endpoint`, поэтому мок из #71 и реальный сервер идут одним путём |
| Схемы | Pydantic 2; JSON Schema и OpenAPI 3.1 генерируются из моделей |
| API | FastAPI |
| Server DB | PostgreSQL |
| Local DB | SQLite |
| ORM/migrations | SQLAlchemy 2, Alembic |
| Worker | PostgreSQL-backed queue |
| Object storage | RustFS/S3 |
| HTTP | httpx |
| Frontend | Next.js App Router (React, RSC + Server Actions) по `ADR-0043`; TypeScript 7 как typecheck + боковой TS6 для `typescript-eslint`; Tailwind 4 с токенизированной темой (светлая/тёмная); двуязычие `next-intl`; стандартный `shadcn/ui` + Radix по atomic design (atoms/molecules/organisms/layouts); типизированный клиент из `schemas/v1/openapi.json` через `@hey-api/openapi-ts`; клиентский стор `zustand`; формы `react-hook-form` + `zod`; линт ESLint flat config (type-aware, полный запрет `any`); тесты Vitest + Testing Library + Playwright + MSW; менеджер пакетов `bun` с `bun.lock` в отдельном Node-workspace `apps/web` |
| Email | Resend |
| Format/lint | Ruff |
| Types | Pyright strict |
| Tests | pytest, Hypothesis, contract/golden/integration |
| Docs | MkDocs, Markdownlint, Mermaid |

`keyring` и `cryptography` входят в зависимости `apps/cli` по `ADR-0058`. `keyring` импортируется лениво: его импорт стоит около 100 мс — втрое дороже Click, — а большинство вызовов не открывает хранилище. Выбранный им backend принимается только из закрытого перечня: измерено, что с установленным `keyrings.alt` побеждает `PlaintextKeyring`, запись молча проходит, и секрет ложится на диск в base64, пока библиотека сообщает об успехе.

Схемы и документ OpenAPI не пишутся руками: единственным источником являются модели `packages/contracts`, а `just back-gen` порождает из них оба артефакта. Рукописный OpenAPI рядом с генерируемыми схемами был бы вторым источником истины, что запрещает `SPEC-015` REQ-1508. Валидация документа выполняется `openapi-spec-validator` в группе `dev`; `httpx` нужен только клиентской стороне и вынесен в необязательную зависимость `ai-stp-contracts[mock]`.

Python workspace создан: корневой `pyproject.toml` с единственным `uv.lock` — источник истины всех Python-зависимостей. Документационные инструменты живут группой `docs`, инструменты разработки — группой `dev`; временный `docs_scripts/requirements.lock.txt` удалён тем же изменением. Node-инструменты закреплены в `docs_scripts/bun.lock`: один менеджер пакетов на язык, `npm` не вызывается. Два активных Python source of truth не допускаются.

## Индекс проекта

- manifests и lockfiles;
- tree-sitter для структуры, где оправдано;
- LSP adapters для Python, TypeScript/JavaScript, Rust, Go и Dart/Flutter;
- parsers информационных форматов и обобщённый разбор ограниченного безопасного текста;
- локальный поиск средствами SQLite без отдельного поискового сервиса;
- embeddings и векторное хранилище отсутствуют в MVP.

## Набор инструментов

Первичная настройка ставит один полный профиль `mvp-full` по `ADR-0019`. Состав задаётся версионируемой политикой, а не текущим содержимым проекта; конкретные версии выбираются из поддерживаемых манифестов на этапе реализации.

## Правила зависимостей

- новая dependency закрывает конкретный gap;
- версия и transitive resolution закрепляются;
- внешние executable tools не смешиваются в одном Python environment;
- provider-specific dependency живёт в adapter/provider;
- собственный build backend не создаётся без доказанной необходимости;
- клиент интерфейса модели не входит в зависимости MVP по `ADR-0022`;
- APM/SX не являются обязательными dependencies.
