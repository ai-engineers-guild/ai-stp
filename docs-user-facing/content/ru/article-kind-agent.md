---
type: article
slug: kind-agent
locale: ru
title: "Agent — именованная роль внутри сетапа"
description: "Расширенный разбор agent: специализация, входы, инструменты, ограничения и проверяемый результат."
published_at: 2026-09-04
tags: [component, agent]
draft: false
---

# `agent`

![Component type: agent](/content/illustrations/kind-agent.jpg)

`agent` описывает специализированную роль внутри харнесса: область
ответственности, входы, ограничения, инструменты, которыми она может
пользоваться, и ожидаемый результат.

Agent отвечает на вопрос: **какая именованная роль должна нести этот
класс работы?**

Он не отвечает «как эта роль должна делать работу?» ([`skill`](https://ai-stp.aiguild.space/ru/docs/components)),
«какие постоянные правила относятся ко всем?»
([`instruction`](https://ai-stp.aiguild.space/ru/docs/components)) и «какой пакет расширяет харнесс?»
([`plugin`](https://ai-stp.aiguild.space/ru/docs/components)).

Agent-компонент не является отдельным сетапом. Он входит в сетап одного
харнесса и наследует его границы.

!!! warning "Вид `agent` — не AGENTS.md и не CLI Agent Skill"

    Файл с именем `AGENTS.md` — кросс-харнесс соглашение об
    **instruction**. Вид `agent` — определение роли, обычно файл под
    каталогом `agents/`.

    CLI также поставляет один канонический Agent Skill, который учит
    агента управлять самим `ai-stp`. Этот объект ставится командой
    [`ai-stp skill install`](https://ai-stp.aiguild.space/ru/docs/components). Это **не** компонент
    каталога и **не** этот вид.

    | Объект | Вид / семейство команд | Живёт в сетапе? |
    | --- | --- | --- |
    | Файл роли под `agents/` | вид `agent` (эта страница) | да |
    | `AGENTS.md` | [`instruction`](https://ai-stp.aiguild.space/ru/docs/components) | да |
    | CLI Agent Skill | `ai-stp skill install` / `status` / `remove` | нет |

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `skill` | skill — процедура; agent — роль, которая может использовать несколько skills |
| `instruction` | instruction — постоянный текст сессии; agent — именованная роль |
| `command` | command — shortcut; agent — кто (или какая роль) выполняет |
| `plugin` | plugin может *содержать* каталог `agents/`; каждый файл всё равно вид `agent` |
| `mcp` | MCP — интерфейс tool, который роли могут разрешить вызывать |
| `hook` | hook срабатывает на событии; agent ждёт, пока ему делегируют |
| `setting` | setting хранит параметры; agent хранит описание роли |

Выбирайте `agent`, когда нужна ограниченная роль с проверяемым
результатом. Выбирайте `skill`, когда нужна процедура, которой эта роль
будет следовать. Выбирайте `instruction`, когда текст применяется без
имени роли.

## Рекомендуемая структура пакета

`agent` декларативен. `--language` — `none`. Роль обычно — один
Markdown-файл. Claude Code авторит agents как файлы в directory-shaped
layout; adopt принимает этот одиночный файл без дополнительного
манифеста-обёртки.

Переносимый пакет (то, что `discover` / `adopt` переносят из `source/`):

```text
reviewer/
└── reviewer.md                    # {name}.md в корне пакета
```

Когда вы начинаете из `ai_stp`, сначала сделайте scaffold. Авторский
каталог шире опубликованного пакета: `discover` / `adopt` переносят
`source/` для portable и `projections/<harness>/` для конкретного харнесса,
а не всё дерево. Агенты Codex — TOML под `agents/`.

```text
reviewer/                          # component-scaffold/3
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    └── reviewer.md
```

```bash
ai-stp component scaffold plan \
  --type agent \
  --language none \
  --harness portable \
  --name reviewer \
  --output ./reviewer \
  --json

ai-stp component scaffold apply \
  --type agent \
  --language none \
  --harness portable \
  --name reviewer \
  --output ./reviewer \
  --expected-plan-digest <digest> \
  --json
```

`--language` для agent — `none`. Вид декларативный.

Опишите цель роли, инструменты, которыми она может пользоваться, как
выглядит готовый результат и когда её вызывать. Не описывайте глобальную
замену всех инструкций, секреты или право менять внешний мир без
подтверждения.

Команды `ai-stp component agent validate` нет. Структурная готовность —
`component passport validate`. Kind-specific проверка по спецификации
есть только у [`skill`](https://ai-stp.aiguild.space/ru/docs/components).

## Стандарты и фреймворки

Независимой спецификации роли agent, сравнимой с
[Agent Skills Specification](https://agentskills.io/specification), нет.
Skill — переносимый workflow; agent — роль.

Ссылайтесь на `layout_source` из `ai-stp component discover --json`,
когда классификация неясна. Custom agents Codex документированы только из
`.codex/agents` — не выдумывайте второй каталог.

NVIDIA SkillSpector и Cisco Skill Scanner — сканеры skill. Это не
валидатор этого вида.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть `layout_source`.
Если классификация неясна, покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | да | да | под `agents/`; внутри доказанного пакета `.claude-plugin/plugin.json` члены `agents/` — agents |
| Codex | нет | да | custom agents только из `.codex/agents`; доказанный пакет `.codex-plugin/plugin.json` не добавляет поддерево agents в контракте |
| Pi | нет | нет | agent layout не объявлен |
| OpenCode | да | да | |
| Grok Build | нет | нет | agent layout не объявлен |
| Cursor | через plugin pack | через plugin pack | agents читаются внутри доказанного пакета `.cursor-plugin/plugin.json` |
| Antigravity | да | да | |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |

Внутри доказанного Claude Code plugin discovery читает `agents` (каждый
потомок — один agent). Внутри доказанного Cursor plugin — то же самое.
Walker не изобретает файлы agent из соседнего каталога.

Одиночный файл в directory-shaped layout дополнительного манифеста не
требует — так авторят agents Claude Code, и adopt их принимает.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Версии — `X.Y`, не SemVer

Опубликованная версия agent неизменяема и имеет вид `X.Y`. Патч-номера нет.
Изменение текста роли, её инструментов или ограничений — новая версия.
Обновление agent внутри сетапа — новая версия сетапа.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию. Мажорная линия — отдельная
граница доступа.

## Что проверяет `ai_stp`

Процент карточки каталога и разделение обязательных и необязательных
проверок объяснены на странице
[Проверки безопасности](https://ai-stp.aiguild.space/ru/docs/components). Для agent ожидайте как
минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого;
- языковой SAST и SCA, когда есть scripts и lockfiles.

Пройденное сканирование снижает известный риск. Это не гарантия, что роль
безвредна. Обязательные проверки, которые провалились или не смогли
запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| Scope роли | размытая роль становится «делай всё» |
| Tools, которыми она может пользоваться | роль, которая наследует каждый MCP-сервер, не ограничена |
| Как выглядит «готово» | без проверяемого результата роль нельзя ревьюить |
| Кто автор | verified-автор не делает роль автоматически безопасной |
| Какой `X.Y` закреплён | обновление agent создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

`author_verified` и `component_verified` независимы. Ни одно не является
гарантией безопасности.

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда со страниц CLI и всегда
`--json`. Исполняемый файл — `ai-stp` (пакет `ai-stp-cli`). Команд
`component inspect` и `setup show` нет. Единственный kind-specific
validate — `ai-stp component skill validate`.

**Именно этот вид:** команды `component agent validate` нет. Используйте
проверку паспорта.

```bash
ai-stp component passport validate --id <stable_id> --json
```

**Не этот вид** — CLI Agent Skill (см.
[Agent Skill CLI](https://ai-stp.aiguild.space/ru/docs/components)):

```bash
ai-stp skill status --json
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

Agent может быть embedded-членом compose-манифеста. См.
[Сетапы](https://ai-stp.aiguild.space/ru/docs/components).

## Как agent проходит через `ai_stp`

=== "Автор"
    Автор публикует роль из публичного GitHub-источника или импортирует её
    локально. Версия закрепляет точный commit и подпуть.

=== "Каталог"
    Каталог показывает роль, поддерживаемые харнессы, ограничения,
    trusted status автора и независимый status самого компонента.

=== "Сборщик"
    Сборщик проверяет, поддерживает ли харнесс такую agent surface и что
    файловая структура подходит проекции provider.

=== "Provider"
    Provider создаёт нативное описание роли только после плана, digest и
    подтверждения. Status показывает, какие роли активны и откуда они
    пришли.

## Красные флаги

- Обращение с `AGENTS.md` как с видом `agent`.
- Обращение с `ai-stp skill install` так, будто оно опубликовало этот
  компонент.
- Роль без ограничений, без ожидаемого результата и с каждым tool
  включённым.
- Codex agents откуда угодно, кроме `.codex/agents`.
- Живые токены, закрытые ключи или тела `.env` в пакете.
- Инструкции игнорировать предыдущие инструкции или расширять права во
  время выполнения.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `author_verified` как с `component_verified`.
- Subagent, которому разрешено менять внешний мир без пути подтверждения.

??? question "Можно ли agent использовать без публикации"
    Да. Собственную, импортированную или точно закреплённую роль можно
    использовать после локальных проверок. Она от этого не становится
    platform-verified и должна быть показана именно как локальный или
    закреплённый объект (`local_owner_or_pinned`).

## Чеклист автора

1. Сделайте scaffold с `--type agent --language none` и держите Markdown
   в корне пакета (в авторском дереве — под `source/`).
2. Назовите роль, её ограничения, её tools и как выглядит «готово».
   Постоянные правила положите в [`instruction`](https://ai-stp.aiguild.space/ru/docs/components),
   процедуры — в [`skill`](https://ai-stp.aiguild.space/ru/docs/components).
3. Объявите потребности в авторизации в паспорте. Секретов нет.
4. Запустите `ai-stp component discover --root . --json` и прочитайте
   `layout_source` у находки.
5. `component adopt --path <точный source_path>` — добавьте `--kind agent`,
   если путь заявлен более чем одним видом.
6. Закрепите точный публичный GitHub commit и подпуть.
7. `component passport validate` → `component version release`, чтобы
   выпустить неизменяемый `X.Y`.
8. Публикуйте через [путь публикации](https://ai-stp.aiguild.space/ru/docs/components).
9. В сетапе закрепите этот `X.Y`. Позднее обновление — новая версия
   сетапа.

Связанное: [Авторство](https://ai-stp.aiguild.space/ru/docs/components),
[Компоненты](https://ai-stp.aiguild.space/ru/docs/components), [`instruction`](https://ai-stp.aiguild.space/ru/docs/components),
[`skill`](https://ai-stp.aiguild.space/ru/docs/components), [CLI Agent Skill](https://ai-stp.aiguild.space/ru/docs/components).
