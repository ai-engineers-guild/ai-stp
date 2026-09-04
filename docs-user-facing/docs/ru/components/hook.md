---
title: "hook"
description: "Hook-компоненты: действия, привязанные к событиям жизненного цикла харнесса."
---

# `hook`

`hook` — действие, привязанное к событию жизненного цикла харнесса: до
запуска tool, после записи, перед отправкой prompt или в другой момент,
который харнесс действительно документирует.

Hook отвечает на вопрос: **что должно выполниться автоматически, когда
происходит это событие?**

Он не отвечает «какой именованный shortcut набрать?»
([`command`](command.md)), «как агент должен делать этот класс задач?»
([`skill`](skill.md)) и «какое постоянное правило агент должен помнить?»
([`instruction`](instruction.md)).

Hook — самый чувствительный из восьми видов: он может менять состояние,
пока пользователь смотрит на что-то другое.

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `command` | command стартует, когда его вызывает человек или агент; hook стартует на событии |
| `skill` | skill ждёт, пока его выберут для задачи; hook не ждёт |
| `instruction` | instruction — текст; hook — действие |
| `plugin` | plugin может *содержать* каталог hooks; сам hook остаётся видом `hook` |
| `mcp` | MCP — интерфейс tool; hook — не сервер протокола |
| `agent` | agent — роль; hook — не subagent |
| `setting` | setting хранит параметры; hook хранит событие и handler |

Выбирайте `hook`, когда проверка на этом событии должна быть неизбежной.
Выбирайте `command`, когда работу должен начать человек. Выбирайте
`instruction`, когда достаточно напоминания прозой.

## Рекомендуемая структура пакета

Handler hook должен быть непосредственно запускаемым после установки.
`--language` — `python`, `typescript`, `javascript` или `dart-flutter`.
Rust и Go отклоняются: provider не делает скрытую сборку исходников.

Переносимый нативный layout — манифест `hooks.json` плюс handler.
Авторский каталог также держит `source/hook.json` (событие, порядок,
блокирующий failure, handler). `discover` / `adopt` переносят `source/`
для portable и `projections/<harness>/` для конкретного харнесса, а не
всё дерево.

```text
pre-tool-check/                    # component-scaffold/3
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    ├── hook.json
    └── hooks/
        └── handler.py
```

```bash
ai-stp component scaffold plan \
  --type hook \
  --language python \
  --harness portable \
  --name pre-tool-check \
  --output ./pre-tool-check \
  --json

ai-stp component scaffold apply \
  --type hook \
  --language python \
  --harness portable \
  --name pre-tool-check \
  --output ./pre-tool-check \
  --expected-plan-digest <digest> \
  --json
```

`--language rust` и `--language go` для этого вида отклоняются закрыто.

Adopt принимает путь, который discovery уже назвал. У каталога должен
быть манифест из закрытого набора. `hooks.json` входит в этот набор.
Каталог hook внутри plugin — один компонент: он включает манифест и
соседние scripts в детерминированный артефакт. Scripts во время discovery
**не** запускаются.

Команды `ai-stp component hook validate` нет. Структурная готовность —
`component passport validate`. Kind-specific проверка по спецификации
есть только у [`skill`](skill.md).

## Стандарты и фреймворки

Независимой спецификации hook, сравнимой с
[Agent Skills Specification](https://agentskills.io/specification) или с
[MCP](https://modelcontextprotocol.io), нет. Каждый харнесс документирует
свои события.

Ссылайтесь на `layout_source` из `ai-stp component discover --json`,
когда классификация неясна. Не угадывайте путь соседа и не считайте
обычный `src/hooks/useFoo.ts` или бизнес-webhook hook'ом харнесса —
`unsupported` в матрице не становится эвристикой по имени файла.

NVIDIA SkillSpector и Cisco Skill Scanner — сканеры skill. Они не
проверяют hooks.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть `layout_source`.
Если классификация неясна, покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | нет top-level ячейки | нет top-level ячейки | манифест-backed: `hooks/hooks.json` **внутри** plugin, доказанного `.claude-plugin/plugin.json` |
| Codex | нет | да | только `.codex/hooks.json` или `hooks/hooks.json` внутри plugin, доказанного `.codex-plugin/plugin.json` |
| Pi | нет | нет | hook layout не объявлен |
| OpenCode | нет | нет | hook layout не объявлен |
| Grok Build | да | да | ограниченный нативный каталог hook |
| Cursor | не выдумывается из соседнего каталога | не выдумывается из соседнего каталога | официальная схема plugin называет `hooks`; walker не изобретает их из соседнего каталога |
| Antigravity | да | да | |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |

Project plugin pack Claude Code доказывается только точным
`.claude-plugin/plugin.json`. Внутри этого pack discovery читает
`hooks/hooks.json` как один hook-компонент.

Cursor pack доказывается `.cursor-plugin/plugin.json`. Walker не создаёт
находку hook из соседнего каталога `hooks/`, который дерево не несёт.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Версии — `X.Y`, не SemVer

Опубликованная версия hook неизменяема и имеет вид `X.Y`. Патч-номера нет.
Изменение события, matcher или handler — новая версия. Обновление hook
внутри сетапа — новая версия сетапа.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию. Мажорная линия — отдельная
граница доступа.

## Что проверяет `ai_stp`

Процент карточки каталога и разделение обязательных и необязательных
проверок объяснены на странице
[Проверки безопасности](../security-checks.md). Для hook ожидайте как
минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого;
- `hook_schema_static` и `hook_command_argv` (схема, argv);
- языковой SAST и SCA, когда есть scripts и lockfiles.

Пройденное сканирование снижает известный риск. Это не гарантия, что
handler безвреден. Обязательные проверки, которые провалились или не
смогли запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| Событие | человек должен суметь назвать, когда оно срабатывает |
| Действие | одна фраза; если сказать нельзя — не включайте |
| Отключение / rollback | hook, который нельзя выключить, не MVP-безопасен |
| Кто автор | verified-автор не делает handler автоматически безопасным |
| Какой `X.Y` закреплён | обновление hook создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

`author_verified` и `component_verified` независимы. Ни одно не является
гарантией безопасности.

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда со страниц CLI и всегда
`--json`. Исполняемый файл — `ai-stp` (пакет `ai-stp-cli`). Команд
`component inspect` и `setup show` нет. Единственный kind-specific
validate — `ai-stp component skill validate`.

**Именно этот вид:** команды `component hook validate` нет. Используйте
проверку паспорта.

```bash
ai-stp component passport validate --id <stable_id> --json
```

**Автор, adopt, публикация:**

```bash
ai-stp component discover --root . --json
ai-stp component adopt --path <source_path> --json
ai-stp component passport validate --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
ai-stp publication plan --id <stable_id> --version 1.0 --json
ai-stp publication confirm --plan-id <id> --plan-hash <hash> --confirm --json
```

**Найти, выбрать, установить:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

Hook может быть embedded-членом compose-манифеста. См.
[Сетапы](../setups/index.md).

## Как hook проходит через `ai_stp`

=== "Автор"
    Автор публикует hook из публичного GitHub-источника или импортирует
    его локально. Версия закрепляет точный commit и подпуть. Discovery
    никогда не исполняет handler.

=== "Каталог"
    Каталог показывает событие, поддерживаемые харнессы, ограничения,
    trusted status автора и независимый status самого компонента.

=== "Сборщик"
    Сборщик проверяет, что харнесс поддерживает это событие жизненного
    цикла и что handler можно спроецировать для provider.

=== "Provider"
    Provider пишет нативную конфигурацию hook только после плана, digest
    и подтверждения. Затем status должен показать hook, его источник и
    как его отключить.

## Красные флаги

- Обычный React-каталог `src/hooks/`, классифицированный как hook харнесса.
- Каталог `hooks/` рядом с Cursor plugin, выданный за hook, хотя walker
  этот layout не изобретает.
- Codex hooks где угодно, кроме `.codex/hooks.json` или
  `hooks/hooks.json` внутри доказанного пакета `.codex-plugin/plugin.json`.
- Scaffold с `--language rust` или `--language go`.
- Handler'ы, которые скачивают и pipe'ят в shell.
- Живые токены, закрытые ключи или тела `.env` в пакете.
- Нет документированного способа отключить или откатить hook.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `author_verified` как с `component_verified`.
- Копирование `hooks.json` в target в обход плана provider.

??? question "Можно ли hook использовать без публикации"
    Да. Собственный, импортированный или точно закреплённый hook можно
    использовать после локальных проверок. Он от этого не становится
    platform-verified и должен быть показан именно как локальный или
    закреплённый объект (`local_owner_or_pinned`). Preview, backup и
    способ выключить его по-прежнему обязательны.

## Чеклист автора

1. Сделайте scaffold с `--type hook` и непосредственно запускаемым
   `--language` (`python`, `typescript`, `javascript` или
   `dart-flutter`).
2. Держите `hooks.json` и handler под `source/`. Заполните
   `source/hook.json`: событие, порядок, блокирующий failure и handler.
3. Объявите в паспорте, что делает handler, что он читает и как его
   отключить. Секретов нет.
4. Запустите `ai-stp component discover --root . --json` и прочитайте
   `layout_source` у находки.
5. `component adopt --path <точный source_path>`.
6. Закрепите точный публичный GitHub commit и подпуть.
7. `component passport validate` → `component version release`, чтобы
   выпустить неизменяемый `X.Y`.
8. Публикуйте через [путь публикации](../publishing/index.md).
9. В сетапе закрепите этот `X.Y`. Позднее обновление — новая версия
   сетапа.

Связанное: [Авторство](../publishing/authoring.md),
[Компоненты](index.md), [`command`](command.md), [`plugin`](plugin.md).
