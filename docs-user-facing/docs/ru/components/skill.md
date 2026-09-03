---
title: "skill"
description: "Skill-компоненты: повторяемые workflows для агента, отдельно от Agent Skill CLI."
---

# `skill`

`skill` — переносимый агентский workflow. Обычно он содержит `SKILL.md`,
инструкции, references, assets и иногда scripts, которые помогают агенту
выполнить специализированную задачу без угадывания процесса.

Skill отвечает на вопрос: **как агент должен делать этот класс задач?**

Он не отвечает «какой именованный shortcut набрать?» (`command`), «какой
внешний tool подключён?» (`mcp`) и «какой пакет расширяет харнесс?»
(`plugin`).

!!! warning "Два разных объекта с именем skill"

    Эта страница — **вид компонента** `skill`, который входит в сетап.

    CLI также поставляет один канонический Agent Skill, который учит агента
    управлять самим `ai-stp`. Этот объект ставится командой
    [`ai-stp skill install`](../cli/skill.md), проверяется через
    `ai-stp skill status` и снимается через `ai-stp skill remove`. Это
    **не** компонент каталога, его **не** выбирают в сетап, и
    `ai-stp component skill validate` — **не** этот установщик.

    | Объект | Семейство команд | Живёт в сетапе? |
    | --- | --- | --- |
    | Вид `skill` (эта страница) | `component …`, `select`, `install` | да |
    | CLI Agent Skill | `ai-stp skill install` / `status` / `remove` | нет |

## Соседи

| Вид | Главное отличие |
| --- | --- |
| `instruction` | даёт общие правила и контекст и не обязан описывать workflow |
| `command` | запускается как именованный shortcut, а skill активируется по смыслу задачи |
| `plugin` | расширяет сам харнесс, а skill расширяет рабочее поведение агента |
| `mcp` | даёт инструментальный интерфейс, а skill объясняет, когда и как им пользоваться |
| `hook` | срабатывает на событии жизненного цикла, а skill ждёт, пока его выберут для задачи |
| `agent` | называет роль, которая может использовать несколько skills; skill — процедура, не роль |
| `setting` | хранит параметры, а не workflow |

Выбирайте `skill`, когда агент должен следовать повторяемой процедуре с
сопроводительными файлами. Выбирайте `instruction`, когда нужны только
постоянные правила. Выбирайте `command`, когда человек или агент должен
вызвать работу по имени.

## Рекомендуемая структура пакета

Из восьми видов независимая спецификация есть только у `skill`: Agent
Skills Specification. `SKILL.md` должен лежать в **корне пакета**. Обёртка
`payload/SKILL.md` не соответствует стандарту для любого читателя, который
реализует спецификацию, а не локальный layout.

```text
playwright-checks/
├── SKILL.md              обязательно: YAML frontmatter и инструкции
├── scripts/              необязательно, по соглашению
├── references/           необязательно, по соглашению
├── assets/               необязательно, по соглашению
├── evals/                допустимое расширение; в отчёте отдельно
└── tests/                допустимое расширение; не отказ
```

Имя каталога должно совпадать с полем `name` во frontmatter.

Когда вы начинаете из `ai_stp`, сначала сделайте scaffold. Авторский
каталог шире опубликованного пакета: `discover` / `adopt` переносят
`native/`, а не всё дерево.

```text
playwright-checks/                 # component-scaffold/2
├── .ai-stp-template.json
├── authoring-template.md
├── component-passport.json
├── eval-profile.json
├── README.md
├── SAFETY.md
├── PUBLICATION.md
└── native/
    └── SKILL.md
```

```bash
ai-stp component scaffold plan \
  --type skill \
  --language none \
  --harness portable \
  --name playwright-checks \
  --output ./playwright-checks \
  --json

ai-stp component scaffold apply \
  --type skill \
  --language none \
  --harness portable \
  --name playwright-checks \
  --output ./playwright-checks \
  --expected-plan-digest <digest> \
  --json
```

`--language` для skill — `none`. Вид декларативный.

### Frontmatter, который примет валидатор

| Поле | Обязательно | Ограничение |
| --- | --- | --- |
| `name` | да | 1–64 символа; строчные буквы, цифры и дефисы; не начинается и не заканчивается дефисом; без двойных дефисов; совпадает с именем каталога |
| `description` | да | 1–1024 символа, непустое |
| `license` | нет | стандарт не задаёт дополнительного лимита |
| `compatibility` | нет | 1–500 символов |
| `metadata` | нет | отображение строк в строки |
| `allowed-tools` | нет | строка через пробел; experimental |

Ключ верхнего уровня, который стандарт не определяет, сообщается как
`SK033`. Свойства конкретного клиента кладите в `metadata`. Тело после
frontmatter на формат не проверяется: спецификация говорит, что ограничений
формата нет.

Проверяйте форму установленного пакета, а не авторское дерево:

```bash
ai-stp component skill validate --path ./playwright-checks/native --json
```

Команда только читает. Она называет каждое отклонение кодом `SKxxx`. Она
не делает adopt, не публикует и не пишет target.

## Стандарты и фреймворки

- [Agent Skills Specification](https://agentskills.io/specification) —
  независимый стандарт. `ai-stp component skill validate` реализует эту
  границу, а не внутренний стиль дома.
- Сканеры безопасности, которые используются при публикации, если
  доступны: [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector)
  и [Cisco Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner).
  Недоступный движок никогда не становится прохождением. См.
  [Проверки безопасности](../security-checks.md).

Не выдумывайте дополнительные поля frontmatter только потому, что их
показывает UI харнесса. Заметки, специфичные для харнесса, кладите в
`metadata`.

## Нативные layout по харнессам

Discovery сообщает только объявленные layout. Точные пути на машине даёт
`ai-stp component discover --json`. У каждой находки есть `layout_source` —
официальный документ, который объявил layout. Если классификация неясна,
покажите это поле; не угадывайте путь соседа.

Из матрицы discovery:

| Харнесс | Global | Project | Что есть в контракте discovery |
| --- | --- | --- | --- |
| Claude Code | да | да | в `skills/` каталог с `SKILL.md` — это skill; каталог с `.claude-plugin/plugin.json` или `plugin.json` — это **plugin** |
| Codex | общий skill | общий skill | общие `.agents/skills` не принадлежат харнессу (`harness_id=null`) |
| Pi | да | да | |
| OpenCode | да | да | |
| Grok Build | да | да | |
| Cursor | через plugin pack | через plugin pack | skills читаются внутри доказанного пакета `.cursor-plugin/plugin.json` |
| Antigravity | да | да | |
| `undefined` | переносимые соглашения | переносимые соглашения | это не харнесс; автоматическая установка не считается безопасной |

Общие `.agents/skills` возвращаются один раз, а не дублируются под каждым
совместимым харнессом.

`nori.json` Nori или `.agents/.skill-lock.json` (версия 3) могут уточнить
уже найденный путь. Они не создают skill из отсутствующего каталога и не
делают внешний манифест источником подтверждённых фактов паспорта.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Версии — `X.Y`, не SemVer

Опубликованная версия skill неизменяема и имеет вид `X.Y`. Патч-номера нет.
Изменение `SKILL.md`, скрипта или asset — новая версия. Обновление skill
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
[Проверки безопасности](../security-checks.md). Для skill ожидайте как
минимум:

- структуру, digest, лицензию, tags, исходный репозиторий;
- ограниченную распаковку и path denylist;
- сканирование секретов (`secrets_heuristic` и Gitleaks, если включён);
- правила prompt-injection и скрытого содержимого;
- `skill_static_gate` (собственные правила плюс SkillSpector и Skill
  Scanner, когда они доступны);
- языковой SAST и SCA, если есть scripts и lockfiles.

Пройденное сканирование снижает известный риск. Это не гарантия, что
workflow безвреден. Обязательные проверки, которые провалились или не
смогли запуститься, блокируют публикацию.

Перед установкой также смотрите:

| Проверка | Почему важно |
| --- | --- |
| Есть ли scripts | скрипты могут действовать вне Markdown |
| Есть ли references или assets | агенту нужен весь комплект, не только `SKILL.md` |
| Совместим ли харнесс | одинаковое имя skill не гарантирует одинаковый формат |
| Кто автор | verified-автор не делает содержимое автоматически безопасным |
| Какой `X.Y` закреплён | обновление skill создаёт новую версию сетапа |
| Линия доверия | `experimental` требует явного согласия |

## Связанные команды CLI

Только команды, которые существуют. Флаги всегда из
`ai-stp help --agent --json`.

**Именно этот вид:**

```bash
ai-stp component skill validate --path <directory> --json
```

**Не этот вид** — CLI Agent Skill (см.
[Agent Skill CLI](../cli/skill.md)):

```bash
ai-stp skill status --json
ai-stp skill install --target <dir> --json
ai-stp skill remove --target <dir> --json
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
ai-stp select eligibility --json
ai-stp install plan --json
```

Skill может быть и embedded-членом compose-манифеста. См.
[Сетапы](../setups/index.md).

## Как skill проходит через `ai_stp`

=== "Автор"
    Автор публикует skill из публичного GitHub-источника или импортирует
    его локально. Версия закрепляет точный commit и подпуть.

=== "Каталог"
    Каталог показывает назначение, поддерживаемые харнессы, ограничения,
    trusted status автора и независимый status самого компонента.

=== "Сборщик"
    Сборщик проверяет, что skill можно встроить в выбранный сетап и что
    его файловая структура подходит проекции provider.

=== "Provider"
    Provider кладёт skill в нативный каталог харнесса и обновляет связанные
    индексы только после плана, digest и подтверждения.

## Красные флаги

- `SKILL.md` вложен в `payload/` или другой каталог-обёртку.
- `name` во frontmatter не совпадает с именем каталога (`SK013`).
- Поле верхнего уровня, которое спецификация не определяет (`SK033`),
  вместо `metadata`.
- Скрипты, которые скачивают и pipe'ят в shell, или которые велят агенту
  игнорировать предыдущие инструкции.
- Живые токены, закрытые ключи или тела `.env` в пакете.
- Каталог под `skills/`, который на самом деле plugin (есть
  `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` /
  `.cursor-plugin/plugin.json` / `plugin.json`), помеченный как skill.
- Линия доверия `experimental` без `consent allow`.
- Харнесс не в списке совместимости компонента.
- «Latest» или имя ветки вместо точных `X.Y` и commit.
- Обращение с `ai-stp skill install` так, будто оно опубликовало этот
  компонент.
- Обращение с `author_verified` как с `component_verified`.

??? question "Можно ли skill использовать без публикации"
    Да. Собственный, импортированный или точно закреплённый skill можно
    использовать после локальных проверок. Он от этого не становится
    platform-verified и должен быть показан именно как локальный или
    закреплённый объект (`local_owner_or_pinned`).

## Чеклист автора

1. Сделайте scaffold с `--type skill --language none` и держите
   `SKILL.md` в корне пакета (в авторском дереве — под `native/`).
2. Заполните `name` и `description`. Ключи конкретного харнесса кладите
   в `metadata`.
3. Добавляйте `scripts/`, `references/` и `assets/` только когда workflow
   без них не работает. Что они делают, объявите в `SAFETY.md`.
4. Запустите `ai-stp component skill validate --path <package> --json` и
   исправьте каждый код `SKxxx`.
5. Закрепите точный публичный GitHub commit и подпуть. Секретов в дереве
   нет.
6. `component discover` → `component adopt` → `component passport validate`.
7. `component version release`, чтобы выпустить неизменяемый `X.Y`.
8. Публикуйте через [путь публикации](../publishing/index.md).
9. В сетапе закрепите этот `X.Y`. Позднее обновление — новая версия
   сетапа.

Связанное: [Авторство](../publishing/authoring.md),
[Компоненты](index.md), [CLI Agent Skill](../cli/skill.md).
