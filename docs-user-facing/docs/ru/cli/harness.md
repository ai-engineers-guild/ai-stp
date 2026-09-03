---
title: "Программа harness"
description: "Установка, обновление, удаление и состояние программы harness."
---

# Программа harness

Эти команды устанавливают *программу* harness — бинарный файл в конкретном
prefix — не сетап, не компонент и не провайдер.
Провайдер — отдельный бинарный файл, который позже записывает нативное
состояние. Применение сетапа описано в [Install](install.md). Обзор
видимых на машине harness — `toolchain harnesses`.

Объект — программа в `--prefix`, а не конфигурация в `--target`. Путаница
между этими двумя путями — способ, которым сетап оказывается в директории
программы, а бинарный файл — в проекте.

## Команды

| Команда | Изменяемость | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp harness install` | `apply` | `none` | Установить саму программу harness в конкретный prefix. |
| `ai-stp harness update` | `apply` | `none` | Перевести программу harness на версию, которую фиксирует провайдер. |
| `ai-stp harness remove` | `destructive` | `explicit_flag` | Удалить программу harness, установленную этим CLI, и ничего больше. |
| `ai-stp harness resume` | `apply` | `none` | Завершить остановленную операцию программы, только проверив состояние, никогда не применяя повторно. |
| `ai-stp harness status` | `read` | `none` | Какая программа находится в данном prefix — по журналу и диску. |

`install`, `update` и `remove` требуют `--harness`, `--prefix` и
`--target`. `remove` также требует `--confirm`. `status` требует
`--harness` и `--prefix`. `resume` требует `--operation`.

`--prefix` — абсолютный путь к директории, в которой находится программа.
Это не target. `--target` — абсолютный путь к конфигурационному target
harness.

## Типичный путь

```bash
ai-stp toolchain harnesses --json
ai-stp harness status --harness codex --prefix <prefix> --json
ai-stp harness install --harness codex --prefix <prefix> --target <target> --json
ai-stp harness status --harness codex --prefix <prefix> --json
```

`<prefix>` и `<target>` — абсолютные пути. `--harness` — одно из значений:
`claude-code`, `codex`, `pi`, `opencode`, `grok-build`, `cursor`,
`antigravity`.

Если операция остановилась без завершённого результата:

```bash
ai-stp harness resume --operation <operation> --json
ai-stp harness status --harness codex --prefix <prefix> --json
```

`resume` завершает, проверяя состояние, никогда не применяя повторно. Это
то же правило, что и для `install resume` сетапов: повторный запуск эффекта
создаёт вторую копию, а не восстанавливает первую.

Переход на версию, зафиксированную провайдером:

```bash
ai-stp harness update --harness codex --prefix <prefix> --target <target> --json
```

Удаление только того, что установил этот CLI:

```bash
ai-stp harness remove --harness codex --prefix <prefix> --target <target> --confirm --json
```

## `harness install`

Устанавливает саму программу harness в конкретный prefix.

```bash
ai-stp harness install --harness codex --prefix <prefix> --target <target> --json
```

Исполняемый файл провайдера определяется при отсутствии `--provider`:
явный путь, затем конфигурация, затем запомненный выбор, затем discovery.
Опциональные флаги описаны в machine help. Не изобретайте путь провайдера.

`state` после успешного применения — то, что сообщил провайдер.
`verified` — единственное состояние, означающее, что программа установлена
и её идентификатор подтверждён.

## `harness update`

Переводит программу harness на версию, зафиксированную провайдером.

```bash
ai-stp harness update --harness codex --prefix <prefix> --target <target> --json
```

Те же обязательные опции, что и у install. Это не `provider update`.
Обновление бинарного файла провайдера — [Provider](provider.md). Эта
команда обновляет *программу harness*, которую провайдер предоставляет в
prefix.

## `harness remove`

Удаляет программу harness, установленную этим CLI, и ничего больше.

```bash
ai-stp harness remove --harness codex --prefix <prefix> --target <target> --confirm --json
```

Destructive. `--confirm` обязателен. Без него команда отказывает с
`AI_STP_USER_DECISION_REQUIRED`. Программа, не установленная этим CLI,
не удаляется. Нативная конфигурация в `--target` не удаляется.
Кэшированные байты каталога не удаляются.

## `harness resume`

Завершает остановленную операцию программы, только проверяя состояние,
никогда не применяя повторно.

```bash
ai-stp harness resume --operation <operation> --json
```

`--operation` обязателен. Он указывает запись журнала, которая остановилась.
Опциональные assert-флаги (`--harness`, `--prefix`, `--target`) берутся из
операции, если не указаны; другое значение отклоняется. Прочитайте их в
machine help, если нужно зафиксировать.

Resume не загружает вторую копию. Он проверяет, что уже есть на диске и в
журнале, и записывает завершённое состояние.

## `harness status`

Какая программа находится в данном prefix — по журналу и диску.

```bash
ai-stp harness status --harness codex --prefix <prefix> --json
```

Два независимых источника, намеренно: журнал говорит, что сделала эта
установка, файловая система — что сейчас там. Сообщение только первого
назвало бы верифицированную операцию успешной на пустом prefix.

`version` берётся из журнала, никогда — из запуска программы. Запрос
версии у бинарного файла означал бы выполнение чужого исполняемого файла
из команды, объявленной как `read`.

Поля успешного `data`:

| Поле | Что это |
| --- | --- |
| `harness_id` | harness, о котором вы спросили |
| `prefix` | директория, которую вы указали |
| `state` | `present`, `removed`, `never_installed`, `foreign`, `lost` или `interrupted` |
| `reason` | почему это состояние таково |
| `entry_point` | экспонированный путь в prefix |
| `executable` | имя программы, как записано |
| `version` | версия, записанная журналом |
| `operation_id` | последняя записанная операция, если есть |
| `recorded_at` | когда журнал последний раз писал |
| `recorded_operation` | `software_install`, `software_update` или `software_remove` |
| `recorded_state` | что журнал последний раз записал |
| `stopped` | операции, остановившиеся без завершённого результата |
| `schema_version` | major-версия схемы этого отчёта |

`lost` означает: журнал говорит verified, а prefix не содержит файлов.
Это отчёт, а не указание немедленно переустановить без чтения.

## Что содержит успешный envelope

`install`, `update`, `remove` и `resume` возвращают операцию программы
в `data`:

| Поле | Что это |
| --- | --- |
| `harness_id` | harness |
| `prefix` | prefix программы |
| `operation` | `software_install`, `software_update` или `software_remove` |
| `operation_id` | запись журнала |
| `plan_digest` | точный план, который был выполнен |
| `state` | что провайдер сообщил после эффекта |
| `version` | версия программы |
| `executable` | экспонированный исполняемый файл |
| `artifacts` | архивы, названные планом |
| `effects` | что изменилось |
| `recovered` | что resume завершил |
| `removed` | забрал ли remove программу обратно |
| `schema_version` | major-версия схемы этого отчёта |

`status` возвращает поля статуса выше. Каждый envelope также содержит
`ok`, `warnings`, `next_actions`, `request_id`, `operation_id` и
`schema_version`.

## Prefix не target не provider

| Путь | Что это | Команда |
| --- | --- | --- |
| `--prefix` | где находится программа harness | эта страница |
| `--target` | где живёт нативная конфигурация | [Install](install.md), [Target](target.md) |
| provider executable | бинарный файл, пишущий target | [Provider](provider.md) |

`toolchain harnesses` отвечает на вопрос «виден ли этот harness на
машине». `harness status` отвечает «что этот CLI положил в этот prefix».
Не используйте одно вместо другого.

## Что эти команды никогда не делают

- не применяют сетап и не записывают нативную конфигурацию как цель
  команды;
- не запускают программу harness для получения версии из `status`;
- не удаляют программу, не установленную этим CLI;
- не заменяют `provider update` или `toolchain install`;
- не пропускают `--confirm` при remove.

## Типичные отказы

| Что вы видите | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` отсутствует `--harness` / `--prefix` / `--target` | эти опции обязательны для install, update и remove | передайте все три; для status нужны harness и prefix |
| `AI_STP_USER_DECISION_REQUIRED` при remove | `--confirm` отсутствует | добавьте `--confirm` после явного решения |
| `AI_STP_NOT_FOUND` при resume | такой операции нет в журнале | `harness status`, прочитайте `stopped` |
| `AI_STP_PRECONDITION_FAILED` | prefix, target или провайдер не совпадают с планом | не переиспользуйте argv от другого prefix |
| `state: foreign` | этот prefix принадлежит чему-то другому | не делайте `remove`; этот CLI его не устанавливал |
| `state: lost` | журнал verified, диск пуст | прочитайте `reason`; resume или восстановление, не слепая переустановка |
| `state: interrupted` | операция остановилась | `harness resume --operation <operation> --json` |

## Связанные страницы

| Страница | Зачем |
| --- | --- |
| [Toolchain](toolchain.md) | обзор присутствия и возможностей |
| [Provider](provider.md) | бинарный файл, пишущий нативное состояние |
| [Install](install.md) | применение сетапа через этот провайдер |
| [Target](target.md) | текущее состояние проекта и harness |
| [Harnesses](../harnesses.md) | основная и бета-поддержка |
| [Agent Skill CLI](skill.md) | skill, который программа будет читать |
| [Quickstart](../quickstart.md) | первый запуск, когда программа отсутствует |

!!! note "Флаги из `ai-stp help --agent --json`"
    Если `help --agent` расходится с флагом на этой странице, CLI побеждает.
    Опциональные флаги здесь не перечислены. Читайте их из descriptor.
    `harness install` и `harness update` требуют `--harness`,
    `--prefix` и `--target`. `harness remove` также требует
    `--confirm`. `harness resume` требует `--operation`.
