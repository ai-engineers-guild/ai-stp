---
title: "command"
description: "Command-компоненты: именованные shortcuts, которые может вызвать человек или агент."
---

# `command`

`command` — именованный вход в повторяемое действие: slash command,
шаблон prompt или другой shortcut, который харнесс действительно
документирует.

Command отвечает на вопрос: **какую проверяемую операцию можно вызвать
по имени?**

Он не отвечает «как агент должен делать этот класс задач?»
([`skill`](skill.md)), «что должно выполниться автоматически на событии?»
([`hook`](hook.md)) и «какое семейство CLI открывает сам `ai-stp`?»
(эти страницы живут в [`cli/`](../cli/index.md)).

!!! warning "Вид `command` — не CLI `ai-stp`"

    Эта страница — **вид компонента** `command`, который входит в сетап.

    Исполняемый файл `ai-stp` (пакет `ai-stp-cli`) имеет собственные
    группы команд — `component`, `select`, `install` и остальные. Они
    описаны в [CLI](../cli/index.md). Это не компоненты каталога, их не
    выбирают в сетап, и команды `ai-stp component command validate` нет.

    Codex называет эту поверхность **command/prompt**. Discovery всё равно
    сообщает вид `command`.

    | Объект | Где живёт | Живёт в сетапе? |
    | --- | --- | --- |
    | Вид `command` (эта страница) | slash/prompt-поверхность харнесса | да |
    | Группы CLI `ai-stp …` | [Карта CLI](../cli/commands.md) | нет |

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `skill` | skill активируется по смыслу задачи; command вызывается по имени |
| `hook` | hook стартует на событии жизненного цикла; command стартует при вызове |
| `instruction` | instruction уже в контексте; command — точка входа |
| `plugin` | plugin может *содержать* каталог `commands/`; каждый файл всё равно вид `command` |
| `agent` | agent — роль; command — shortcut, которым роль может пользоваться |
| `mcp` | MCP — протокол tool; command — не сервер |
| `setting` | setting хранит параметры; command хранит вызов |

Выбирайте `command`, когда человек или агент должен начать работу по
имени. Выбирайте `skill`, когда агент должен узнать задачу без slash.
Выбирайте `hook`, когда работа должна произойти на событии.

## Рекомендуемая структура пакета

`command` декларативен. `--language` — `none`. Обычно command — один
Markdown-файл. Claude Code авторит commands как файлы в directory-shaped
layout; adopt принимает этот одиночный файл без дополнительного
манифеста-обёртки.

Переносимый пакет (то, что `discover` / `adopt` переносят из `native/`):

```text
run-tests/
└── run-tests.md                   # {name}.md в корне пакета
```

Когда вы начинаете из `ai_stp`, сначала сделайте scaffold. Авторский
каталог шире опубликованного пакета: `discover` / `adopt` переносят
`native/`, а не всё дерево.

```text
run-tests/                         # component-scaffold/2
├── .ai-stp-template.json
├── authoring-template.md
├── component-passport.json
├── eval-profile.json
├── README.md
├── SAFETY.md
├── PUBLICATION.md
└── native/
    └── run-tests.md
```

```bash
ai-stp component scaffold plan \
  --type command \
  --language none \
  --harness portable \
  --name run-tests \
  --output ./run-tests \
  --json

ai-stp component scaffold apply \
  --type command \
  --language none \
  --harness portable \
  --name run-tests \
  --output ./run-tests \
  --expected-plan-digest <digest> \
  --json
```

`--language` для command — `none`. Вид декларативный.

Команды `ai-stp component command validate` нет. Структурная готовность —
`component passport validate`. Kind-specific проверка по спецификации
есть только у [`skill`](skill.md).

Дайте command короткое имя, явное описание и ограниченные аргументы.
Агент должен читать доступные commands из machine help, а не придумывать
их из памяти — это правило для самого `ai-stp`
(`ai-stp help --agent --json`) и правильная привычка для commands харнесса
тоже.

## Стандарты и фреймворки

Независимой спецификации command, сравнимой с
[Agent Skills Specification](https://agentskills.io/specification), нет.
Skill — переносимый workflow; command — именованный вход.

Ссылайтесь на `layout_source` из `ai-stp component discover --json`,
когда классификация неясна. Не угадывайте путь соседа.

NVIDIA SkillSpector и Cisco Skill Scanner — сканеры skill. Они не
проверяют commands.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть `layout_source`.
Если классификация неясна, покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | да | да | под `commands/`; внутри доказанного пакета `.claude-plugin/plugin.json` члены `commands/` — commands |
| Codex | command/prompt | нет | global-каталог prompt в ограниченной матрице |
| Pi | да | да | |
| OpenCode | да | да | |
| Grok Build | общий command | нет | общий command в global-области в ограниченной матрице |
| Cursor | через plugin pack | через plugin pack | commands читаются внутри доказанного пакета `.cursor-plugin/plugin.json` |
| Antigravity | нет | нет | command layout в ограниченной матрице не объявлен |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |

Внутри доказанного Claude Code plugin discovery читает `commands` (каждый
потомок — один command). Внутри доказанного Cursor plugin — то же самое.
Официальная схема Cursor называет и другие ключи; walker не изобретает
файлы command из соседнего каталога.

Одиночный файл в directory-shaped layout дополнительного манифеста не
требует — так авторят commands Claude Code, и adopt их принимает.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Версии — `X.Y`, не SemVer

Опубликованная версия command неизменяема и имеет вид `X.Y`. Патч-номера
нет. Изменение Markdown, имени или аргументов — новая версия. Обновление
command внутри сетапа — новая версия сетапа.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию. Мажорная линия — отдельная
граница доступа.

## Что проверяет `ai_stp`

Процент карточки каталога и разделение обязательных и необязательных
проверок объяснены на странице
[Проверки безопасности](../security-checks.md). Для command ожидайте как
минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого.

Пройденное сканирование снижает известный риск. Это не гарантия, что
shortcut безвреден. Обязательные проверки, которые провалились или не
смогли запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| Конфликт имён | два shortcut с одним именем путают и людей, и агентов |
| Описание | агент не должен угадывать, для чего command |
| Что он меняет | command, который мутирует внешний мир, должен быть в плане установки |
| Кто автор | verified-автор не делает shortcut автоматически безопасным |
| Какой `X.Y` закреплён | обновление command создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

`author_verified` и `component_verified` независимы. Ни одно не является
гарантией безопасности.

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда со страниц CLI и всегда
`--json`. Исполняемый файл — `ai-stp` (пакет `ai-stp-cli`). Команд
`component inspect` и `setup show` нет. Единственный kind-specific
validate — `ai-stp component skill validate`.

**Именно этот вид:** команды `component command validate` нет.
Используйте проверку паспорта.

```bash
ai-stp component passport validate --id <stable_id> --json
```

**Не этот вид** — группы CLI `ai-stp` (см. [CLI](../cli/index.md)):

```bash
ai-stp help --agent --json
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

Command может быть embedded-членом compose-манифеста. См.
[Сетапы](../setups/index.md).

## Как command проходит через `ai_stp`

=== "Автор"
    Автор публикует command из публичного GitHub-источника или импортирует
    его локально. Версия закрепляет точный commit и подпуть.

=== "Каталог"
    Каталог показывает имя, поддерживаемые харнессы, ограничения,
    trusted status автора и независимый status самого компонента.

=== "Сборщик"
    Сборщик проверяет конфликт имён, совместимость с харнессом и что
    файловая структура подходит проекции provider.

=== "Provider"
    Provider создаёт нативную команду там, где её ожидает этот харнесс,
    только после плана, digest и подтверждения.

## Красные флаги

- Обращение с группой CLI `ai-stp` так, будто это этот вид компонента.
- Skill (каталог с `SKILL.md`), помеченный как command, или наоборот.
- Каталог `commands/` внутри `.claude-plugin/` (каталог манифеста держит
  только `plugin.json`; `commands/` стоит в корне plugin).
- Неограниченные аргументы, из-за которых опасный вызов становится лёгким.
- Живые токены, закрытые ключи или тела `.env` в пакете.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `author_verified` как с `component_verified`.
- Command, который меняет внешний мир, но невидим в плане установки.

??? question "Можно ли command использовать без публикации"
    Да. Собственный, импортированный или точно закреплённый command можно
    использовать после локальных проверок. Он от этого не становится
    platform-verified и должен быть показан именно как локальный или
    закреплённый объект (`local_owner_or_pinned`).

## Чеклист автора

1. Сделайте scaffold с `--type command --language none` и держите
   Markdown в корне пакета (в авторском дереве — под `native/`).
2. Дайте короткое имя, описание, которое прочитает человек, и
   ограниченные аргументы. Процедуру с assets положите в
   [`skill`](skill.md).
3. Объявите в `SAFETY.md`, что command меняет. Секретов нет.
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
[Компоненты](index.md), [`skill`](skill.md), [`hook`](hook.md),
[Карта CLI](../cli/commands.md).
