---
title: "Быстрый старт для ИИ-агента"
description: "Каждую сессию ai-stp начинать с task intents; запускать CLI самим; исполнять continuation argv только когда JSON-поле actor — cli; не собирать флаги из памяти."
---

# Быстрый старт для ИИ-агента

Эта страница — ритуал первого запуска и каждой сессии для coding agent,
который ведёт `ai-stp`. Человеку, который ставит бинарник, нужен
[Быстрый старт для человека](human.md).

Исполняемый файл — `ai-stp`. Дистрибутив на PyPI — `ai-stp-cli`. Команды
`ai-stp docs` нет. Документация называет команды, чтобы человек нашёл
страницу. **Вы** не должны собирать флаги, схемы и `next_actions` из
памяти, если установленный CLI уже отдаёт их сам.

## Каждая сессия начинается здесь

```bash
ai-stp task intents --json
```

Выберите один shipped intent. Запускайте `ai-stp task start` сами.
`envelope.continuations[0].actor` — JSON-поле, а не личность пользователя.
Когда поле `cli`, исполните `argv` своими tools. Когда `human`, это
`argv` не исполняйте: передайте `questions[0]` через
`ai-stp task answer` с уже связанными `task`, `revision` и `question-id`.
Когда `external`, покажите payload один раз и остановитесь. Этот `argv`
не исполняйте. `provider-too-old` — не login. Device-code можно позже
продолжить через `ai-stp task continue` после браузера; не опрашивайте
в цикле. Остановитесь, когда continuations нет. В отчёте —
проверка payload, а не только `ok` конверта.

Не запускайте `ai-stp doctor` и не дампьте `ai-stp help --agent` как
прелюдию к каждому запросу. Завершённого `inspect` достаточно, если
пользователь спросил, что не так. `ai-stp doctor --json` — только когда
спросили, что сломано.

`help --agent --json` остаётся полным реестром команд **этой** установки,
когда нужен дескриптор. Если эта страница и конверт расходятся, прав CLI.
Если команды нет в machine help, остановитесь. Не подменяйте похожей.

Каждую команду копируйте с `--json`, чтобы в stdout был ровно один конверт.
Предпочитайте уже выданный `argv`, а не набор expert leaves вручную.

## Как читать конверт

При `ok: true` результат в `data`. `warnings` всё равно могут быть важны.
При `ok: false` `error.code` — стабильный код из закрытого реестра;
`next_actions` — цитируемое отображение, не eval. Используйте
`continuations[].argv`.

Не угадывайте следующий шаг только по классу кода выхода. Повторяйте
только когда конверт говорит `retryable: true`. После неподтверждённого
таймаута сначала читайте status. Не повторяйте `install apply`.

## Mutability и confirmation

Эти два поля отвечают на разные вопросы. Подробности:
[CLI](../cli/index.md).

| `mutability` | Смысл |
| --- | --- |
| `read` | наблюдает; ничего не создаёт |
| `plan` | записывает проверяемый план или снимок; target не меняет |
| `apply` | меняет состояние |
| `destructive` | уничтожает идентичность или управляемые байты; всегда отдельное решение |

| `confirmation` | Смысл |
| --- | --- |
| `none` | лишнего токена нет; это не «можно запускать не спрашивая» |
| `explicit_flag` | передать флаг, который называет дескриптор, обычно `--confirm` |
| `plan_digest` | машинная привязка точных байт плана. Task intents привязывают её in-process. Expert leaves берут digest из plan-команды этого семейства, названной machine help. |

Intents `install`, `change` и `switch` сливают plan/approve/apply
in-process по полномочию задачи. Не набирайте `install plan`, чтобы
получить digest, и не хореографируйте эти leaves.

Команда чтения на свежей установке возвращает типизированную пустоту. Она
молча не запускает `device init`.

## Если inspect или doctor говорит, что нет идентичности

Попросите человека создать локальную идентичность или выполните те же
команды. Это не аккаунт. Подробности: [Устройство](../cli/device.md),
[Паспорта](../cli/passport.md).

```bash
ai-stp device init --json
ai-stp device show --json
ai-stp passport developer init --json
ai-stp passport device refresh --json
```

`device init` идемпотентен. `device reset` разрушителен, требует
`--confirm` и не является повтором `inspect`.

## Если нет Agent Skill

Это Agent Skill самого CLI: процедура, по которой вы ведёте `ai-stp`. Это
**не** компонент kind `skill`. Смешение двух смыслов — как перезаписывают
чужой workflow. Подробности: [Agent Skill CLI](../cli/skill.md).

```bash
ai-stp skill status --target <dir> --json
ai-stp skill install --target <dir> --json
```

`--target` обязателен. Это каталог, из которого harness читает native
skill. Не угадывайте этот каталог. Если не знаете его, спросите человека
или документацию harness.

Установка файла не заменяет чтение `task intents`. Когда файл на месте,
всё равно начинайте сессию оттуда.

## Чтения каталога — кандидаты

Анонимное чтение каталога не требует входа. `--kind` обязателен:
`component` или `setup`. Результат — не разрешение ставить.

Everyday-установка, когда кандидат уже есть:

```bash
ai-stp task start --intent install --idempotency-key install-session-01 --json
```

Expert-просмотр каталога:

```text
ai-stp registry search --kind component --json
ai-stp registry show --kind component --id <stable_id> --json
```

До установки проверьте harness, точный `X.Y`, линию доверия
и две независимые оси verification. Как читать карточку:
[Каталог](../catalog/index.md). `author_verified` не равен
`component_verified`, и ни то ни другое не гарантия безопасности:
[Доверие и безопасность](../trust-and-safety/index.md).

Если сети нет, чтение может ответить из кэша. Смотрите `checked_at`. Не
выдавайте попадание в кэш за живой каталог.

## Рабочий цикл

```text
task intents --json
→ task start (inspect | initialize | install | change | author | switch | account | publish)
→ execute continuation argv только когда JSON-поле actor — cli
→ task answer только для blocked human question
→ проверка payload
```

Пропускайте шаг только когда предыдущий конверт уже сделал его ненужным.
Не пропускайте механическую проверку. Не пишите нативные файлы harness;
это делает только public provider. Подробности: [Выбор](../cli/select.md),
[Установка](../cli/install.md), [Provider](../cli/provider.md).

Полный путь связным текстом для человека —
[Быстрый старт для человека](human.md). Группы команд — [CLI](../cli/index.md).
Одна строка на команду: [Карта команд](../cli/commands.md).

## Чего нельзя делать

- вызывать API модели или просить ключ модели;
- собирать флаги с этой страницы, когда доступны continuation `argv` или
  `help --agent`;
- хореографировать `install plan`, `install approve` или `install apply`;
- считать `author_verified` доказательством, что версия безопасна;
- ставить по заголовочному проценту каталога;
- пропускать `--json` на мутирующей команде;
- применять устаревший digest плана;
- выдумывать каталог skill harness, если нет `--target`.

## Типичные отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `ai-stp` не найден | инструмента нет или его нет в `PATH` | сказать человеку поставить `ai-stp-cli`; см. [Быстрый старт для человека](human.md) |
| doctor `device_identity` не `ready` | идентичность не создавали или хранилище её не читает | `ai-stp device init --json`, если её не создавали; иначе читать `detail` |
| команды нет в `help --agent` | этой установки её нет | остановиться; не подменять похожей командой |
| `AI_STP_VALIDATION_ERROR` нет `--target` | нужен каталог назначения | передать `--target <dir>`; не угадывать путь |
| stale plan | байты плана изменились | продолжить ту же задачу; движок перепланирует. Не набирайте `install plan` |
| `ok: false` при `retryable: false` | тот же argv не поможет | читать `error.code` и `continuations` |

## Связанные страницы

- [Быстрый старт](index.md) — выбрать путь человека или агента.
- [Быстрый старт для человека](human.md) — поставить бинарник и создать идентичность.
- [Наблюдение](../cli/observe.md) — `doctor`, `capabilities`, `help --agent`.
- [CLI](../cli/index.md) — конверты и группы команд.
- [Карта команд](../cli/commands.md) — одна строка на команду.
- [Agent Skill CLI](../cli/skill.md) — skill плоскости управления, не kind `skill`.
- [Диагностика](../troubleshooting/index.md) — после красной проверки.

!!! note "Команды здесь — карта, не парсер"
    Если `help --agent` расходится с флагом на этой странице, прав CLI.
    Опциональные флаги здесь не перечислены. Читайте их из descriptor.
