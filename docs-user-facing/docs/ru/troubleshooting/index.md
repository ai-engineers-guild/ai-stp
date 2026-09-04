---
title: "Диагностика"
description: "Базовая диагностика ai_stp и безопасное восстановление после ошибок."
---

# Диагностика

Начинайте с команды:

```bash
ai-stp doctor --json
```

Она показывает состояние CLI, окружения, локального реестра, устройства,
хранилища секретов и доступных возможностей. `doctor` завершается с кодом 0
даже если установка ещё не готова; состояние — в теле ответа.

Также полезно:

```bash
ai-stp capabilities --json
ai-stp help --agent --json
```

Если `help --agent` расходится с флагом на этой странице, прав CLI.

## PATH / команда не найдена

Проверьте установку:

```bash
uv tool list
uv tool install ai-stp-cli
ai-stp version --json
```

Исполняемый файл — `ai-stp`. Пакет PyPI — `ai-stp-cli`. Если пакет есть, а
команды нет, каталог `uv` tools не находится в `PATH`. Добавьте его и снова
запустите `ai-stp version --json`.

## Нет аккаунта

Аккаунт не нужен для локального режима и анонимного чтения публичного
каталога. Авторизация нужна для приватных объектов, синхронизации, публикации,
устройств, привязанных к облачной сессии, и grants.

```bash
ai-stp auth status --json
ai-stp registry search --kind setup --query frontend --json
ai-stp device init --json
ai-stp passport developer init --json
```

`auth status` сообщает local-only, authenticated, expired или revoked. Не
запускайте `auth login`, чтобы «починить» локальный compose.

## Офлайн-кэш

Локальный режим должен продолжать работать после первичной настройки.
Публичный каталог может быть доступен из кэша, если объект уже был подтверждён
платформой.

```bash
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry fetch --kind component --id <stable_id> --version 1.0 --json
ai-stp registry acquire --id <setup_id> --version 1.0 --offline --json
```

Смотрите `checked_at` (или эквивалентное поле свежести в конверте). Попадание
в кэш — не новая verified-публикация. `--offline` у `acquire` использует
только проверенные кэшированные паспорта и артефакты; если их нет, команда
отказывается.

## Устаревший digest плана

Apply повторяет план и отказывается, если digest больше не совпадает. Это
защита, а не ошибка. Не проталкивайте старый digest.

```bash
ai-stp setup compose plan --manifest setup.json --root . --json
ai-stp install plan --setup <stable_id>@<X.Y> --json
```

Постройте новый план, покажите его, передайте новый
`--expected-plan-digest` (или `--plan-hash` / `--set-digest`). Если операцию
уже одобрили, а байты под ней изменились, отмените её, пока apply не начался:

```bash
ai-stp install cancel --operation <id> --json
```

## Частичное применение

Не удаляйте target и резервные копии вручную.

```bash
ai-stp install status --json
ai-stp install recover --operation <id> --json
ai-stp target status --project <id> --harness <id> --json
```

`install recover` сообщает, что оставила остановленная операция и что можно
сделать. Сама команда ничего не восстанавливает.

## install recover / resume

Если apply прервался после того, как provider уже начал работу, завершите
проверку результата, не применяя изменения снова:

```bash
ai-stp install resume --operation <id> --provider <exe> --json
```

`resume` ничего не применяет. Он спрашивает provider, что реально оказалось
на диске. Затем:

```bash
ai-stp target status --project <id> --harness <id> --json
ai-stp target backups --project <id> --harness <id> --json
```

Подробности команд: [Установка](../cli/install.md),
[Target](../cli/target.md).

## Харнесс `undefined`

Автоматическая установка не считается безопасной, когда харнесс —
`undefined`.

```bash
ai-stp toolchain harnesses --json
ai-stp toolchain harness-capabilities --json
ai-stp doctor --json
```

Оставайтесь на основном харнессе (Claude Code, Codex, Grok Build) или
импортируйте и просматривайте локально без apply:

```bash
ai-stp setup import inspect --root <dir> --harness <id> --json
```

См. [Харнессы](../harnesses.md).

## Нет хранилища секретов

Ключ устройства живёт в системном хранилище секретов, если есть доверенный
backend, иначе — в файле только для владельца. `doctor` называет уровень.
Файловый уровень — поддерживаемая конфигурация (SSH, контейнеры), а не
скрытый сбой.

```bash
ai-stp doctor --json
ai-stp device show --json
```

Смотрите проверку `credential_store` и поля идентичности устройства. Если
`device init` ещё не запускали, это `needs_user_action`, а не отсутствие
хранилища:

```bash
ai-stp device init --json
```

`device reset` разрушителен и требует `--confirm`. Это не повтор `doctor`.

## experimental без согласия

Непроверенные объекты не участвуют в автоматической установке без явного
согласия. Нет настройки «включать все непроверенные навсегда».

```bash
ai-stp consent list --json
ai-stp consent allow --scope publisher --target <publisher_id> --json
ai-stp consent allow --scope object_major --target <stable_id>@<major> --json
ai-stp registry search --kind component --query scanner --include-experimental --json
```

`--include-experimental` меняет только этот поиск. Для установки по-прежнему
нужна долговременная запись. Отзыв: `ai-stp consent revoke`. См.
[Доверие и безопасность](../trust-and-safety/index.md).

## Связанные страницы

- [Наблюдение](../cli/observe.md) — `doctor`, `capabilities`, `help --agent`.
- [Быстрый старт для человека](../quickstart/human.md) — `PATH` и первая
  идентичность.
- [Быстрый старт для ИИ-агента](../quickstart/agent.md) — что делать с отказом.
- [Установка](../cli/install.md) — recover, resume, cancel.
- [Target](../cli/target.md) — резервные копии и именованный откат.
- [Харнессы](../harnesses.md) — `undefined` не ставится сам.
- [Согласие](../cli/consent.md) — experimental-объекты.
