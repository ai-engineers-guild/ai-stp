---
title: "instruction"
description: "Instruction-компоненты: постоянные правила, память и текстовые ограничения для харнесса."
---

# `instruction`

`instruction` — постоянный текст, который формирует решения агента:
правила, проектная память, стиль работы, границы полномочий и заметки
харнесса, которые не являются workflow, shortcut или пакетом.

Instruction отвечает на вопрос: **что агент должен держать в уме, пока
работает?**

Он не отвечает «как агент должен делать этот класс задач?»
([`skill`](skill.md)), «какой именованный shortcut набрать?»
([`command`](command.md)) и «какая специализированная роль должна
выполнять работу?» ([`agent`](agent.md)).

!!! warning "AGENTS.md — это instruction, а не `agent`"

    Файл с именем `AGENTS.md` — кросс-харнесс соглашение об инструкции.
    Вид `agent` — определение роли. Discovery не считает `AGENTS.md`
    ролью и не считает файл роли постоянными правилами.

    `CODEX.md` — **не** документированный layout инструкции Codex.
    Discovery возвращает его как `unsupported_manifest` и указывает на
    `AGENTS.md`.

    Память, правила, preferences и проектные договорённости — *содержимое*
    `instruction` (или [`setting`](setting.md)). Вида `memory` нет.

    | Объект | Вид | Живёт в сетапе? |
    | --- | --- | --- |
    | `AGENTS.md` / `CLAUDE.md` / текст rules | `instruction` | да |
    | Именованная роль под `agents/` | `agent` | да |
    | CLI Agent Skill (`ai-stp skill …`) | не этот вид | нет |

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `skill` | skill — повторяемая процедура с сопроводительными файлами; instruction — постоянный контекст |
| `command` | command вызывается по имени; instruction уже есть в сессии |
| `agent` | agent — роль, которая *использует* инструкции; instruction — текст, а не роль |
| `plugin` | plugin расширяет харнесс; instruction расширяет список чтения агента |
| `mcp` | MCP подключает tool; instruction может лишь *сказать*, когда этим tool пользоваться |
| `hook` | hook срабатывает на событии жизненного цикла; instruction не исполняется |
| `setting` | setting хранит параметры; instruction хранит прозу |

Выбирайте `instruction`, когда агент должен следовать постоянным правилам
без приложенной процедуры. Выбирайте `skill`, когда у работы есть шаги,
scripts или references. Выбирайте `command`, когда человек должен начать
работу по имени.

## Рекомендуемая структура пакета

`instruction` декларативен. `--language` — `none`. Независимой
спецификации instruction, сравнимой с
[Agent Skills Specification](https://agentskills.io/specification), нет;
тело — Markdown, который харнесс загрузит как контекст.

Переносимый пакет (то, что `discover` / `adopt` переносят из `source/`):

```text
project-conventions/
└── AGENTS.md
```

Когда вы начинаете из `ai_stp`, сначала сделайте scaffold. Авторский
каталог шире опубликованного пакета: `discover` / `adopt` переносят
`source/` для portable и `projections/<harness>/` для конкретного харнесса,
а не всё дерево.

```text
project-conventions/                 # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    └── AGENTS.md
```

`source/AGENTS.md` — канон. Проекция Claude Code — `CLAUDE.md`; Cursor —
`rules/<name>.mdc`. Не выдумывайте второй каталог-обёртку.

```bash
ai-stp component scaffold plan \
  --type instruction \
  --language none \
  --harness portable \
  --name project-conventions \
  --output ./project-conventions \
  --json

ai-stp component scaffold apply \
  --type instruction \
  --language none \
  --harness portable \
  --name project-conventions \
  --output ./project-conventions \
  --expected-plan-digest <digest> \
  --json
```

`--language` для instruction — `none`. Вид декларативный.

Adopt принимает только путь, который discovery уже назвал. У каталога
должен быть манифест из закрытого набора (`SKILL.md`, `AGENTS.md`,
`plugin.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `hooks.json`, `package.json` или
`pyproject.toml`). Одиночный файл в file-shaped layout — в том числе
`AGENTS.md` — и есть компонент; дополнительная обёртка не нужна.

Команды `ai-stp component instruction validate` нет. Структурная
готовность — `component passport validate`. Kind-specific проверка по
спецификации есть только у [`skill`](skill.md).

## Стандарты и фреймворки

- [AGENTS.md](https://agents.md) — кросс-продуктовый файл инструкции.
  Discovery считает `AGENTS.md` в корне проекта instruction, а не видом
  `agent`.
- Страницы харнесса, которые объявили layout, появляются у каждой находки
  как `layout_source` из `ai-stp component discover --json`. Если
  классификация неясна, покажите это поле; не угадывайте путь соседа.
- Сравнивайте с [Agent Skills Specification](https://agentskills.io/specification),
  когда хочется положить workflow в instruction: процедура с `SKILL.md` —
  это `skill`.

Не выдумывайте вид `memory`, вид `rules` или extra frontmatter, который
случайно показывает UI харнесса. Это содержимое этого вида или
`setting`.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть
`layout_source` — официальный документ, который объявил layout. Если
классификация неясна, покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | да | да | постоянный текст; каталог под `skills/` с plugin-манифестом — это **plugin**, не instruction |
| Codex | да | да | `CODEX.md` — `unsupported_manifest`; используйте `AGENTS.md` |
| Pi | да | нет | в ограниченной матрице только global instruction |
| OpenCode | нет | нет | instruction в ограниченной матрице не объявлен |
| Grok Build | нет | нет | instruction в ограниченной матрице не объявлен |
| Cursor | да | да | внутри доказанного пакета `.cursor-plugin/plugin.json` каждый файл под `rules/` — instruction |
| Antigravity | нет | нет | instruction в ограниченной матрице не объявлен |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |

Внутри доказанного Cursor plugin discovery читает `rules` и классифицирует
каждый файл как `instruction`. Он не выдумывает файлы instruction из
соседнего каталога.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

Если один путь отвечает более чем одному харнессу, назовите `--harness`
при adopt. Для общей кросс-продуктовой претензии используйте `portable`.

## Версии — `X.Y`, не SemVer

Опубликованная версия instruction неизменяема и имеет вид `X.Y`.
Патч-номера нет. Изменение Markdown — новая версия. Обновление
instruction внутри сетапа — новая версия сетапа.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` открывает следующую мажорную линию. Мажорная линия — отдельная
граница доступа.

## Что проверяет `ai_stp`

Процент карточки каталога и разделение обязательных и необязательных
проверок объяснены на странице
[Проверки безопасности](../security-checks.md). Для instruction ожидайте
как минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого (`pi_content_pack`,
  `content_hidden`).

Пройденное сканирование снижает известный риск. Это не гарантия, что
текст безвреден. Обязательные проверки, которые провалились или не смогли
запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| Diff прозы | instruction может незаметно расширить полномочия |
| Совместимость с харнессом | Claude-специфичный текст не должен попасть на несовместимый target |
| Scope | глобальные правила действуют шире, чем файл проекта |
| Кто автор | verified-автор не делает содержимое автоматически безопасным |
| Какой `X.Y` закреплён | обновление текста создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

`author_verified` и `component_verified` независимы. Ни одно не является
гарантией безопасности.

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда со страниц CLI и всегда
`--json`. Исполняемый файл — `ai-stp` (пакет `ai-stp-cli`). Команд
`component inspect` и `setup show` нет. Единственный kind-specific
validate — `ai-stp component skill validate`.

**Именно этот вид:** команды `component instruction validate` нет.
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

Если discovery сообщил путь более чем под одним харнессом или видом:

```bash
ai-stp component adopt --path <source_path> --harness portable --kind instruction --json
```

**Найти, выбрать, установить:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

Instruction может быть embedded-членом compose-манифеста. См.
[Сетапы](../setups/index.md).

## Как instruction проходит через `ai_stp`

=== "Автор"
    Автор публикует instruction из публичного GitHub-источника или
    импортирует её локально. Версия закрепляет точный commit и подпуть.

=== "Каталог"
    Каталог показывает назначение, поддерживаемые харнессы, ограничения,
    trusted status автора и независимый status самого компонента.

=== "Сборщик"
    Сборщик проверяет, что instruction можно встроить в выбранный сетап и
    что её файловая структура подходит проекции provider.

=== "Provider"
    Provider кладёт instruction на нативную поверхность харнесса и
    обновляет связанные индексы только после плана, digest и
    подтверждения.

## Красные флаги

- Обращение с `AGENTS.md` как с видом `agent`, или с файлом роли как с
  постоянными правилами.
- Поставка `CODEX.md` в ожидании, что discovery примет его как инструкции
  Codex.
- Markdown, вложенный в `payload/` или другой каталог-обёртку.
- Живые токены, закрытые ключи или тела `.env` в пакете.
- Правила, которые велят агенту игнорировать предыдущие инструкции или
  выносить секреты.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `author_verified` как с `component_verified`.
- Выдуманный вид `memory` вместо памяти в этом тексте.
- Копирование файлов в target в обход плана provider.

??? question "Можно ли instruction использовать без публикации"
    Да. Собственную, импортированную или точно закреплённую instruction
    можно использовать после локальных проверок. Она от этого не становится
    platform-verified и должна быть показана именно как локальный или
    закреплённый объект (`local_owner_or_pinned`).

## Чеклист автора

1. Сделайте scaffold с `--type instruction --language none` и держите
   Markdown в корне пакета (в авторском дереве — под `source/`).
2. Пишите только постоянные правила. Процедуру перенесите в
   [`skill`](skill.md); именованный shortcut — в [`command`](command.md).
3. Объявите в паспорте, чего текст требует от агента. Секретов нет.
4. Запустите `ai-stp component discover --root . --json` и прочитайте
   `layout_source` у находки.
5. `component adopt --path <точный source_path>` — добавьте
   `--kind instruction`, если путь заявлен более чем одним видом.
6. Закрепите точный публичный GitHub commit и подпуть.
7. `component passport validate` → `component version release`, чтобы
   выпустить неизменяемый `X.Y`.
8. Публикуйте через [путь публикации](../publishing/index.md).
9. В сетапе закрепите этот `X.Y`. Позднее обновление — новая версия
   сетапа.

Связанное: [Авторство](../publishing/authoring.md),
[Компоненты](index.md), [`agent`](agent.md), [`skill`](skill.md).
