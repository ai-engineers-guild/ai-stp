---
title: "Обнаружение и adopt"
description: "Найти нативные компоненты, сделать scaffold и зарегистрировать обнаруженное."
---

# Обнаружение и adopt

Эти команды смотрят на файлы, которые уже есть на этой машине, или создают
новый каталог авторства. Они не публикуют, не устанавливают и не пишут
состояние harness.

Discovery сообщает пути, не открывая файлы с секретными именами, чтобы
узнать содержимое. Adopt пути — явное действие: он регистрирует один
найденный компонент в локальном реестре. Forget помечает запись удалённой
и сохраняет историю.

## Таблица команд

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component discover` | `read` | `none` | перечислить нативные компоненты в корнях harness и одном проекте |
| `ai-stp component find` | `read` | `none` | искать в локальном реестре по prefix, phrase, tag или field |
| `ai-stp component scaffold plan` | `plan` | `none` | показать точные файлы и digest одного версионированного scaffold |
| `ai-stp component scaffold apply` | `apply` | `plan_digest` | создать ровно подтверждённый scaffold; путь не перезаписывать |
| `ai-stp component template render` | `read` | `none` | отрендерить и проверить portable-шаблон для одного harness |
| `ai-stp component adopt` | `apply` | `none` | зарегистрировать один найденный компонент в локальном реестре |
| `ai-stp component forget` | `apply` | `none` | пометить зарегистрированный компонент удалённым, историю сохранить |

`--json` глобальный. Всегда передавайте его.

## Discover

`discover` сканирует корни harness и, если назван `--root`, один проект.
Ничего не меняет. Путь, похожий на секрет, помечается по **имени**, а не
потому что файл открыли.

```bash
ai-stp component discover --json
ai-stp component discover --root . --json
```

Поля успеха: `components`, `diagnostics`, `project`, `schema_version`. У
каждого компонента есть `candidate_id`, `component_type`, `layout_source`,
`native_role`, `path`, `harness_id`, `holds_secret`, `byte_length`,
`entry_points` и `evidence_refs`.

Пустой список `components` — типизированная пустота, не отказ. Он не
запускает молча `device init` и ничего не adopt.

## Find

`find` ищет объекты, уже лежащие в локальном реестре. Без модели и без
сети. Непроверенные попадания скрыты, пока не передадите
`--include-unverified` только для этого вызова. Флаг никогда не сохраняется.

```bash
ai-stp component find --prefix demo --json
ai-stp component find --phrase "playwright" --tag mcp --json
ai-stp component find --field kind --value skill --include-unverified --json
```

`--tag` повторяемый: каждый названный tag должен совпасть. `--field` и
`--value` вместе точно совпадают с одним объявленным полем.

Поля успеха: `hits` (у каждого `stable_id`, `lane` и `fields`) и
`schema_version`.

## Scaffold plan, затем apply

Scaffold — новый каталог авторства. Сначала plan. Apply создаёт ровно те
файлы, которые назвал план, и отказывается перезаписать путь, который уже
существует.

`--type` — одно из `instruction`, `skill`, `mcp`, `hook`, `command`,
`agent`, `plugin`, `setting`. `--language` — `none` для декларативных
типов или одно из `python`, `typescript`, `javascript`, `rust`, `go`,
`dart-flutter`. `--harness` — `portable` или конкретный harness:
`claude-code`, `codex`, `pi`, `opencode`, `grok-build`, `cursor`,
`antigravity`. `--name` — slug в нижнем регистре. `--output` — новый
каталог.

```bash
ai-stp component scaffold plan \
  --type skill \
  --language python \
  --harness portable \
  --name demo-skill \
  --output ./components/demo-skill \
  --json
```

Ответ плана несёт `plan_id`, `plan_digest`, `output`, `component_name`,
`descriptor` и `files`. У каждого файла есть `path`, `digest` и
`byte_length`. `publication_ready` равен `false`. Перед публикацией
scaffold всё равно нужен точный источник.

Apply повторяет те же опции и добавляет `--expected-plan-digest`
неизменённого плана. `--confirm` нет. Digest говорит, **какой** scaffold.

```bash
ai-stp component scaffold apply \
  --type skill \
  --language python \
  --harness portable \
  --name demo-skill \
  --output ./components/demo-skill \
  --expected-plan-digest sha256:... \
  --json
```

Ответ apply несёт `plan_id`, `plan_digest`, `output` и `created`. Если
каталог уже есть, команда отказывается. Если digest больше не совпадает с
пересчитанным планом, команда отказывается как stale.

## Template render

Рендер portable UTF-8 шаблона для одного конкретного harness. Это read:
он проверяет рендер. Нативные файлы он не пишет.

```bash
ai-stp component template render \
  --template ./templates/skill.md \
  --harness codex \
  --name demo-skill \
  --component-root components/demo-skill \
  --json
```

`--harness` здесь — harness из закрытого реестра, не `portable`.
`--component-root` — ограниченный относительный POSIX-путь.

## Adopt

Adopt пишет паспорт и сохраняет байты. Назвать `--path` точным путём из
discovery **и есть** решение. `--confirm` нет.

```bash
ai-stp component adopt --path <exact-path> --json
ai-stp component adopt --path <exact-path> --root . --json
```

Если один путь отвечает более чем одному harness, назовите `--harness`.
Для общей кросс-продуктовой претензии используйте `portable`. Если путь
отвечает более чем одному kind, назовите `--kind`.

Ответ — вид паспорта: `stable_id`, `kind`, `revision_id`,
`parent_revision_ids`, `owner_id`, `created_at`, `facts`, `schema_version`.

## Forget

Forget помечает компонент удалённым в локальном реестре и сохраняет
историю. Управляемые байты на target harness он не удаляет.

```bash
ai-stp component forget --id <stable_id> --reason "replaced by catalog pin" --json
```

`--reason` необязателен. Ответ той же формы, что у adopt.

## Happy path

```text
component discover --root .
→ component adopt --path <exact>
→ component passport show --id <stable_id>
```

Или для нового компонента:

```text
component scaffold plan → scaffold apply --expected-plan-digest
→ component adopt --path <output>
→ component passport validate --id <stable_id>
```

## Именованные поля успеха

| Команда | Какие поля читать |
| --- | --- |
| `discover` | `components`, `diagnostics`, `project` |
| `find` | `hits`, у каждого `stable_id` и `lane` |
| `scaffold plan` | `plan_id`, `plan_digest`, `files` |
| `scaffold apply` | `plan_digest`, `output`, `created` |
| `template render` | payload отрендеренного шаблона |
| `adopt` / `forget` | `stable_id`, `revision_id`, `kind`, `facts` |

## Отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | обязательная опция отсутствует или не из закрытого словаря | прочитать дескриптор; не выдумывать type или harness |
| `AI_STP_NOT_FOUND` | discovery этот путь не сообщал, или id неизвестен | снова `discover` или `find` |
| `AI_STP_USER_DECISION_REQUIRED` | путь заявлен более чем одним harness или kind | передать `--harness` и/или `--kind` |
| `AI_STP_PLAN_STALE` | байты scaffold больше не совпадают с `--expected-plan-digest` | снова plan, показать файлы, apply с новым digest |
| `AI_STP_CONFLICT` | apply перезаписал бы существующий путь | выбрать новый `--output` |
| пустой `components` | нативного ничего не найдено | это успех; не adopt угаданный путь |
| забыли `--include-unverified` | непроверенные локальные объекты скрыты | передать флаг только для этого вызова или оставить скрытыми |

Не передавайте `--confirm` в adopt, forget или scaffold apply. Этих флагов
нет в декларации. Scaffold apply подтверждается `--expected-plan-digest`.

## Связанные страницы

- [Команды компонента](component.md)
- [Паспорт компонента](component-passport.md)
- [Источник компонента](component-source.md)
- [Публикация компонента](component-publish.md)
- [Компоненты](../components/index.md)
- [Проект](project.md)
- [Реестр](registry.md)
- [Согласие](consent.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды обнаружения, чтобы человек их нашёл.
Установленный CLI — источник флагов, схем и `next_actions`. Если страница
и CLI расходятся, следуйте CLI.
