---
type: article
slug: kind-mcp
locale: ru
title: "MCP — внешний интерфейс инструмента, а не секретный конфиг"
description: "Расширенный разбор MCP: сервер, клиентская настройка, транспорт, permissions и проверка границ."
published_at: 2026-09-04
tags: [component, mcp]
draft: false
---

# `mcp`

![Component type: mcp](/content/illustrations/kind-mcp.jpg)

`mcp` — способ, которым агент получает структурированную tool surface:
сервер, говорящий на Model Context Protocol, или клиентская конфигурация,
которая указывает харнессу на такой сервер.

MCP-компонент отвечает на вопрос: **какой внешний tool-интерфейс
подключён?**

Он не отвечает «как агент должен пользоваться этим tool?»
([`skill`](https://ai-stp.aiguild.space/ru/docs/components) или [`instruction`](https://ai-stp.aiguild.space/ru/docs/components)), «какой пакет
расширяет харнесс?» ([`plugin`](https://ai-stp.aiguild.space/ru/docs/components)) и «какой именованный shortcut
набрать?» ([`command`](https://ai-stp.aiguild.space/ru/docs/components)).

!!! warning "Два разных MCP-объекта"

    Эта страница покрывает обе нативные роли, которые может сообщить
    discovery. Они разделяют вид `mcp` и это не один объект.

    | Объект | `native_role` | Что делает discovery |
    | --- | --- | --- |
    | Пакет MCP-**сервера** | `mcp_server` | `harness_id=null`; доказывает цепочку пакета; сервер никогда не запускает |
    | `.mcp.json` plugin | `mcp_client_config` | доказывает себя именем; discovery **не открывает** файл |
    | Серверы внутри файла настроек | `mcp_client_config` | файл также является `setting`; читаются только **имена** серверов |

    `.mcp.json` plugin — клиентский конфиг, не сервер. Токены, URL с
    доступом, command, args, headers и env **никогда** не попадают в
    вывод discovery, паспорта, логи или фикстуры.

    Файлы с именем `mcp.json` под Pi — расширения пользователя, не layout
    харнесса. Машинная таблица сообщает
    `no_documented_mcp_client_config`.

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `plugin` | plugin может *нести* клиентский конфиг `.mcp.json`; пакет сервера всё равно `mcp` |
| `setting` | Codex, OpenCode и Grok Build держат клиентские серверы в файле, который также объявлен как `setting` |
| `skill` | skill объясняет, когда и как пользоваться tool; MCP — сам интерфейс tool |
| `instruction` | постоянные правила про tools остаются текстом; они не запускают сервер |
| `hook` | hook срабатывает на событии; MCP ждёт вызова как tool |
| `command` | command — именованный shortcut; MCP — поверхность протокола |
| `agent` | роли могут разрешить вызывать MCP-tools; сервер — не роль |

Выбирайте `mcp`, когда агент должен вызывать внешний tool через MCP.
Выбирайте `plugin`, когда вы поставляете пакет харнесса, который может
включать клиентский конфиг. Выбирайте `setting`, когда закрепляете
параметры, которые не являются записями серверов.

## Рекомендуемая структура пакета

`--language` для MCP-**сервера** — одно из `python`, `typescript`,
`javascript`, `rust`, `go` или `dart-flutter`. Вид исполняемый.

Пакет MCP-**сервера** не принадлежит ни одному харнессу
(`harness_id=null`). Discovery не угадывает по подстроке `mcp`. Он
требует согласованную цепочку:

- **Python:** `pyproject.toml` → зависимость MCP SDK → `project.scripts`
  → точный import модуля SDK.
- **TypeScript:** `package.json` → зависимость SDK → `bin` / script
  source → точный import SDK.

```text
github-issues/                     # опубликованный пакет сервера
├── pyproject.toml                 # dependencies включают mcp или fastmcp
└── src/
    └── github_issues/
        └── server.py              # цель project.scripts; импортирует SDK
```

```text
github-issues/                     # пакет сервера TypeScript
├── package.json                   # @modelcontextprotocol/sdk или fastmcp
└── src/
    └── index.ts                   # вход bin/script; импортирует SDK
```

Когда вы начинаете из `ai_stp`, сначала сделайте scaffold. Авторский
каталог шире опубликованного пакета: `discover` / `adopt` переносят
`source/` для portable и `projections/<harness>/` для конкретного харнесса,
а не всё дерево. Scaffold кладёт `source/mcp.json` и языковой entry;
обнаруживаемому **серверу** всё равно нужна цепочка манифеста выше.
Claude Code `mcp` отклоняется: у provider нет собственной MCP-поверхности.

```text
github-issues/                     # component-scaffold/3
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    ├── mcp.json
    └── src/main.py                # python handler; добавьте манифест пакета
```

```bash
ai-stp component scaffold plan \
  --type mcp \
  --language python \
  --harness portable \
  --name github-issues \
  --output ./github-issues \
  --json

ai-stp component scaffold apply \
  --type mcp \
  --language python \
  --harness portable \
  --name github-issues \
  --output ./github-issues \
  --expected-plan-digest <digest> \
  --json
```

Для `required_env` в паспорт записывайте имена и назначение, никогда
значения. Секреты, токены и пароли в паспорт не попадают.

Команды `ai-stp component mcp validate` нет. Структурная готовность —
`component passport validate`. Kind-specific проверка по спецификации
есть только у [`skill`](https://ai-stp.aiguild.space/ru/docs/components).

## Стандарты и фреймворки

- [Model Context Protocol](https://modelcontextprotocol.io) — независимый
  стандарт.
- Руководство по сборке сервера, которое discovery использует как
  `layout_source` пакетов сервера:
  [Build an MCP server](https://modelcontextprotocol.io/docs/develop/build-server).
- Имена SDK, которые discovery примет в цепочке зависимостей: Python
  `mcp` или `fastmcp`; TypeScript `@modelcontextprotocol/sdk` или
  `fastmcp`.
- NVIDIA SkillSpector и Cisco Skill Scanner — сканеры skill. Они не
  проверяют MCP.

Клиентские layout объявлены по харнессам. Ссылайтесь на `layout_source`
находки, а не угадывайте путь вендора.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть `layout_source`.
Если классификация неясна, покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | да | да | внутренний `.mcp.json` plugin — `mcp_client_config`; discovery его не открывает |
| Codex | имена в `config.toml` | имена в `config.toml` | файл также является `setting`; ключ `mcp_servers`; существования недостаточно |
| Pi | нет | нет | пробел `no_documented_mcp_client_config`; файлы `mcp.json` — расширения пользователя |
| OpenCode | имена в `opencode.json` / `opencode.jsonc` | те же файлы | файл также является `setting`; ключ `mcp`; существования недостаточно |
| Grok Build | имена в `config.toml` | имена в `config.toml` | файл также является `setting`; ключ `mcp_servers`; существования недостаточно |
| Cursor | не выдумывается из соседнего каталога | не выдумывается из соседнего каталога | официальная схема plugin называет `mcpServers`; walker файл не изобретает |
| Antigravity | да | да | |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |
| (пакет сервера) | n/a | n/a | `harness_id=null`; цепочка Python или TypeScript как выше |

Codex, OpenCode и Grok Build держат клиентские серверы в файле, который
также объявлен как `setting`. Существования файла недостаточно: под
ключом должен быть объявлен хотя бы один сервер. Один файл может дать две
находки (`setting` + `mcp`). В `evidence_refs` попадают только **имена**
серверов (например `mcp_servers.github`). Значения рядом с именем —
command, аргументы, URL, headers, environment — не читаются и не
возвращаются.

`.mcp.json` plugin доказывает себя именем, поэтому discovery его не
открывает. Рабочие серверы Claude Code pack живут там; угадывать другой
home-файл — не layout.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

Если один путь одновременно `setting` и `mcp`, назовите `--kind` при
adopt. Не adopt'ьте файл дважды под угаданными видами.

## Версии — `X.Y`, не SemVer

Опубликованная версия MCP неизменяема и имеет вид `X.Y`. Патч-номера нет.
Изменение сервера, точки входа или клиентского объявления — новая версия.
Обновление MCP внутри сетапа — новая версия сетапа.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию. Мажорная линия — отдельная
граница доступа.

## Что проверяет `ai_stp`

Процент карточки каталога и разделение обязательных и необязательных
проверок объяснены на странице
[Проверки безопасности](https://ai-stp.aiguild.space/ru/docs/components). Для MCP ожидайте как
минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого;
- `mcp_config_static` (схема, политика транспорта, capability);
- языковой SAST и SCA, когда есть scripts и lockfiles.

Пройденное сканирование снижает известный риск. Это не гарантия, что
сервер безвреден. Обязательные проверки, которые провалились или не
смогли запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| `native_role` | клиентский конфиг — не сервер; сервер — не plugin |
| Требуемые permissions | MCP расширяет то, до чего агент может дотянуться |
| Как передаются секреты | имена в паспорте, значения в окружении или системном хранилище |
| Кто автор | verified-автор не делает сервер автоматически безопасным |
| Какой `X.Y` закреплён | обновление MCP создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

`author_verified` и `component_verified` независимы. Ни одно не является
гарантией безопасности.

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда со страниц CLI и всегда
`--json`. Исполняемый файл — `ai-stp` (пакет `ai-stp-cli`). Команд
`component inspect` и `setup show` нет. Единственный kind-specific
validate — `ai-stp component skill validate`.

**Именно этот вид:** команды `component mcp validate` нет. Используйте
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

Когда находка также является файлом setting:

```bash
ai-stp component adopt --path <source_path> --kind mcp --json
```

**Найти, выбрать, установить:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

MCP-компонент может быть embedded-членом compose-манифеста. См.
[Сетапы](https://ai-stp.aiguild.space/ru/docs/components).

## Как MCP-компонент проходит через `ai_stp`

=== "Автор"
    Автор публикует сервер или клиентский конфиг из публичного
    GitHub-источника или импортирует его локально. Версия закрепляет
    точный commit и подпуть. Секретные значения в дерево не входят.

=== "Каталог"
    Каталог показывает назначение, поддерживаемые харнессы, требуемые
    permissions, trusted status автора и независимый status самого
    компонента.

=== "Сборщик"
    Сборщик проверяет, что MCP-объект можно встроить в выбранный сетап и
    что его файловая структура подходит проекции provider.

=== "Provider"
    Provider регистрирует нативную клиентскую запись или поставляет пакет
    сервера только после плана, digest и подтверждения. Он не копирует
    токены из паспорта — их там нет.

## Красные флаги

- Обращение с `.mcp.json` plugin так, будто это пакет сервера.
- Открытие `.mcp.json` или MCP-блока настроек, чтобы «проверить» токены —
  discovery уже отказывается читать эти значения.
- Файлы `mcp.json` у Pi, выданные за layout харнесса
  (`no_documented_mcp_client_config`).
- `config.toml` / `opencode.json` без серверов под ключом, помеченные как
  MCP потому что файл существует.
- Незакреплённые запускатели `npx` / `uvx` или command/args/URL/headers/env,
  сохранённые в паспорте.
- Живые токены, закрытые ключи или тела `.env` в пакете.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `author_verified` как с `component_verified`.
- Сканеры skill, процитированные так, будто они проверили этот вид.

??? question "Можно ли MCP-компонент использовать без публикации"
    Да. Собственный, импортированный или точно закреплённый MCP-объект
    можно использовать после локальных проверок. Он от этого не становится
    platform-verified и должен быть показан именно как локальный или
    закреплённый объект (`local_owner_or_pinned`).

## Чеклист автора

1. Сделайте scaffold с `--type mcp` и настоящим `--language` (не `none`).
2. Для **сервера** соберите цепочку Python или TypeScript: манифест,
   зависимость SDK, объявленный вход, точный import SDK. Не запускайте
   сервер, чтобы его «доказать».
3. Для **клиентского конфига** держите значения с доступом вне артефакта.
   Записывайте только *имена* env.
4. Объявите в паспорте потребности в файловой системе, сети и
   учётных данных.
5. Запустите `ai-stp component discover --root . --json` и прочитайте
   `native_role`, `harness_id` и `layout_source`.
6. `component adopt --path <точный source_path>` — добавьте `--kind mcp`,
   когда файл также является setting.
7. Закрепите точный публичный GitHub commit и подпуть. Секретов в дереве
   нет.
8. `component passport validate` → `component version release`, чтобы
   выпустить неизменяемый `X.Y`.
9. Публикуйте через [путь публикации](https://ai-stp.aiguild.space/ru/docs/components). В сетапе
   закрепите этот `X.Y`.

Связанное: [Авторство](https://ai-stp.aiguild.space/ru/docs/components),
[Компоненты](https://ai-stp.aiguild.space/ru/docs/components), [`plugin`](https://ai-stp.aiguild.space/ru/docs/components), [`setting`](https://ai-stp.aiguild.space/ru/docs/components).
