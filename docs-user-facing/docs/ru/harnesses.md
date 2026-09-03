---
title: "Поддерживаемые харнессы"
description: "Какие AI-харнессы поддерживает ai_stp и что означает уровень поддержки."
---

# Поддерживаемые харнессы

Харнесс — CLI-среда, в которой работает coding agent. `ai_stp` не заменяет
харнесс и не вызывает модели: он помогает собрать проверяемый сетап для
конкретного target, а применяет итоговое состояние только provider этого
харнесса.

## Статусы MVP

| Харнесс | Статус в MVP | Что доступно | Что помнить |
| --- | --- | --- | --- |
| Claude Code | основная поддержка | паспорта, совместимость, сборка сетапа, provider-план | production-путь проектируется в первую очередь под него |
| Codex | основная поддержка | паспорта, совместимость, сборка сетапа, provider-план | второй основной target MVP |
| Grok Build | основная поддержка | паспорта, совместимость, сборка сетапа, provider-план | третий основной target MVP |
| Pi | beta | каталог и совместимость, ограниченный provider-путь | поведение может уточняться по мере интеграции |
| OpenCode | beta | каталог и совместимость, adapter/projection checks | формат открыт, но не весь UX считается стабильным |
| Cursor | beta | каталог и совместимость, нативный plugin pack и cli-config | plugin pack распознаётся по манифесту `.cursor-plugin` |
| Antigravity | beta | каталог и совместимость, provider-план | конфигурация лежит внутри `~/.gemini`, а не в собственном каталоге |
| `undefined` | ограниченный режим | чтение, импорт, локальные проверки | автоматическая установка не считается безопасной |

## Что означает “поддерживается”

Поддержка в `ai_stp` состоит из нескольких уровней. Харнесс может проходить
один уровень и ещё не быть готовым к следующему.

| Уровень | Что проверяется | Зачем пользователю |
| --- | --- | --- |
| Detection | CLI понимает, что за target перед ним | чтобы не применить сетап не туда |
| Compatibility | компоненты объявляют поддержку харнесса | чтобы отсеять очевидно неподходящее |
| Projection | сетап можно превратить в нативную структуру | чтобы файлы и настройки попали в правильный формат |
| Provider plan | provider строит план изменения target | чтобы увидеть diff до применения |
| Apply | provider применяет изменения и пишет журнал | чтобы был rollback и проверяемый результат |

=== "Основные: Claude Code, Codex, Grok Build"

    Для них MVP должен давать самый короткий путь: найти сетап, проверить
    совместимость, увидеть план, подтвердить и применить через provider.

=== "Beta: Pi, OpenCode, Cursor, Antigravity"

    Beta означает, что `ai_stp` уже различает харнесс и может работать с его
    объектами, но часть provider-пути, UX или проверок может быть строже и
    требовать ручного подтверждения.

=== "`undefined`"

    Этот режим нужен, чтобы не терять объект, когда харнесс неизвестен. Он
    подходит для чтения, импорта и локального анализа, но не для уверенной
    автоматической установки.

??? question "Почему сетап принадлежит одному харнессу"
    Потому что одинаковые слова в разных CLI часто означают разные файлы,
    права и события. `skill` для Codex и `skill` для Claude Code могут иметь
    похожий смысл, но разные нативные поверхности. Поэтому сетап создаётся для
    одного харнесса, а перенос делается через явную новую версию или адаптацию.

## Что оказывается на диске у трёх основных харнессов

`ai_stp` не копирует файлы в target. Сборщик строит нативный пакет; provider
его записывает. Точные пути на машине даёт
`ai-stp component discover --json` (`source_path`, `layout_source`) и план
provider. Виды, которые discovery будет искать:

| Вид | Claude Code | Codex | Grok Build |
| --- | --- | --- | --- |
| `instruction` | global и project | global и project | нативный layout инструкции не объявлен |
| `skill` | global и project | общий skill (включая `.agents/skills`) | global и project |
| `mcp` | global и project | имена внутри файла настроек (`config.toml`), если есть ключ `mcp_servers` | имена внутри `config.toml`, если ключ есть |
| `hook` | в матрице discovery нет top-level layout | project: `.codex/hooks.json` или `hooks/hooks.json` внутри доказанного plugin | global и project |
| `command` | global и project | global command/prompt | общий command, global |
| `agent` | global и project | project: `.codex/agents` | нативный layout агента не объявлен |
| `plugin` | global и project; pack — plugin только через `.claude-plugin/plugin.json` | корень plugin, skill и hooks-directory; pack через `.codex-plugin/plugin.json` | global и project; `plugins/marketplaces` — не plugin |
| `setting` | global и project | global и project (`config.toml`) | global и project (`config.toml`) |

Каталог `plugins/` без манифеста поддерживаемого харнесса не является
plugin. `CODEX.md` — не официальный layout инструкции Codex; discovery
возвращает `unsupported_manifest` и указывает на `AGENTS.md`.

Общие `.agents/skills` не принадлежат ни одному харнессу и возвращаются с
`harness_id=null`.

После apply подтвердите:

```bash
ai-stp target status --project <id> --harness <id> --json
ai-stp target diff --project <id> --harness <id> --json
```

## Официальная документация харнессов

Это документация вендоров, а не страницы `ai_stp`. Layouts, с которыми
`ai_stp` будет работать, — только те, что `component discover` вернул с
`layout_source`.

| Харнесс | Официальная документация |
| --- | --- |
| Claude Code | [документация Claude Code](https://docs.anthropic.com/en/docs/claude-code) |
| Codex | [документация ChatGPT / Codex](https://learn.chatgpt.com/docs) (нативный файл инструкции: `AGENTS.md`) |
| Grok Build | [документация xAI Build](https://docs.x.ai/build) |
| Pi | [документация Pi](https://pi.dev/docs/latest) |
| OpenCode | [документация OpenCode](https://opencode.ai/docs) |
| Cursor | [документация Cursor](https://docs.cursor.com) |
| Antigravity | [документация Antigravity](https://antigravity.google/docs) |

Если классификация неясна, покажите поле `layout_source` из
`component discover`. Не выдумывайте путь только потому, что соседний
харнесс так устроен.

## Как выбрать target

1. Запустите `ai-stp doctor --json`.
2. Проверьте, какой харнесс обнаружен: `ai-stp toolchain harnesses --json`.
3. Откройте сетап или компонент в каталоге.
4. Сверьте поддержку харнесса и линию доверия.
5. Смотрите provider-план до применения.

```bash
ai-stp doctor --json
ai-stp toolchain harnesses --json
ai-stp toolchain harness-capabilities --json
```

!!! tip "Для MVP"
    Если вы не уверены, начинайте с Claude Code, Codex или Grok Build. Для
    beta-линий сохраняйте план установки и не удаляйте backup до проверки
    результата.
