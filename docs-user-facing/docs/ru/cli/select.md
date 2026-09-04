---
title: "Выбор сетапа"
description: "Пригодность кандидатов, proposal, отчёты состава, граф, пакет и подтверждение выбора сетапа."
---

# Выбор сетапа

Выбор отвечает, из каких кандидатов можно собрать harness, записывает одно
proposal и замораживает его как частную версию сетапа. Target он не создаёт.
Provider пишет нативное состояние позже, через [Установку](install.md).

Агент может помочь выбрать членов. Он не обходит механические ограничения
eligibility, доступа и безопасности. Пустой допустимый список с причинами
рядом — честный ответ, не авария.

## Таблица команд

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp select eligibility` | `read` | `none` | каких кандидатов может использовать один harness, и почему каждый отказ |
| `ai-stp select eligibility-matrix` | `read` | `none` | куда можно собрать один объект, для каждого поддерживаемого harness |
| `ai-stp select impact` | `read` | `none` | сравнить контекст, стоимость токенов и capabilities точных локальных версий |
| `ai-stp select blast-radius` | `read` | `none` | локальные ссылки сетапа, проекта, устройства и target на компонент |
| `ai-stp select propose` | `plan` | `none` | записать одно composition proposal; без версии, без target |
| `ai-stp select confirm` | `apply` | `none` | заморозить одно proposal как частную версию сетапа, trace и pin |
| `ai-stp select cancel` | `apply` | `none` | закрыть одно proposal, не создавая версию |
| `ai-stp select graph` | `read` | `none` | разрешить точное замыкание зависимостей или назвать каждую причину отказа |
| `ai-stp select reports` | `read` | `none` | что выбрано, что конфликтует, что теряется |
| `ai-stp select bundle` | `read` | `none` | скомпилировать детерминированный пакет; в target не писать |
| `ai-stp select session` | `read` | `none` | открытые proposal для проекта и harness и выбранная версия |

`--json` глобальный. Всегда передавайте его. У `select confirm`
`confirmation: none`: назвать `--proposal` **и есть** решение. `--confirm`
нет.

## Eligibility

```bash
ai-stp select eligibility --harness codex --json
ai-stp select eligibility --harness codex --project . --json
ai-stp select eligibility --harness codex --include-unverified --json
ai-stp select eligibility --harness codex --for-redistribution --json
```

`--harness` обязателен. `--project` называет корень проекта, из фактов
которого строится target. `--include-unverified` соглашается рассматривать
непроверенные кандидаты **только для этого вызова**. Он никогда не
сохраняется и никогда не достаточен, чтобы выбрать автоматически.
`--for-redistribution` применяет права на распространение, потому что состав
предназначен к redistributе.

Поля успеха: `harness_id`, `harness_version`, `os`, `arch`,
`admissible_count`, `auto_selectable_count`, `candidates`, `capabilities`,
`capability_vocabulary_version`. `admissible_count: 0` с перечисленными
отказами — успех.

## Eligibility matrix

```bash
ai-stp select eligibility-matrix --json
ai-stp select eligibility-matrix --harness codex --harness claude-code --json
```

`--harness` повторяемый. Опустите, чтобы покрыть каждый поддерживаемый
harness. Остальные флаги совпадают с `eligibility`.

## Impact и blast-radius

Impact сравнивает точные локальные версии сетапа. Blast-radius перечисляет
локальные ссылки на одну версию компонента.

```bash
ai-stp select impact \
  --setup-id <setup_id> \
  --setup-version 1.0 \
  --json

ai-stp select impact \
  --setup-id <setup_id> \
  --setup-version 1.1 \
  --against-setup-id <setup_id> \
  --against-setup-version 1.0 \
  --tokenizer-profile ai-stp:utf8-bytes/1 \
  --json

ai-stp select blast-radius \
  --component-id <component_id> \
  --component-version 1.0 \
  --scenario update \
  --json
```

`--tokenizer-profile` — `ai-stp:utf8-bytes/1` или
`ai-stp:unicode-chars-div4/1`. `--price-profile` — явный локальный JSON
файл цен токенов. `--project-id` берёт установленный или выбранный сетап
этого проекта как baseline, когда `--against-setup-id` нет. `--scenario` —
одно из `update`, `deprecation`, `blocked`, `expired_evidence`, `advisory`.

## Propose, session, confirm, cancel

Proposal — короткоживущий точный объект сессии. Он истекает. Confirm
замораживает частную версию сетапа. Cancel ничего не создаёт.

`--member` повторяемый, каждое значение `<stable_id>@<X.Y>`. `--empty`
собирает сетап, который не проецирует файлы. `--empty` и `--member` вместе
отклоняются.

```bash
ai-stp select session --harness codex --project . --json

ai-stp select propose \
  --harness codex \
  --project . \
  --member component_...@1.0 \
  --member component_...@2.1 \
  --json

ai-stp select confirm --proposal <proposal_id> --json
ai-stp select cancel --proposal <proposal_id> --json
```

Propose возвращает сессию с `proposal_id`, `state` (`open`, `confirmed`,
`cancelled`, `expired`), `members`, `harness_id`, `project_id`,
`created_at`, `expires_at`, `snapshot`. Confirm возвращает `created`,
`stable_id`, `version`, `revision_id`, `state` (`pending_install` или
`installed`), `trace`. Повторный confirm того же proposal — успех: по
`created` отличите «этот вызов создал» от «уже было создано».

## Graph, reports, bundle

```bash
ai-stp select graph --proposal <proposal_id> --json
ai-stp select graph --member component_...@1.0 --json

ai-stp select reports --harness codex --proposal <proposal_id> --json

ai-stp select bundle --harness codex --proposal <proposal_id> --json
ai-stp select bundle \
  --harness codex \
  --proposal <proposal_id> \
  --target <absolute-dir> \
  --scope project \
  --json
```

`graph` берёт либо `--proposal`, либо повторяемый `--member`, не смесь,
которую вы придумали. У каждого узла есть `stable_id`, `version`,
`passport_digest`, `revision_id`, `depth`, `requires`.

`reports` нужны `--harness` и `--proposal`. `--project` — корень проекта,
из фактов которого строится target.

`bundle` компилирует байты и манифест. Это `read`: `ADR-0012` отдаёт запись
provider. `--scope` — `global` (по умолчанию), `project` или `user_root`.
`--target` нужен, когда член добавляет ключ в файл, которым provider уже
владеет: текущие байты существуют только на target. Если `compiled` равен
false, `digest` и `files` пусты, а `refusals` называет каждую причину.

## Happy path

```text
select eligibility --harness <id> --project .
→ select propose --harness <id> --member <id>@<X.Y>
→ select reports --harness <id> --proposal <proposal>
→ select graph --proposal <proposal>
→ select confirm --proposal <proposal>
→ install plan --proposal <proposal> --provider <exe> …
```

Читайте `select session`, когда нужны открытое proposal и выбранная версия
этой пары.

## Именованные поля успеха

| Команда | Какие поля читать |
| --- | --- |
| `eligibility` | `admissible_count`, `auto_selectable_count`, `candidates` |
| `propose` / `session` / `cancel` | `proposal_id`, `state`, `members`, `expires_at` |
| `confirm` | `created`, `stable_id`, `version`, `revision_id`, `state` |
| `graph` | узлы с `stable_id`, `version`, `passport_digest` |
| `bundle` | `compiled`, `digest` / `artifact_digest`, `refusals` |
| `impact` | сравниваемые версии и поля стоимости |
| `blast-radius` | ссылающиеся сетапы, проекты, устройства, target |

## Отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | нет `--harness`, или `--member` вместе с `--empty` | исправить запрос |
| `AI_STP_NOT_FOUND` | proposal, сетап или компонент неизвестны | `select session` или `component find` |
| `AI_STP_USER_DECISION_REQUIRED` | непроверенным кандидатам нужно явное согласие | `--include-unverified` на eligibility, затем выбор человека |
| `AI_STP_PRECONDITION_FAILED` | proposal истекло или не `open` | снова `propose`; не confirm истекший id |
| `AI_STP_CONFLICT` | сессия уже сдвинулась | `select session`, затем действовать по текущему proposal |
| `admissible_count: 0` | для этого harness собирать нечего | прочитать отказ каждого кандидата; не выдумывать member |
| `compiled: false` | bundle собрать не удалось | прочитать `refusals`; не устанавливать половину пакета |
| выдумывать `--confirm` у confirm | этого флага нет | `--proposal` и есть подтверждение |

`--include-unverified` никогда не становится сохранённым согласием.
Сохранённое согласие — [Согласие](consent.md). Experimental-объектам оно
всё равно нужно до установки.

## Связанные страницы

- [Установка](install.md)
- [Команды сетапа](setup.md)
- [Команды компонента](component.md)
- [Реестр](registry.md)
- [Согласие](consent.md)
- [Сетапы](../setups/index.md)
- [Доверие и безопасность](../trust-and-safety/index.md)
- [Карта команд](commands.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды выбора, чтобы человек их нашёл.
Установленный CLI — источник флагов, схем и `next_actions`. Если страница
и CLI расходятся, следуйте CLI.
