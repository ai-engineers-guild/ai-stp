---
title: "Паспорт компонента"
description: "Показать, предложить, обновить, провалидировать и проверить качество локального паспорта компонента."
---

# Паспорт компонента

Паспорт компонента — локальное версионированное описание одного adopted
объекта. Эти команды показывают текущий черновик, предлагают факты для
подтверждения, пишут новую ревизию и сообщают, структурно ли head готов к
публикации.

Они не публикуют. Они не меняют `author_verified` и `component_verified`.
Подсказки quality необязательны и механические. Паспорта разработчика и
устройства — другая группа: [Паспорта](passport.md).

## Таблица команд

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp component passport show` | `read` | `none` | показать текущий локальный черновик паспорта |
| `ai-stp component passport suggest` | `read` | `none` | предложить точные факты манифеста, не меняя черновик |
| `ai-stp component passport update` | `apply` | `plan_digest` | добавить подтверждённые факты как новую content-addressed ревизию |
| `ai-stp component passport validate` | `read` | `none` | сообщить каждый структурный блокер публикации этой ревизии |
| `ai-stp component passport quality` | `read` | `none` | необязательные подсказки автору; trust и готовность не меняет |

`--json` глобальный. Всегда передавайте его.

## Show

```bash
ai-stp component passport show --id <stable_id> --json
```

`--id` — стабильный идентификатор adopted-компонента.

Ответ — вид паспорта: `stable_id`, `kind`, `revision_id`,
`parent_revision_ids`, `owner_id`, `created_at`, `facts`, `schema_version`.
`kind` равен `component`. `revision_id` — head, который нужно назвать, если
пишете patch.

## Suggest

Suggest читает adopted-байты и предлагает факты закрытой схемы. Ничего не
пишет. Неразрешённые поля остаются неразрешёнными, пока вы не подтвердите
их через `update`.

```bash
ai-stp component passport suggest --id <stable_id> --json
```

Поля успеха: `stable_id`, `revision_id`, `suggestions`,
`unresolved_fields`, `schema_version`. У каждого предложения есть `field`,
`value` и `source_refs`. В файл patch копируйте только просмотренные факты.

## Update

Update применяет ограниченный JSON-patch закрытой схемы как потомка
текущего head. Токен подтверждения — `--expected-revision`, точный
`revision_id`, который вернул `show`. Нет `--confirm` и нет
`--expected-plan-digest`.

```bash
ai-stp component passport update \
  --id <stable_id> \
  --expected-revision <revision_id> \
  --from ./passport-patch.json \
  --json
```

`--from` — путь к patch. Секреты, тела `.env`, токены и абсолютные личные
пути в этот файл не входят.

Если patch содержит `tags`, передавайте от 1 до 10 уникальных тегов. Каждый
тег — от 2 до 32 символов: только строчные английские буквы, цифры и дефис.
Пробел заменяйте дефисом; типографская пунктуация и неанглийские буквы
отклоняются.

Ответ — новый вид паспорта. `revision_id` изменился. Предыдущий head — в
`parent_revision_ids`. Второй вызов со старым `--expected-revision`
отклоняется: head сдвинулся.

## Validate

Validate сообщает каждый структурный блокер публикации текущей ревизии.
Это локальный вердикт, не разрешение писать в облако. Публикации всё равно
нужен свой аутентифицированный план.

```bash
ai-stp component passport validate --id <stable_id> --json
ai-stp component passport validate --id <stable_id> --for-publication --json
```

`--for-publication` выбирает профиль готовности к публичной публикации.
Этот профиль команда и так применяет. Флаг принят, чтобы старое написание
вызывающего всё ещё разбиралось.

Поля успеха: `stable_id`, `revision_id`, `ready`, `missing_fields`,
`invalid_fields`, `for_publication`, `schema_version`. `ready: false` —
успешный отчёт о блокерах, а не упавшая команда. Исправьте черновик через
`update`, затем validate снова.

## Quality

Quality показывает необязательные механические подсказки автору. Черновик,
trust и готовность к публикации не меняет. `affects_component_verified`
равен `false`.

```bash
ai-stp component passport quality --id <stable_id> --json
```

Измерения — подсказки. Не пропускайте `validate`, потому что quality
выглядел зелёным. Не считайте quality платформенным сканом безопасности;
он бывает при публикации.

## Happy path

```text
component adopt --path <exact>
→ component passport show --id <stable_id>
→ component passport suggest --id <stable_id>
→ просмотреть suggestions; написать patch
→ component passport update --id <stable_id> --expected-revision <rev> --from <patch>
→ component passport validate --id <stable_id>
→ component version release --id <stable_id>
```

После каждой записи показывайте конверт. Следующий `update` должен назвать
новый `revision_id`.

## Именованные поля успеха

| Команда | Какие поля читать |
| --- | --- |
| `show` / `update` | `stable_id`, `revision_id`, `kind`, `facts`, `parent_revision_ids` |
| `suggest` | `revision_id`, `suggestions`, `unresolved_fields` |
| `validate` | `ready`, `missing_fields`, `invalid_fields`, `revision_id` |
| `quality` | статусы измерений и checks; `affects_component_verified` |

## Отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | нет `--id`, `--expected-revision` или `--from`, или patch не закрытой схемы | исправить запрос; не слать свободный JSON-объект |
| `AI_STP_NOT_FOUND` | этот id — не adopted-компонент | `component find` или `component discover` |
| `AI_STP_CONFLICT` / `AI_STP_PRECONDITION_FAILED` | `--expected-revision` больше не head | `passport show`, собрать patch заново, update снова |
| `AI_STP_PLAN_STALE` | patch готовили против байтов, которые сдвинулись | как при conflict: show, затем новый patch |
| `ready: false` | структурные блокеры остались | прочитать `missing_fields` и `invalid_fields`; `update`; validate снова |
| секреты в patch | паспорт не держит учётные данные | убрать их; хранить секреты вне паспорта |
| `--confirm` отвергнут | этого флага нет в декларации | подтверждать update только `--expected-revision` |

`validate` с `ready: false` — не `ok: false`. Конверт всё равно успех.
Блокеры — данные.

## Связанные страницы

- [Команды компонента](component.md)
- [Обнаружение и adopt](component-discover.md)
- [Источник компонента](component-source.md)
- [Публикация компонента](component-publish.md)
- [Паспорта](passport.md)
- [Публикация](../publishing/index.md)
- [Доверие и безопасность](../trust-and-safety/index.md)
- [Проверки безопасности](../security-checks.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды паспорта, чтобы человек их нашёл.
Установленный CLI — источник флагов, схем и `next_actions`. Если страница
и CLI расходятся, следуйте CLI.
