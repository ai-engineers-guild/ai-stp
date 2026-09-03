---
title: "Объекты владельца"
description: "Перечислить и показать серверные объекты, которыми владеет аутентифицированный аккаунт."
---

# Объекты владельца

Команды владельца читают серверные объекты, принадлежащие этой учётной записи, а также точные версии одного объекта. Это операции чтения. Они не публикуют, не предоставляют доступ и не меняют видимость.

Публичный каталог показывает то, что уже открыто. Эта группа показывает то, чем владеете **вы**, включая приватные версии, данные жизненного цикла и возможность начать публикацию версии.

Локальный черновик от `component adopt` не является объектом владельца. Он становится таковым, когда публикация сохранит его на сервере. Гранты, которые вы получили, отображаются в [Грантах доступа](grant.md), а не здесь.

## Таблица команд

| Команда | Изменяемость | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp owner objects` | `read` | `none` | список объектов, принадлежащих аутентифицированной учётной записи |
| `ai-stp owner object show` | `read` | `none` | чтение одного серверного авторизованного объекта владельца и его точных версий |
| `ai-stp owner version show` | `read` | `none` | чтение одной точной версии владельца и её серверных данных жизненного цикла |

`--json` — глобальный флаг. Передавайте его всегда. Ни одна из этих команд не принимает `--confirm`.

## Список

```bash
ai-stp owner objects --json
ai-stp owner objects --kind component --json
ai-stp owner objects --kind setup --page-size 20 --json
ai-stp owner objects --cursor <cursor> --json
```

`--kind` необязателен: `component` или `setup`. `--cursor` — непрозрачный курсор, возвращённый предыдущей страницей. `--page-size` по умолчанию равен 20.

Поля успеха: `items`, `page`. Каждый элемент — это сводка объекта владельца: стабильный id, вид и имя. `page` содержит следующий курсор, если остались ещё данные. `--page-size` ограничен; не придумывайте размер страницы вне контракта. Проходите страницы, пока курсор не станет пустым. Первая страница без элементов — это типизированная пустота, а не ошибка.

## Показ объекта

```bash
ai-stp owner object show --kind component --id <stable_id> --json
ai-stp owner object show --kind setup --id <stable_id> --json
```

`--kind` и `--id` обязательны.

Поля успеха: `stable_id`, `object_kind`, `name`, `versions`. Каждая сводка версии включает `version`, `visibility` (`public` или `private`), `trust_lane` (`authoritative` или `experimental`), `author_verified`, `component_verified`, `content_digest`, `lifecycle_state`, `install_eligible`, `can_start_publication`, `published_at`.

`author_verified` и `component_verified` независимы. Подтверждённый автор может владеть неподтверждённой версией. `can_start_publication` — это разрешение начать план, а не завершённая публикация.

`visibility` — это `public` или `private` для данной версии. Изменение видимости — не эта команда. `trust_lane` в представлении владельца — это `authoritative` или `experimental`. `install_eligible` — серверный бит для данной версии; локальная пригодность по-прежнему определяется через `select eligibility`. `lifecycle_state` — это серверный жизненный цикл, а не локальный журнал установки.

## Показ версии

```bash
ai-stp owner version show \
  --kind component \
  --id <stable_id> \
  --version 1.0 \
  --json
```

`--kind`, `--id` и `--version` обязательны. `--version` — точный `X.Y`.

Ответ — полная версия владельца плюс серверные данные жизненного цикла: те же координаты, что и в сводке, с данными, которые сервер сохранил для этой точной версии. Используйте перед `publication plan`. Сравните `content_digest` с локальным паспортом перед планированием. Расхождение означает, что локальный head сдвинулся; выпустите новый `X.Y` вместо пере-публикации старого номера.

Не ожидайте, что эта команда вернёт байты артефакта. Получайте опубликованные байты через [Реестр](registry.md) `registry fetch`. Не ожидайте, что она вернёт получателей грантов; это `grant list`.

## Счастливый путь

```text
auth status
→ owner objects --kind component
→ owner object show --kind component --id <id>
→ owner version show --kind component --id <id> --version 1.0
→ publication plan --id <id> --version 1.0
```

Для графа сетапа — тот же цикл с `--kind setup`, затем `setup publish plan`.

После публикации:

```text
owner version show --kind component --id <id> --version <X.Y>
→ visibility public, can_start_publication больше не является следующим шагом
→ registry version --kind component --id <id> --version <X.Y>
```

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `objects` | `items`, `page` |
| `object show` | `stable_id`, `object_kind`, `name`, `versions` |
| `version show` | `version`, `content_digest`, `lifecycle_state`, `can_start_publication`, `author_verified`, `component_verified` |

Для каждой версии также читайте `visibility`, `trust_lane` и `install_eligible`.

## Отказы

| Что вы видите | Что это означает | Что делать |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | нет выполненного входа | `auth login` |
| `AI_STP_PERMISSION_DENIED` | эта учётная запись не владеет данным объектом | вы получатель гранта или читатель каталога; используйте `registry show` |
| `AI_STP_NOT_FOUND` | id или версия отсутствуют на сервере | `owner objects`; локальный черновик здесь не отображается |
| `AI_STP_VALIDATION_ERROR` | отсутствует `--kind` на show или `--version` | `--kind` обязателен для object и version show |
| `AI_STP_DEVICE_REVOKED` | ключ устройства отозван для облачного чтения | новое устройство + вход |
| интерпретация `can_start_publication` как опубликованного | это бит разрешения | всё ещё нужно выполнить `publication plan`, затем `confirm` |
| ожидание, что `experimental` будет скрыт | представление владельца включает то, чем вы владеете | дорожки публичного каталога — это другая поверхность |

Локальные черновики от `component adopt` не являются объектами владельца, пока они не будут опубликованы или иным образом сохранены на сервере. `owner objects` на новой учётной записи — это типизированная пустота.

## Связанные ссылки

- [Публикация](publication.md)
- [Гранты доступа](grant.md)
- [Реестр](registry.md)
- [Вход](auth.md)
- [Веб-объекты](../web/objects.md)
- [Публикация](../publishing/index.md)
- [Карта команд](commands.md)

## Справка для машины — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды владельца для удобства поиска. Установленный CLI является источником флагов, схем и `next_actions`. Если эта страница и CLI расходятся, следуйте CLI.
