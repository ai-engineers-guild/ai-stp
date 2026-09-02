<p align="center">
  <a href="README.md">English</a> · <strong>Русский</strong>
</p>

<p align="center">
  <img src="assets/readme/ru/hero.png" width="100%" alt="ai_stp: соберите, проверьте и установите полный сетап через вашего агента. Пять рук замыкают петлю вокруг знака продукта.">
</p>

<p align="center">
  <a href="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml"><img src="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml/badge.svg?branch=main" alt="check"></a>
  <a href="https://pypi.org/project/ai-stp-cli/"><img src="https://img.shields.io/pypi/v/ai-stp-cli" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="License: AGPL-3.0"></a>
  <a href="https://ai-stp.aiguild.space"><img src="https://img.shields.io/badge/catalog-ai--stp.aiguild.space-black" alt="catalog"></a>
</p>

Проект [AI Engineers Guild](https://github.com/ai-engineers-guild). Первичный
потребитель — **агент** пользователя через строгий машинный CLI. Каждая
команда отвечает одним JSON-конвертом с типизированными ошибками и явными
следующими шагами. Веб владеет учётной записью и публичным каталогом и
показывает результаты. Создание паспортов, индекс, подбор, сборка, проверка и
установка принадлежат CLI и агенту.

<p align="center">
  <img src="assets/readme/shared/kinds.png" width="100%" alt="Восемь видов компонентов в одном сетапе: instruction, skill, mcp, hook, command, agent, plugin, setting.">
</p>

<p align="center">
  <img src="assets/readme/ru/section-what.svg" width="100%" alt="01 Что это">
</p>

**Сетап** — полная конфигурация одного харнесса: `instruction`, `skill`,
`mcp`, `hook`, `command`, `agent`, `plugin` и `setting`. Память, правила и
вспомогательные инструменты живут внутри этих видов. Каждая устанавливаемая
версия привязана к харнессу, версии харнесса, операционной системе, точным
версиям компонентов и результатам проверки.

`ai-stp` не вызывает API модели и не требует ключа модели. Итоговое нативное
состояние харнесса пишет только его публичный **провайдер** — выпущенный и
подписанный исполняемый setup-system. `ai-stp` проверяет граф компонентов,
собирает детерминированный пакет и ведёт провайдера по плану с digest,
резервной копией и откатом. Провайдеры живут в
[NDDev-OpenNetwork](https://github.com/NDDev-OpenNetwork) под своими
лицензиями.

<p align="center">
  <img src="assets/readme/ru/section-how.svg" width="100%" alt="02 Как это работает">
</p>

<p align="center">
  <img src="assets/readme/shared/workflow.svg" width="100%" alt="Жизненный цикл: install, passports, select, plan, apply, restore.">
</p>

```text
установка CLI
→ паспорта разработчика и устройства
→ индекс проекта
→ поиск и сборка сетапа
→ проверки
→ план установки и резервная копия
→ apply через провайдера харнесса
→ проверка состояния; restore при отказе
→ необязательная облачная синхронизация
```

Без аккаунта: локальный реестр, паспорта, индекс проекта, анонимное чтение
публичного каталога, подбор и установка публичных объектов.

После входа через Google или GitHub: облачная копия личного реестра,
приватные объекты, публикация, устройства и их ключи, выдачи доступа и
отчёты.

<p align="center">
  <img src="assets/readme/ru/section-use.svg" width="100%" alt="03 Первый запуск">
</p>

```bash
uv tool install ai-stp-cli
ai-stp doctor --json
```

Затем отдайте агенту машинный реестр:

```bash
ai-stp help --agent --json
ai-stp passport developer init --json
ai-stp device init --json
```

Каждая команда принимает `--json`. Тот же реестр питает человеческую справку.
Исполняемый файл — `ai-stp`; имя дистрибутива — `ai-stp-cli`.

## Поддерживаемые харнессы

| Статус | Харнессы |
|---|---|
| Основная поддержка | Claude Code, Codex, Grok Build |
| Бета | Pi, OpenCode, Cursor, Antigravity |
| ограниченный режим | `undefined` для неизвестного харнесса |

## Стратегическое направление: Rust и plugin-архитектура в духе Pi

**By 31 December 2026, `ai-stp` will be rewritten in Rust and migrated to a
plugin-first architecture inspired by Pi.** The migration will preserve the
public CLI and API contracts while separating a lightweight, deterministic
core from versioned plugins for harnesses, components, projections, and
provider-specific integrations.

## Стадия

Единственный владелец текущего статуса фазы —
[`docs/engineering/implementation-roadmap.md`](docs/engineering/implementation-roadmap.md).
Этот README не копирует его таблицу: CLI, платформа и evidence выпуска
двигаются с разной скоростью, и одно слово «готово» спрятало бы незакрытые
внешние доказательства.

## Разработка

Участники работают в личных ветках и открывают pull request в `main`. `main`
— единственная линия. Процесс описан в
[`docs/engineering/git-workflow.md`](docs/engineering/git-workflow.md).

- [CONTRIBUTING.md](CONTRIBUTING.md): как изменения попадают в репозиторий.
- [SECURITY.md](SECURITY.md): как сообщить об уязвимости.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): правила участия.

## Документация

- [AGENTS.md](AGENTS.md): rules for people and agents. Read before any repository change.
- [docs/index.md](docs/index.md): map of product, architecture, contract, engineering, and operations documentation.
- [docs/product/vision.md](docs/product/vision.md): the problem, users, value, and positioning of ai_stp.
- [docs/product/scope.md](docs/product/scope.md): required MVP capabilities, harness statuses, and explicit exclusions.
- [docs/architecture/overview.md](docs/architecture/overview.md): overall data flow and the boundaries of the local and server environments.
- [specs/index.md](specs/index.md): versioned requirements that the code must satisfy.
- User docs: [English](https://ai-stp.aiguild.space/en/docs) · [Русский](https://ai-stp.aiguild.space/ru/docs)

## Лицензия

AGPL-3.0-or-later. Лицензия покрывает и сетевое использование платформы: если
`ai-stp` предлагается пользователям как сервис, исходный код изменённой версии
остаётся им доступен.

Каталог принадлежит гильдии. NDDev предоставляет публичные провайдеры
харнессов; они остаются отдельными проектами под своими лицензиями и этим
репозиторием не перелицензируются.

Компоненты и сетапы, опубликованные пользователями, — самостоятельные
произведения под лицензиями своих авторов; лицензия платформы на них не
распространяется.
