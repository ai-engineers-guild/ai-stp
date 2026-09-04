---
title: "plugin"
description: "Plugin-компоненты: нативные расширения харнесса, отдельно от marketplace."
---

# `plugin`

`plugin` — нативное расширение харнесса. Оно может добавлять skills,
agents, commands, hooks, клиентскую MCP-конфигурацию или другие surfaces
**там, где этот харнесс их документирует**.

Plugin отвечает на вопрос: **какой пакет расширяет сам харнесс?**

Он не отвечает «какой один MCP-сервер подключён?» ([`mcp`](mcp.md)),
«какой workflow должен следовать агент?» ([`skill`](skill.md)) и «через
какой каталог plugins это поставляется?» (это упаковка **marketplace**,
а не вид компонента).

!!! warning "Plugin — не marketplace"

    `marketplace` — нативная упаковка: коллекция или ledger, которым
    харнесс распространяет plugins. Это **не** один из восьми видов
    компонента. `plugins/marketplaces` у Grok Build — служебный контейнер,
    не plugin, и discovery не возвращает его как кандидат.

    Каталог под `plugins/` становится plugin только через точный манифест
    из закрытого набора. JSON-**значения** манифеста не читаются —
    существование файла доказывает, что каталог является plugin.

    | Объект | Что это | Вид компонента? |
    | --- | --- | --- |
    | Pack с `.claude-plugin/plugin.json` | plugin | да, `plugin` |
    | Pack с `.codex-plugin/plugin.json` | plugin | да, `plugin` |
    | Pack с `.cursor-plugin/plugin.json` | plugin | да, `plugin` |
    | Pack с `plugin.json` | plugin | да, `plugin` |
    | Marketplace / `plugins/marketplaces` | упаковка / служебный контейнер | нет |

    Внутри доказанного plugin вложенные члены сохраняют свои виды
    (`skill`, `agent`, `command`, `hook`, `instruction`, `mcp`). Pack —
    это plugin; члены не переименовываются в plugins.

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `skill` | skill расширяет рабочее поведение агента; plugin расширяет харнесс |
| `mcp` | MCP-**сервер** — это `mcp` с `harness_id=null`; `.mcp.json` plugin — клиентский конфиг, всё ещё вид `mcp` |
| `instruction` | файлы `rules/` Cursor plugin — instructions, а не сам plugin |
| `hook` | plugin может нести `hooks/hooks.json`; этот член — вид `hook` |
| `command` | plugin может нести `commands/`; каждый файл — вид `command` |
| `agent` | plugin может нести `agents/`; каждый файл — вид `agent` |
| `setting` | setting хранит параметры; plugin — пакет |

Выбирайте `plugin`, когда поставляете пакет харнесса. Выбирайте `mcp`,
когда поставляете сервер. Выбирайте `skill`, когда нужен только workflow.

## Рекомендуемая структура пакета

`--language` для plugin — одно из `python`, `typescript`, `javascript`,
`rust`, `go` или `dart-flutter`. Plugins OpenCode и Pi — **один модуль
JS/TS**, не выдуманный манифест: для этих двух харнессов `--language`
должен быть `javascript` или `typescript`.

Манифест-каталоги plugins (Claude Code, Codex, Cursor и переносимый
`plugin.json`):

```text
review-pack/
├── .claude-plugin/
│   └── plugin.json                # или .codex-plugin / .cursor-plugin / plugin.json
├── skills/                        # необязательно; каждый потомок с SKILL.md — skill
├── agents/                        # Claude Code / Cursor, когда есть
├── commands/                      # Claude Code / Cursor, когда есть
├── hooks/
│   └── hooks.json                 # Claude Code / Codex, когда есть
└── .mcp.json                      # клиентский конфиг Claude Code; не сервер
```

Cursor внутри доказанного pack: `skills`, `agents`, `commands` и `rules`
(каждый файл — `instruction`). Официальная схема также называет `hooks`
и `mcpServers`; walker не изобретает эти виды из соседнего каталога.

Когда вы начинаете из `ai_stp`, сначала сделайте scaffold. Авторский
каталог шире опубликованного пакета: `discover` / `adopt` переносят
`source/` для portable и `projections/<harness>/` для конкретного харнесса,
а не всё дерево.

```text
review-pack/                       # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    ├── plugin.json
    └── skills/
        └── README.md
```

```bash
ai-stp component scaffold plan \
  --type plugin \
  --language python \
  --harness portable \
  --name review-pack \
  --output ./review-pack \
  --json

ai-stp component scaffold apply \
  --type plugin \
  --language python \
  --harness portable \
  --name review-pack \
  --output ./review-pack \
  --expected-plan-digest <digest> \
  --json
```

Для OpenCode или Pi сделайте scaffold одного `{name}.js` или `{name}.ts`
под `source/` (и `projections/<harness>/`). Не выдумывайте `plugin.json`,
который эти продукты не используют.

Adopt каталога требует манифест из закрытого набора. Имена plugin в этом
наборе: `plugin.json`, `.claude-plugin/plugin.json`,
`.codex-plugin/plugin.json` и `.cursor-plugin/plugin.json`. Каталог
`plugins/`, у членов которого нет манифеста **ни одного**
поддерживаемого харнесса, компонентов не даёт и один раз на коллекцию
сообщает `unsupported_manifest`.

Команды `ai-stp component plugin validate` нет. Структурная готовность —
`component passport validate`. Kind-specific проверка по спецификации
есть только у [`skill`](skill.md).

## Стандарты и фреймворки

- Plugins Claude Code (проверенный источник):
  [Create plugins](https://code.claude.com/docs/en/plugins). Discovery
  `layout_source` для этого pack — `code.claude.com/docs/en/plugins`.
- Packs Codex и Cursor: ссылайтесь на `layout_source` находки
  (`learn.chatgpt.com/docs/build-plugins`,
  `cursor.com/docs/reference/plugins`). Не выдумывайте URL документации.
- Вложенные skills по-прежнему следуют
  [Agent Skills Specification](https://agentskills.io/specification).
- Вложенный MCP-клиентский конфиг следует
  [MCP](https://modelcontextprotocol.io) как протоколу; файл `.mcp.json`
  всё равно не сервер.

NVIDIA SkillSpector и Cisco Skill Scanner — сканеры skill. Они не
проверяют пакет plugin целиком.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть `layout_source`.
Если классификация неясна, покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | да | да | доказывается только точным `.claude-plugin/plugin.json`; внутри: `skills`, `agents`, `commands`, `hooks/hooks.json`, `.mcp.json` |
| Codex | корень plugin | корень plugin | доказывается `.codex-plugin/plugin.json`; внутри: `skills`, `hooks/hooks.json` |
| Pi | да | да | ограниченный нативный каталог plugin/extension; отдельного project-plugin манифеста не объявлено |
| OpenCode | да | да | ограниченный нативный каталог plugin; один модуль JS/TS |
| Grok Build | да | да | ограниченный нативный каталог plugin; `plugins/marketplaces` — **не** plugin |
| Cursor | да | да | доказывается `.cursor-plugin/plugin.json`; внутри: `skills`, `agents`, `commands`, `rules` |
| Antigravity | да | да | ограниченный нативный каталог plugin |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |

Pack одного харнесса не вызывает жалобу другого: Codex pack остаётся pack
даже без манифеста Claude.

Под `skills/` каталог с `SKILL.md` — это skill; каталог с
`.claude-plugin/plugin.json` или `plugin.json` — это **plugin**. Discovery
различает их по манифесту, а не по имени родительской папки.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Версии — `X.Y`, не SemVer

Опубликованная версия plugin неизменяема и имеет вид `X.Y`. Патч-номера
нет. Изменение манифеста, вложенного члена или входного модуля — новая
версия. Обновление plugin внутри сетапа — новая версия сетапа.

Манифесты plugin вендора могут содержать собственные строки версии. Эти
строки — не версии `ai_stp`. `ai_stp` по-прежнему выпускает неизменяемый
`X.Y`.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию. Мажорная линия — отдельная
граница доступа.

## Что проверяет `ai_stp`

Процент карточки каталога и разделение обязательных и необязательных
проверок объяснены на странице
[Проверки безопасности](../security-checks.md). Для plugin ожидайте как
минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого;
- языковой SAST и SCA, когда есть scripts и lockfiles;
- вложенные члены, сканируемые как свои виды, когда они есть
  (`mcp_config_static`, `hook_schema_static`, `hook_command_argv`,
  `skill_static_gate`).

Пройденное сканирование снижает известный риск. Это не гарантия, что
plugin безвреден. Обязательные проверки, которые провалились или не
смогли запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| Точный манифест | нет манифеста — это не plugin |
| Вложенные члены | skills, hooks и `.mcp.json` меняют поведение после установки |
| Происхождение | `github/exact` не является platform verification и не означает безопасность plugin |
| Кто автор | verified-автор не делает plugin автоматически безопасным |
| Какой `X.Y` закреплён | обновление plugin создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

`author_verified` и `component_verified` независимы. Ни одно не является
гарантией безопасности.

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда со страниц CLI и всегда
`--json`. Исполняемый файл — `ai-stp` (пакет `ai-stp-cli`). Команд
`component inspect` и `setup show` нет. Единственный kind-specific
validate — `ai-stp component skill validate`.

**Именно этот вид:** команды `component plugin validate` нет. Используйте
проверку паспорта. Вложенные skills всё равно можно проверить так:

```bash
ai-stp component skill validate --path <directory-with-SKILL.md> --json
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

Если путь также заявлен как каталог skill:

```bash
ai-stp component adopt --path <source_path> --kind plugin --json
```

**Найти, выбрать, установить:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

Plugin может быть embedded-членом compose-манифеста. См.
[Сетапы](../setups/index.md).

## Как plugin проходит через `ai_stp`

=== "Автор"
    Автор публикует plugin из публичного GitHub-источника или импортирует
    его локально. Версия закрепляет точный commit и подпуть. Discovery
    plugin не запускает.

=== "Каталог"
    Каталог показывает назначение, поддерживаемые харнессы, ограничения,
    trusted status автора и независимый status самого компонента.

=== "Сборщик"
    Сборщик проверяет, что plugin можно встроить в выбранный сетап и что
    его файловая структура подходит проекции provider.

=== "Provider"
    Provider устанавливает нативный пакет только после плана, digest и
    подтверждения. Rollback должен вернуть target настолько, насколько
    позволяет provider этого харнесса.

## Красные флаги

- Каталог `plugins/` без поддерживаемого манифеста, выданный за plugin.
  Discovery один раз сообщает `unsupported_manifest`; пустой инвентарь без
  этой диагностики был бы хуже.
- Marketplace или `plugins/marketplaces` Grok Build, помеченные как вид
  `plugin`.
- `commands/`, `agents/`, `skills/` или `hooks/` **внутри**
  `.claude-plugin/` (там принадлежит только `plugin.json`).
- Каталог под `skills/`, который на самом деле plugin, помеченный как
  skill.
- Открытие `.mcp.json`, чтобы скопировать токены в паспорт.
- Живые токены, закрытые ключи или тела `.env` в пакете.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `author_verified` как с `component_verified`.
- Обращение с `github/exact` как с доказательством, что plugin безопасен.

??? question "Можно ли plugin использовать без публикации"
    Да. Собственный, импортированный или точно закреплённый plugin можно
    использовать после локальных проверок. Он от этого не становится
    platform-verified и должен быть показан именно как локальный или
    закреплённый объект (`local_owner_or_pinned`). Supply-chain и
    post-install поведение по-прежнему требуют плана.

## Чеклист автора

1. Сделайте scaffold с `--type plugin` и настоящим `--language`. Для
   OpenCode или Pi используйте `javascript` или `typescript` и один
   модуль.
2. Докажите pack точным манифестом этого харнесса. Не выдумывайте вид
   marketplace.
3. Кладите вложенные члены в корень plugin (`skills/`, `agents/`,
   `commands/`, `hooks/hooks.json`, `.mcp.json`, `rules/` Cursor) только
   когда доказанный pack этого харнесса их действительно читает.
4. Объявите post-install поведение в паспорте. Секретов нет.
5. Запустите `ai-stp component discover --root . --json` и прочитайте
   `layout_source` у находки plugin и у вложенных членов.
6. `component adopt --path <точный source_path>` — добавьте
   `--kind plugin`, если путь также является каталогом skill.
7. Закрепите точный публичный GitHub commit и подпуть.
8. `component passport validate` → `component version release`, чтобы
   выпустить неизменяемый `X.Y`.
9. Публикуйте через [путь публикации](../publishing/index.md). В сетапе
   закрепите этот `X.Y`.

Связанное: [Авторство](../publishing/authoring.md),
[Компоненты](index.md), [`mcp`](mcp.md), [`skill`](skill.md).
