---
title: "Toolchain"
description: "Установить и удалить управляемые инструменты, прочитать закреплённый профиль и обзор harness с нативными возможностями."
---

# Toolchain

Управляемый toolchain — закреплённый профиль, а не случайный
`pip install`. `toolchain install` пишет в управляемый каталог и
ничего не запускает из только что положенного инструмента.
`toolchain harnesses` сообщает, есть ли поддерживаемый harness на
этой машине. `toolchain harness-capabilities` говорит, что продукт
умеет читать нативно и что этот билд умеет проецировать. Это не
утверждение, что компонент активен.

Это не [Программа harness](harness.md). Установка бинарника harness —
`harness install`. Это не [Provider](provider.md). Provider — бинарник,
который потом пишет нативное состояние.

## Команды

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp toolchain install` | `apply` | `none` | установить один закреплённый инструмент в управляемый каталог; из него ничего не запускает |
| `ai-stp toolchain remove` | `destructive` | `explicit_flag` | удалить один управляемый инструмент, трогая только пути, которые создал этот CLI |
| `ai-stp toolchain profile` | `read` | `none` | показать управляемый профиль toolchain, как он разрешается на этой машине |
| `ai-stp toolchain harnesses` | `read` | `none` | сообщить о каждом поддерживаемом harness и есть ли он на этой машине |
| `ai-stp toolchain harness-capabilities` | `read` | `none` | по harness и kind: что продукт читает нативно, что этот билд умеет проецировать, и почему любой gap — gap. Не утверждение, что компонент активен — это спрашивают у провайдера |

`--tool` обязателен на `install` и `remove`. `remove` также требует
`--confirm`. Точные идентификаторы инструментов — из
`toolchain profile`, а не из памяти.

## Типичный путь

Прочитать профиль, затем поставить один закреплённый инструмент, затем
посмотреть harness:

```bash
ai-stp toolchain profile --json
ai-stp toolchain install --tool <tool> --json
ai-stp toolchain harnesses --json
ai-stp toolchain harness-capabilities --json
```

`<tool>` — идентификатор, который закрепляет профиль. Если `doctor`
сообщил об отсутствующем инструменте, имя в `detail` этой проверки
или в `ecosystems[].tools` профиля. Не выдумывайте имя пакета.

Чтобы забрать управляемый инструмент:

```bash
ai-stp toolchain remove --tool <tool> --confirm --json
```

`--confirm` обязателен. Без него команда отказывает с
`AI_STP_USER_DECISION_REQUIRED`. Удаление трогает только пути, которые
создал этот CLI. Всё, чего нет в списке владения, остаётся на месте и
сообщается как `kept`.

## `toolchain profile`

Показать управляемый профиль toolchain, как он разрешается на этой машине.

```bash
ai-stp toolchain profile --json
```

Это чтение. Оно ничего не скачивает и ничего не ставит.

Успешный `data` называет:

| Поле | Что это |
| --- | --- |
| `profile` | какой это профиль |
| `platform` | для какой платформы он разрешился |
| `ecosystems` | каждый с `ecosystem`, `title`, `state`, `tools`, `reason` |
| `schema_version` | major схемы этого отчёта |

`state` экосистемы — `available` или `not_available`. Каждый
закреплённый инструмент несёт идентичность, версию, digest и источник
digest. `digest_source` — `vendor_published` или `pinned_on_download`.

## `toolchain install`

Установить один закреплённый инструмент в управляемый каталог. Из него
ничего не запускает.

```bash
ai-stp toolchain install --tool <tool> --json
```

Сначала план, затем проверка, затем распаковка рядом с целью, затем
перемещение одного указателя. Из архива ничего не исполняется. Вне
собственного каталога данных пользователя ничего не пишется, поэтому
здесь нет пути, которому понадобился бы пароль.

`action` в результате — то, что случилось, а не то, что пытались:

| `action` | Смысл |
| --- | --- |
| `installed` | инструмент положили и проверили |
| `already_installed` | закреплённые байты уже были текущими |
| `needs_user_action` | пришлось бы менять что-то вне управляемого каталога |

`needs_user_action` — не запрос секрета. `reason` говорит точно, что
пришлось бы изменить.

## `toolchain remove`

Удалить один управляемый инструмент, трогая только пути, которые создал
этот CLI.

```bash
ai-stp toolchain remove --tool <tool> --confirm --json
```

Destructive. Список — манифест владения. Решать в момент удаления,
какие файлы «похожи на наши», — способ забрать вместе с уборкой
данные пользователя, поэтому всё, чего нет в списке, остаётся на месте.

`action` — `removed`. `kept` называет пути, которые не принадлежали
этому CLI.

## `toolchain harnesses`

Сообщить о каждом поддерживаемом harness и есть ли он на этой машине.

```bash
ai-stp toolchain harnesses --json
```

Это обзор присутствия, а не жизненный цикл программы. `harness status`
отвечает на другой вопрос: какая программа стоит под одним prefix,
который поставил этот CLI. Словари у них разные нарочно.

Успешный `data` называет:

| Поле | Что это |
| --- | --- |
| `harnesses` | по одной строке на поддерживаемый harness |
| `schema_version` | major схемы этого отчёта |

Каждая строка называет `harness_id`, `title`, `support` (`primary`
или `beta`), `state` (`configured`, `installed`, `unknown_version`
или `available`), `installations`, `configuration` и `reason`.
Установка называет `path`, `version`, `version_source`, `surface`
(`cli` или `desktop`) и `diagnostic`.

Присутствие — не разрешение собирать состав для этого harness.
Eligibility — [Выбор](select.md). Уровни поддержки —
[Harnesses](../harnesses.md).

## `toolchain harness-capabilities`

По harness и kind: что продукт читает нативно, что этот билд умеет
проецировать, и почему любой gap — gap. Это не утверждение, что
компонент активен — это спрашивают у провайдера.

```bash
ai-stp toolchain harness-capabilities --json
```

Успешный `data` называет `harnesses`. Каждая строка — один harness, с
видами компонентов, нативными раскладками, способностью проекции и
`gaps`. Пробел — причина, а не подсказка изобрести обход.

Эта команда не спрашивает provider, активен ли компонент сейчас в
target. Этот вопрос принадлежит [Provider](provider.md) и
[Target](target.md).

## Что содержит успешный конверт

`install` и `remove` возвращают установку инструмента в `data`:

| Поле | Что это |
| --- | --- |
| `tool_id` | идентификатор, который вы передали |
| `version` | закреплённая версия |
| `action` | `installed`, `already_installed`, `needs_user_action` или `removed` |
| `reason` | почему исход именно такой |
| `binary` | где управляемый бинарник, или `null` |
| `paths` | пути, которые создала эта команда |
| `kept` | пути, которые эта команда отказалась трогать |
| `offline_capable` | можно ли воспроизвести результат из кэша |
| `schema_version` | major схемы этого отчёта |

`profile`, `harnesses` и `harness-capabilities` возвращают поля,
названные в своих разделах. Каждый конверт также несёт `ok`,
`warnings`, `next_actions`, `request_id`, `operation_id` и
`schema_version`.

## Чего эти команды никогда не делают

- не исполняют инструмент, который только что поставили;
- не пишут вне управляемого каталога;
- не ставят программу harness (`harness install`) и provider
  (`provider fetch`);
- не утверждают, что компонент активен в target;
- не кладут секрет в профиль или запись установки.

## Типичные отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` нет `--tool` | install и remove его требуют | передать `--tool <tool>` из профиля |
| `AI_STP_NOT_FOUND` | профиль не закрепляет инструмент с таким именем | `toolchain profile --json` и взять идентификатор из списка |
| `AI_STP_PRECONDITION_FAILED` нет артефакта для этой платформы | инструмент закреплён, но не для этой машины | читать `details.available`; не скачивать случайный бинарник |
| `AI_STP_USER_DECISION_REQUIRED` на remove | не было `--confirm` | `toolchain remove --tool <tool> --confirm --json` |
| `action: needs_user_action` | вне управляемого каталога нужно что-то изменить | читать `reason`; не давать CLI пароль |
| считать `harness-capabilities` за «установлено» | эта таблица — нативное чтение плюс проекция | `toolchain harnesses` и `harness status` |

## Связанные страницы

| Страница | Зачем |
| --- | --- |
| [Наблюдение](observe.md) | `doctor` после отсутствующего инструмента |
| [Программа harness](harness.md) | бинарник harness, не инструмент |
| [Provider](provider.md) | бинарник, который пишет нативное состояние |
| [Harnesses](../harnesses.md) | primary против beta |
| [Agent Skill CLI](skill.md) | другой отсутствующий объект первого запуска |
| [Быстрый старт для человека](../quickstart/human.md) | вкладка toolchain первого запуска |

!!! note "Флаги из `ai-stp help --agent --json`"
    Если `help --agent` расходится с флагом на этой странице, прав CLI.
    Необязательные флаги здесь не перечислены. Читайте их из дескриптора.
    `toolchain install` требует `--tool`. `toolchain remove` требует
    `--tool` и `--confirm`.
