---
title: "Отчёты"
description: "Подготовить, подтвердить и перечислить закрытые кейсы жалоб."
---

# Отчёты

Отчёт открывает закрытый модерационный кейс об одной точной версии объекта. Это не публичная дискуссия, не GitHub issue и не запись в паспорте. Содержимое ограничено и предварительно просматривается перед отправкой.

Preview ничего не записывает на сервер. Confirm отправляет ровно один предварительный просмотр после `--confirm`. List показывает закрытые кейсы этой учётной записи. Веб-сайт может открыть кейс того же типа; CLI — это путь, который привязывает точный дайджест содержимого, который у вас уже есть.

## Таблица команд

| Команда | Изменяемость | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp report preview` | `plan` | `none` | подготовка и отображение точного ограниченного содержимого без отправки |
| `ai-stp report confirm` | `apply` | `explicit_flag` | отправка ровно одного предварительного просмотра после явного подтверждения |
| `ai-stp report list` | `read` | `none` | список закрытых кейсов отчётов текущей учётной записи |

`--json` — глобальный флаг. Передавайте его всегда.

## Предпросмотр

```bash
ai-stp report preview \
  --kind component \
  --id <stable_id> \
  --version 1.0 \
  --content-digest sha256:... \
  --idempotency-key <key> \
  --json
```

`--kind` — `component` или `setup`. `--id`, `--version`, `--content-digest` и `--idempotency-key` обязательны.

Необязательный контекст, когда он у вас есть:

```bash
ai-stp report preview \
  --kind setup \
  --id <stable_id> \
  --version 1.0 \
  --content-digest sha256:... \
  --harness-id codex \
  --harness-version 0.140.1 \
  --provider-version 1.2.3 \
  --operation-id <operation_id> \
  --error-code AI_STP_PRECONDITION_FAILED \
  --validation-snapshot-id <snapshot_id> \
  --diagnostics-file ./diagnostics.txt \
  --vulnerability \
  --idempotency-key <key> \
  --json
```

`--harness-id`, `--harness-version`, `--provider-version` и `--operation-id` необязательны. `--error-code` — связанный зарегистрированный код ошибки. `--validation-snapshot-id` повторяемый. `--diagnostics-file` — ограниченный предварительно просмотренный файл UTF-8. `--vulnerability` отмечает возможную уязвимость безопасности.

Не помещайте секреты, токены, содержимое `.env` или персональные данные в файл диагностики. Preview показывает ровно то, что было бы отправлено.

Поля успеха: `plan_id`, `plan_digest`, `report`, `submitted`. `report` повторяет `object_kind`, `stable_id`, `version`, `content_digest`, `idempotency_key` и необязательные поля, которые вы задали. `submitted` равен false.

## Подтверждение

```bash
ai-stp report confirm \
  --plan-id <plan_id> \
  --plan-digest sha256:... \
  --confirm \
  --json
```

`--plan-id`, `--plan-digest` и `--confirm` обязательны. Дайджест — тот, что вернул `preview`. Изменившееся содержимое — это новый preview.

Поля успеха: `case_id`, `object_kind`, `stable_id`, `version`, `state`, `vulnerability`, `created_at`. Кейс закрыт: это не публичная ветка.

## Список

```bash
ai-stp report list --json
```

Поля успеха: `items`, каждый с `case_id`, `object_kind`, `stable_id`, `version`, `state`, `vulnerability`, `created_at`.

## Счастливый путь

```text
registry version --kind component --id <id> --version 1.0
→ скопируйте дайджест содержимого из проверенного паспорта
→ report preview --kind component --id <id> --version 1.0 --content-digest sha256:... --idempotency-key <key>
→ прочитайте содержимое
→ report confirm --plan-id <plan_id> --plan-digest sha256:... --confirm
→ report list
```

Если preview неверен, не подтверждайте. Создавайте новый preview с новым ключом идемпотентности только тогда, когда намерение действительно отличается.

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `preview` | `plan_id`, `plan_digest`, `report`, `submitted` |
| `confirm` | `case_id`, `state`, `vulnerability`, `created_at` |
| `list` | `items` |

## Отказы

| Что вы видите | Что это означает | Что делать |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | нет выполненного входа | `auth login` |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` был пропущен | передайте `--confirm` после чтения preview |
| `AI_STP_VALIDATION_ERROR` | отсутствует `--kind`, `--id`, `--version`, `--content-digest` или `--idempotency-key` | исправьте запрос |
| `AI_STP_PLAN_STALE` | `--plan-digest` больше не совпадает с сохранённым preview | сделайте preview снова |
| `AI_STP_NOT_FOUND` | id плана неизвестен | сначала `report preview` |
| `AI_STP_CONFLICT` | ключ идемпотентности уже именует другое содержимое | новый ключ для нового намерения |
| `AI_STP_PRECONDITION_FAILED` | файл диагностики не является ограниченным UTF-8, или дайджест не от этой версии | уменьшите файл; скопируйте дайджест из паспорта версии |
| помещение токена в диагностику | отчёты не должны содержать секреты | отредактируйте; сделайте preview снова |

Отметка об уязвимости не публикует CVE и не удаляет объект сама по себе. Она помечает закрытый кейс. Триаж персоналом выполняется на сервере.

## Связанные ссылки

- [Реестр](registry.md)
- [Объекты владельца](owner.md)
- [Публикация](publication.md)
- [Веб-отчёты](../web/reports.md)
- [Доверие и безопасность](../trust-and-safety/index.md)
- [Карта команд](commands.md)

## Справка для машины — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды отчётов для удобства поиска. Установленный CLI является источником флагов, схем и `next_actions`. Если эта страница и CLI расходятся, следуйте CLI.
