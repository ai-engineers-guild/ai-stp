---
title: "Синхронизация"
description: "Предпросмотр, push, merge и pull приватного потока аккаунта."
---

# Синхронизация

Sync перемещает локальные ревизии паспортов в и из приватного потока учётной записи.
Это не публичный каталог, не Git и не установка. Предпросмотр никогда
не изменяет head. Push, merge и pull — явные, безопасные для повторного воспроизведения записи.

Локальная работа не нуждается в sync. Вход в учётную запись обязателен для этих команд,
потому что они обращаются к потоку учётной записи. Поток несёт ревизии паспортов,
а не файлы таргета харнеса и не бэкапы провайдера.

## Таблица команд

| Команда | Мутабельность | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp sync preview` | `read` | `none` | предпросмотр локального fast-forward, merge или конфликта без изменения head |
| `ai-stp sync push` | `apply` | `explicit_flag` | запушить один точный локальный head с устойчивым безопасным для воспроизведения событием |
| `ai-stp sync merge` | `apply` | `explicit_flag` | зафиксировать механически чистый мёрж двух head разработческих паспортов |
| `ai-stp sync pull` | `apply` | `explicit_flag` | получить и атомарно применить одну ограниченную страницу из потока учётной записи |

`--json` — глобальный флаг. Всегда передавайте его. Push, merge и pull требуют
`--confirm`.

## Preview

```bash
ai-stp sync preview --id <stable_id> --json
```

`--id` — стабильный идентификатор, чьи локальные head сравниваются.

Поля успеха: `stable_id`, `state`, `head_revision_ids`,
`common_ancestor_revision_id`, `candidate_revision_id`,
`server_head_revision_id`, `affected_fields`.

`state` — это следующий механический ход:

| `state` | Значение |
| --- | --- |
| `up_to_date` | один локальный head, нечего мёржить или пушить |
| `fast_forward` | чистый потомок существует; push или pull могут переместить head |
| `merge` | два head имеют чистый механический кандидат на мёрж |
| `conflict` | сервер указывает head, которого нет на этом устройстве, или поля расходятся |
| `manual_resolution` | более двух локальных head, или нет общего предка |

Preview не пушит. Конфликт — это честный отчёт, а не сбой. Один
локальный head плюс отклонённый push, который указывает head сервера, которого нет на этом
устройстве, — это тоже `conflict`, а не `up_to_date`.

## Push

```bash
ai-stp sync push --id <stable_id> --confirm --json
```

`--id` и `--confirm` обязательны. Событие устойчиво и безопасно для воспроизведения:
второй push того же head не создаёт второй эффект.

Поля успеха: `stable_id`, `state`, `processed_events`, `event_id`,
`local_revision_id`, `remote_revision_id`, `server_head_revision_id`,
`conflicting_entity_id`, `conflict_fields`.

Если `state` сообщает конфликт, остановитесь и выполните `preview` снова. Не пушьте в
цикле.

## Merge

```bash
ai-stp sync merge --id <stable_id> --confirm --json
```

`--id` и `--confirm` обязательны. Merge фиксирует механически чистый
мёрж **двух** head разработческих паспортов. Он не изобретает значения полей.
Если preview был `conflict` или `manual_resolution`, merge отклоняется.

Ответ — это предпросмотр результирующих head: та же схема, что и у
`sync preview`. Запушьте после, если новый head должен покинуть это устройство.

## Pull

```bash
ai-stp sync pull --confirm --json
ai-stp sync pull --page-size 20 --confirm --json
ai-stp sync pull --skip-event <event_id> --confirm --json
```

`--confirm` обязателен. `--page-size` — максимальное количество событий на этой странице.
`--skip-event` повторяем: каждое значение — это точный id отклонённого события,
через которое нужно пройти, отбрасывая его ревизию. Пропуск запоминается этим
устройством, поэтому последующий pull проходит мимо него без запроса.

Поля успеха: `received`, `applied`, `replayed`, `next_cursor`,
`skipped`. Выполняйте pull, пока `next_cursor` не станет пустым, если намерены опустошить
поток. Каждая страница атомарна.

## Счастливый путь

```text
auth status
→ sync preview --id <stable_id>
→ sync pull --confirm          # если поток впереди
→ sync merge --confirm         # только когда preview говорит merge
→ sync push --id <stable_id> --confirm
→ sync preview --id <stable_id>
```

Читайте `preview` после каждой записи. Не пушьте и не pull'ите в одном действии,
не прочитав `state`.

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `preview` / `merge` | `state`, `head_revision_ids`, `candidate_revision_id`, `affected_fields` |
| `push` | `event_id`, `local_revision_id`, `remote_revision_id`, `state` |
| `pull` | `received`, `applied`, `replayed`, `next_cursor`, `skipped` |

## Отказы

| Что вы видите | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | нет выполненного входа | `auth login` |
| `AI_STP_DEVICE_REVOKED` | ключ этого устройства отозван для облачных операций | `device` + новый вход; не переиспользуйте отозванный ключ |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` был пропущен | передайте `--confirm` после чтения preview |
| `AI_STP_NOT_FOUND` | у этого id нет локальных head ревизий | `passport developer show` / создайте объект локально сначала |
| `AI_STP_CONFLICT` | head сервера расходится с этим устройством | `preview`; merge только если state — `merge` |
| `AI_STP_PRECONDITION_FAILED` | merge, когда head не являются чистой парой | разрешите вручную; не пропускайте события, чтобы скрыть это |
| `AI_STP_RATE_LIMITED` | сервер попросил замедлиться | повторяйте только если `retryable: true` |
| пропуск события | его ревизия отброшена на этом устройстве | передавайте `--skip-event` только после человеческого отказа |

Не помещайте токены потока в командную строку. Не принимайте sync за бэкап
таргета харнеса. Копии таргета живут у провайдера; см.
[Target](target.md).

## Связанные ссылки

- [Вход](auth.md)
- [Паспорта](passport.md)
- [Устройство](device.md)
- [Объекты владельца](owner.md)
- [Карта команд](commands.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды синхронизации, чтобы человек мог их найти. Установленный
CLI — источник флагов, схем и `next_actions`. Если эта страница и
CLI расходятся, следуйте CLI.
