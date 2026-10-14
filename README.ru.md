<p align="center">
  <a href="README.md">English</a> · <strong>Русский</strong>
</p>

<p align="center">
  <img src="assets/readme/ru/hero.svg" width="640" alt="ai-stp: подберите, проверьте и установите полный сетап через агента.">
</p>

<p align="center">
  <a href="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml"><img src="https://github.com/ai-engineers-guild/ai-stp/actions/workflows/check.yml/badge.svg?branch=main" alt="check"></a>
  <a href="https://github.com/ai-engineers-guild/ai-stp/releases?q=cli-v"><img src="https://img.shields.io/badge/CLI-Rust-orange" alt="Rust CLI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="License: AGPL-3.0"></a>
  <a href="https://ai-stp.aiguild.space"><img src="https://img.shields.io/badge/catalog-ai--stp.aiguild.space-black" alt="catalog"></a>
</p>

Команда — `ai-stp`, самостоятельный бинарник на Rust без Python. Первичный потребитель —
агент пользователя: каждая команда отвечает одним JSON-конвертом. `ai-stp` не
вызывает API модели и не требует ключа модели.

## Один сетап, девять видов, точные версии

<p align="center">
  <img src="assets/readme/shared/kinds.svg" width="640" alt="Девять видов: instruction, skill, mcp, hook, command, agent, plugin, setting, cli.">
</p>

**Сетап** с создания принадлежит одному харнессу. Закрытые виды:
`instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`,
`setting`, `cli`. `command` — именованный slash-вызов; `cli` — отдельный
исполняемый процесс. Память и правила — содержимое этих видов, не отдельные
виды. Опубликованная версия закрепляет точные версии компонентов и неизменяема.

## CLI собирает, провайдер пишет

CLI и агент подбирают, проверяют и собирают пакет. Каждая команда — один
JSON-конверт. CLI не пишет нативные файлы харнесса. Веб владеет аккаунтом и
публичным каталогом; он не собирает и не устанавливает сетап. Нативное
состояние харнесса пишет только провайдер.

<p align="center">
  <img src="assets/readme/shared/workflow.svg" width="640" alt="Восемь видов закрепляются в один сетап одного харнесса. CLI проверяет и собирает пакет. Нативные файлы пишет только провайдер.">
</p>

Доверие — origin, version и consent. Совместимость — graph, target и policy —
решает до apply. Опубликованная версия — неизменяемый digest, связанный с
версией объекта, политикой и устройством. Синхронизация продолжается с
последнего подтверждённого cursor. Подтверждение автора — происхождение, а не
вердикт о безопасности байтов. `author_verified` и `component_verified`
независимы.

Локальная работа не требует аккаунта. Публичный каталог читается анонимно.
Вход через Google или GitHub открывает приватные объекты, синхронизацию,
публикацию, устройства и grants.

## Поставьте CLI, дальше ведёт агент

Скачайте Rust-архив для своей платформы из
[GitHub Releases](https://github.com/ai-engineers-guild/ai-stp/releases?q=cli-v),
проверьте checksum и attestation и выполните
[инструкцию установки](apps/cli-v2/README.md#install-and-update).

```sh
ai-stp init --credential-store os_keyring --json
ai-stp task intents --json
```

Для существующей Python-установки используйте явный перенос состояния из
[руководства CLI](apps/cli-v2/README.md#state-and-first-run): база остаётся на месте,
ключ устройства сохраняется, старый писатель блокируется. Исторический пакет
PyPI `ai-stp-cli` больше не является актуальным способом установки.

`task input-schema` описывает входы author/install, `help --agent --json` —
реальные команды. Сетап-системы входят в ai-stp как установочные компоненты.
Исполняемые файлы харнессов пользователь и их поставщики обслуживают сами.

## Настольное приложение

`apps/desktop` — это `ai-stp-desktop`, оболочка Tauri 2 над тем же
машинным контрактом CLI — каталог, сценарии task-движка, цели и
восстановление в нативном окне для Linux, macOS и Windows. Релизные
пакеты содержат CLI как sidecar, поэтому отдельная установка не нужна.
Свежая сборка — на
[GitHub Releases](https://github.com/ai-engineers-guild/ai-stp/releases?q=desktop)
(пакеты не подписаны; `SHA256SUMS` покрывает каждый артефакт). Детали и
правила границ — в `apps/desktop/README.md` и ADR-0222.

## Поддержка платформ и харнессов

Сборки Rust CLI проверяются CI на Linux x86-64, Apple Silicon macOS и Windows
x86-64. Изолированная установка сетапов и передача активной сессии реализованы
на Linux. На macOS и Windows эта операция возвращает явный отказ; успешная
сборка не означает поддержку установщика. Точную границу показывает `capabilities`.

Установочные компоненты охватывают Claude Code, Codex, Grok Build, Pi, OpenCode,
Cursor и Antigravity. `provider inspect` и проверки совместимости определяют
доступные виды и поверхности для конкретной операции.

Актуальное [руководство Rust CLI](apps/cli-v2/README.md) описывает установку,
перенос состояния и восстановление. Параметры команд принадлежат реестру CLI.

`main` — защищённая релизная ветка; разработка начинается от `dev`, изменения
входят в неё через PR и затем продвигаются в `main`. Для работы на новом ПК
следуйте [CONTRIBUTING.md](CONTRIBUTING.md#development-on-a-new-workstation).

Статус фазы принадлежит
[`docs/engineering/implementation-roadmap.md`](docs/engineering/implementation-roadmap.md):
это файл, который нужно открыть за текущим evidence, а не краткое изложение здесь.

<details>
<summary>Участие</summary>

- [CONTRIBUTING.md](CONTRIBUTING.md): how changes enter this repository.
- [SECURITY.md](SECURITY.md): how to report a vulnerability.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): expectations for participation.
- [AGENTS.md](AGENTS.md): rules for people and agents. Read before any repository change.

</details>

<details>
<summary>Документация</summary>

- [docs/index.md](docs/index.md): map of product, architecture, contract, engineering, and operations documentation.
- [docs/product/vision.md](docs/product/vision.md): the problem, users, value, and positioning of ai_stp.
- [docs/product/scope.md](docs/product/scope.md): required MVP capabilities, harness statuses, and explicit exclusions.
- [docs/architecture/overview.md](docs/architecture/overview.md): overall data flow and the boundaries of the local and server environments.
- [specs/index.md](specs/index.md): versioned requirements that the code must satisfy.
- User docs: [English](https://ai-stp.aiguild.space/en/docs) · [Русский](https://ai-stp.aiguild.space/ru/docs)

</details>

<details>
<summary>Лицензия</summary>

AGPL-3.0-or-later. Сетевое использование платформы покрыто: если `ai-stp`
предлагается как сервис, исходный код изменённой версии остаётся доступен
этим пользователям.

Каталог принадлежит гильдии. Публичные провайдеры харнессов — компоненты
ai-stp, сохраняющие отдельные репозитории и собственные лицензии.

Компоненты и сетапы пользователей — самостоятельные произведения под
лицензиями авторов; лицензия платформы на них не распространяется.

</details>
