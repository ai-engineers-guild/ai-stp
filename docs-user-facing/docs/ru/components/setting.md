---
title: "setting"
description: "Setting-компоненты: параметры и режимы, никогда секреты; иногда тот же файл, что и MCP."
---

# `setting`

`setting` — конфигурационная часть сетапа: параметры, режимы, feature
flags, preferences, thresholds и другие значения, которые харнесс или
provider умеет применять.

Setting отвечает на вопрос: **какие несекретные параметры нужно
закрепить?**

Он не отвечает «какое постоянное правило агент должен помнить?»
([`instruction`](instruction.md)), «что должно выполниться на событии?»
([`hook`](hook.md)) и «какие MCP-серверы объявлены в этом же файле?»
(эта находка — вид [`mcp`](mcp.md), `native_role`
`mcp_client_config`).

Setting не должен хранить секреты. Если значение является token,
password, private key или credential, оно идёт через поддерживаемое
хранилище секретов, а не через паспорт компонента.

!!! warning "Один файл может быть setting и MCP-находкой"

    Codex, OpenCode и Grok Build держат клиентские MCP-серверы в файле,
    который также объявлен как `setting`:

    | Харнесс | Файл | Ключ MCP |
    | --- | --- | --- |
    | Codex | `config.toml` | `mcp_servers` |
    | OpenCode | `opencode.json` / `opencode.jsonc` | `mcp` |
    | Grok Build | `config.toml` | `mcp_servers` |

    Существование файла доказывает **setting**, никогда серверы. Файл
    становится находкой `mcp` только когда под этим ключом объявлен хотя
    бы один сервер. Один файл может дать две находки разных видов. Adopt
    с `--kind`, когда путь заявлен обоими.

    В `evidence_refs` читаются только **имена** серверов. Значения
    (command, args, URL, headers, env) никогда не читаются.

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `instruction` | instruction — проза; setting — типизированный параметр |
| `mcp` | MCP-серверы могут жить *внутри* того же файла; они всё равно вид `mcp` |
| `hook` | hook — действие; setting не срабатывает |
| `command` | command вызывается; setting применяется |
| `plugin` | plugin — пакет; setting — конфигурация |
| `skill` | skill — workflow; setting — нет |
| `agent` | agent — роль; setting — нет |

Выбирайте `setting`, когда значение читает provider или CLI. Выбирайте
`instruction`, когда агенту нужно сказать прозой. Выбирайте `hook` или
`command`, если значение запускает действие.

## Рекомендуемая структура пакета

`setting` декларативен. `--language` — `none`. `setting` требует
конкретный харнесс: portable отклоняется. Claude Code проецирует
`settings.json`; Codex и Grok — `config.toml`; OpenCode — `opencode.json`.

```text
strict-mode/                       # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
├── source/
│   └── settings.json
└── projections/claude-code/
    └── settings.json
```

```bash
ai-stp component scaffold plan \
  --type setting \
  --language none \
  --harness claude-code \
  --name strict-mode \
  --output ./strict-mode \
  --json

ai-stp component scaffold apply \
  --type setting \
  --language none \
  --harness claude-code \
  --name strict-mode \
  --output ./strict-mode \
  --expected-plan-digest <digest> \
  --json
```

`--language` для setting — `none`. Вид декларативный.

В артефакт кладите только значения, которые можно хранить:

| Можно | Нельзя |
| --- | --- |
| режим выполнения | API token |
| язык интерфейса | password |
| policy flag | private key |
| лимит или threshold | содержимое `.env` |
| путь внутри target, если он не секретный | OAuth refresh token |

Для `required_env` в паспорт записывайте имена и назначение, никогда
значения.

Команды `ai-stp component setting validate` нет. Структурная готовность —
`component passport validate`. Kind-specific проверка по спецификации
есть только у [`skill`](skill.md).

## Стандарты и фреймворки

Независимой спецификации setting, сравнимой с
[Agent Skills Specification](https://agentskills.io/specification) или с
[MCP](https://modelcontextprotocol.io), нет. Каждый харнесс документирует
свой файл конфигурации.

Ссылайтесь на `layout_source` из `ai-stp component discover --json`,
когда классификация неясна. Не угадывайте путь соседа и не считайте файл
настроек MCP только потому, что он существует.

NVIDIA SkillSpector и Cisco Skill Scanner — сканеры skill. Они не
проверяют settings.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть `layout_source`.
Если классификация неясна, покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | да | да | |
| Codex | да | да | `config.toml` может также дать находку `mcp`, когда заполнен `mcp_servers` |
| Pi | да | да | |
| OpenCode | да | да | `opencode.json` / `opencode.jsonc` могут также дать находку `mcp`, когда заполнен `mcp` |
| Grok Build | да | да | `config.toml` может также дать находку `mcp`, когда заполнен `mcp_servers` |
| Cursor | да | нет | global setting в ограниченной матрице; project setting — не объявленная ячейка |
| Antigravity | да | нет | global setting в ограниченной матрице |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |

Объявленный путь всё равно принадлежит недоверенной машине. Discovery не
читает секретные значения из файла настроек, чтобы их «проверить».

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

Если один путь отвечает более чем одному виду, назовите `--kind` при
adopt.

```bash
ai-stp component adopt --path <source_path> --kind setting --json
```

## Версии — `X.Y`, не SemVer

Опубликованная версия setting неизменяема и имеет вид `X.Y`. Патч-номера
нет. Изменение флага, режима или threshold — новая версия. Обновление
setting внутри сетапа — новая версия сетапа.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию. Мажорная линия — отдельная
граница доступа.

## Что проверяет `ai_stp`

Процент карточки каталога и разделение обязательных и необязательных
проверок объяснены на странице
[Проверки безопасности](../security-checks.md). Для setting ожидайте как
минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого.

Пройденное сканирование снижает известный риск. Это не гарантия, что
конфигурация безвредна. Обязательные проверки, которые провалились или не
смогли запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| Ключи, похожие на секрет | setting — не место, чтобы прятать токены |
| Diff значений | дрейф конфигурации — как поведение меняется без нового skill |
| Двойные находки | тот же файл может быть и клиентским конфигом MCP |
| Кто автор | verified-автор не делает значения автоматически безопасными |
| Какой `X.Y` закреплён | обновление setting создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

`author_verified` и `component_verified` независимы. Ни одно не является
гарантией безопасности.

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда со страниц CLI и всегда
`--json`. Исполняемый файл — `ai-stp` (пакет `ai-stp-cli`). Команд
`component inspect` и `setup show` нет. Единственный kind-specific
validate — `ai-stp component skill validate`.

**Именно этот вид:** команды `component setting validate` нет.
Используйте проверку паспорта.

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

Setting может быть embedded-членом compose-манифеста. См.
[Сетапы](../setups/index.md).

## Как setting проходит через `ai_stp`

=== "Автор"
    Автор публикует setting из публичного GitHub-источника или импортирует
    его локально. Версия закрепляет точный commit и подпуть. Секретные
    значения в дерево не входят.

=== "Каталог"
    Каталог показывает параметры, поддерживаемые харнессы, ограничения,
    trusted status автора и независимый status самого компонента.

=== "Сборщик"
    Сборщик проверяет конфликты с другими компонентами сетапа и что
    файловая структура подходит проекции provider.

=== "Provider"
    Provider показывает diff конфигурации и пишет нативную поверхность
    только после плана, digest и подтверждения.

## Красные флаги

- Токены, пароли, закрытые ключи, OAuth refresh token или тела `.env` в
  setting, паспорте или примерах README.
- Setting как удобное место для workflow, hook или command.
- Пометка `config.toml` / `opencode.json` как MCP потому что файл
  существует, когда ключ MCP пуст.
- Открытие MCP-блока файла настроек, чтобы скопировать command, args,
  URL, headers или env в паспорт.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `author_verified` как с `component_verified`.
- Копирование файла настроек в target в обход плана provider.

??? question "Можно ли setting использовать без публикации"
    Да. Собственный, импортированный или точно закреплённый setting можно
    использовать после локальных проверок. Он от этого не становится
    platform-verified и должен быть показан именно как локальный или
    закреплённый объект (`local_owner_or_pinned`). Секреты в нём по-прежнему
    не место.

## Чеклист автора

1. Сделайте scaffold с `--type setting --language none` и держите
   нативный файл под `source/`.
2. Храните только несекретные параметры. Записывайте *имена* env в
   паспорт, если харнессу позже понадобится учётная запись.
3. Если файл также объявляет MCP-серверы, считайте это отдельной находкой
   [`mcp`](mcp.md). Не кладите значения серверов в этот артефакт.
4. Объявите в паспорте, что меняют значения.
5. Запустите `ai-stp component discover --root . --json` и прочитайте
   `layout_source`, а также `native_role`, если появится вторая находка.
6. `component adopt --path <точный source_path>` — добавьте
   `--kind setting`, когда путь также является MCP.
7. Закрепите точный публичный GitHub commit и подпуть. Секретов в дереве
   нет.
8. `component passport validate` → `component version release`, чтобы
   выпустить неизменяемый `X.Y`.
9. Публикуйте через [путь публикации](../publishing/index.md). В сетапе
   закрепите этот `X.Y`.

Связанное: [Авторство](../publishing/authoring.md),
[Компоненты](index.md), [`mcp`](mcp.md), [`instruction`](instruction.md).
