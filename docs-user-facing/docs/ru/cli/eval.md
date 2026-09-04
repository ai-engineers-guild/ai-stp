---
title: "Eval"
description: "Привязать эталонный evaluation-профиль к локальному сетапу и запустить его."
---

# Eval

Eval привязывает версионированный эталонный evaluation-профиль к одному
конкретному локальному графу сетапа и выполняет локальные детерминированные
проверки. Он не устанавливает, не публикует и не обращается к API модели.

Профиль одинаков для всех вызывающих. План фиксирует сетап, harness,
провайдер и раннер. Запуск подтверждается дайджестом плана. Команды status
и show читают неизменяемые локальные свидетельства. Повторный `eval show`
с тем же `run_id` возвращает те же байты.

## Таблица команд

| Команда | Изменяемость | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp eval profile` | `read` | `none` | показать версионированный эталонный профиль для всех или одного типа компонента |
| `ai-stp eval plan` | `plan` | `none` | привязать этот профиль к одному конкретному локальному графу сетапа |
| `ai-stp eval run` | `apply` | `plan_digest` | выполнить локальные детерминированные проверки для одного подтверждённого точного плана |
| `ai-stp eval status` | `read` | `none` | прочитать неизменяемый статус одного локального evaluation-запуска |
| `ai-stp eval show` | `read` | `none` | показать полные неизменяемые локальные свидетельства одного evaluation-запуска |

`--json` — глобальный флаг. Всегда передавайте его. `eval run` требует
`--expected-plan-digest`. Флага `--confirm` не существует.

## Profile

```bash
ai-stp eval profile --json
ai-stp eval profile --type skill --json
```

`--type` опционален. Если указан — одно из значений: `instruction`, `skill`,
`mcp`, `hook`, `command`, `agent`, `plugin`, `setting`.

Поля успеха: `profile_id`, `scope`, `component_types`, `preconditions`,
`checks`, `eval_permissions`, `profile_version`. Каждая проверка содержит
`check_id`, `method`, `runner`, `assertion`, `tolerance`, `budget`.
Permissions перечисляют `filesystem`, `network` и `process` posture.
Поля бюджета включают `timeout_seconds` и `max_output_bytes`.

## Plan

```bash
ai-stp eval plan \
  --setup-id <setup_id> \
  --setup-version 1.0 \
  --harness-version 0.140.1 \
  --provider-version 1.2.3 \
  --runner-version 1.0.0 \
  --json
```

Обязательные: `--setup-id`, `--setup-version`, `--harness-version`,
`--provider-version`, `--runner-version`. `--component-id` — повторяемый:
опциональное точное подмножество графа сетапа.

Сетап уже должен существовать локально в точной версии `X.Y`. Eval его
не собирает.

Поля успеха: `plan_id`, `plan_digest`, `profile`, `setup_id`,
`setup_version`, `setup_passport_digest`, `setup_artifact_digest`,
`harness_id`, `harness_version`, `provider_version`, `runner_version`,
`components`, `planned_at`. Каждая координата компонента содержит `stable_id`,
`version`, `passport_digest`, `artifact_digest`, `component_type`.

## Run

```bash
ai-stp eval run \
  --plan-id <plan_id> \
  --expected-plan-digest sha256:... \
  --json
```

`--plan-id` и `--expected-plan-digest` обязательны. Дайджест — тот, что
вернул `eval plan`. Изменённый граф — это новый план.

Запуск выполняет local-static проверки из профиля. Он не применяет
сетап и не обращается к модели.

Поля успеха: `run_id`, `result_digest`, `plan`, `status`, `executed_at`,
`checks`. Каждый результат проверки содержит `check_id`, `method`, `runner`, `status`,
`message`. Также присутствуют: `immutable_published_bytes_changed`,
`provider_permissions_used`.

## Status и show

```bash
ai-stp eval status --run-id <run_id> --json
ai-stp eval show --run-id <run_id> --json
```

`--run-id` обязателен. Оба ответа используют ту же схему результата. `status` —
краткое неизменяемое представление; `show` — полные свидетельства. Ни одна
из команд не перезапускает проверки.

## Счастливый путь

```text
select confirm --proposal <id>          # или setup compose apply
→ eval profile --type skill
→ eval plan --setup-id <id> --setup-version <X.Y> --harness-version … --provider-version … --runner-version …
→ eval run --plan-id <plan_id> --expected-plan-digest sha256:...
→ eval status --run-id <run_id>
→ eval show --run-id <run_id>
```

Зелёный eval — локальное свидетельство. Это не `component_verified`, не
публикация и не установка. Подписанные аттестации добавляются через
`attestation sign`, когда они нужны плану публикации.

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `profile` | `profile_id`, `checks`, `eval_permissions` |
| `plan` | `plan_id`, `plan_digest`, `setup_passport_digest`, `components` |
| `run` / `status` / `show` | `run_id`, `result_digest`, `status`, `checks`, `executed_at` |

Для запуска также читайте `immutable_published_bytes_changed` и
`provider_permissions_used`. Изменение опубликованных байтов во время eval —
сигнал остановиться, а не деталь, которую можно проигнорировать.

## Отказы

| Что вы видите | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | отсутствует обязательная версия или id, либо `--type` не входит в закрытый набор | прочитайте descriptor |
| `AI_STP_NOT_FOUND` | такая версия сетапа или id плана отсутствуют локально | сначала compose или confirm сетап |
| `AI_STP_PLAN_STALE` | `--expected-plan-digest` больше не совпадает | выполните `eval plan` заново |
| `AI_STP_PRECONDITION_FAILED` | предварительное условие профиля не выполнено | прочитайте `preconditions`; исправьте граф |
| `AI_STP_USER_DECISION_REQUIRED` | дайджест не передан | передайте `--expected-plan-digest` |
| интерпретация `status: failed` как `ok: false` | envelope всё ещё может быть успешным отчётом о проваленных проверках | читайте `status` и `message` каждой проверки |
| изобретение `--confirm` | запуск подтверждается дайджестом плана | не добавляйте boolean-флаг |
| просьба eval вызвать модель | этот продукт этого не делает | остановитесь; флага для ключа модели не существует |

Eval permissions — это заявленная posture профиля. Это не установка
провайдера и не сетевое исключение для harness.

## Связанные ссылки

- [Select](select.md)
- [Setup commands](setup.md)
- [Publication](publication.md)
- [Security checks](../security-checks.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Command map](commands.md)

## Machine help — источник парсера

```bash
ai-stp help --agent --json
```

Эта страница группирует команды eval, чтобы человек мог их найти.
Установленный CLI — источник флагов, схем и `next_actions`. Если эта
страница и CLI расходятся, следуйте CLI.
