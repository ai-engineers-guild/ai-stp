---
title: "Публикация"
description: "Подписать attestation, спланировать, просмотреть и подтвердить публикацию компонента."
---

# Публикация

Публикация создаёт неизменяемый серверный план для одной точной выпущенной версии компонента и подтверждает этот план по его хешу. Подписание аттестации привязывает тестовые данные, зависящие от учётных данных, к активному ключу устройства.

План не делает версию публичной. Confirm делает. Неудавшаяся проверка не должна оставлять частично опубликованную версию. `author_verified` по-прежнему не означает, что содержимое безопасно.

## Таблица команд

| Команда | Изменяемость | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp attestation sign` | `apply` | `explicit_flag` | подписание точных тестовых данных, зависящих от учётных данных, активным ключом устройства |
| `ai-stp publication plan` | `plan` | `none` | создание неизменяемого серверного плана для одной точной выпущенной версии компонента |
| `ai-stp publication status` | `read` | `none` | чтение текущего серверного состояния одного плана публикации |
| `ai-stp publication confirm` | `apply` | `explicit_flag` | подтверждение одного точного неистёкшего хеша плана публикации |

`--json` — глобальный флаг. Передавайте его всегда.

`attestation sign` требует `--confirm`. `publication confirm` требует `--plan-hash` и `--confirm`. Для всего графа сетапа используйте `setup publish plan` / `setup publish confirm` вместо подтверждения каждого участника вручную.

## Подпись аттестации

Подписание наблюдаемых тестовых данных локально. Выходной файл — JSON только для владельца. Команда не загружает его.

```bash
ai-stp attestation sign \
  --id <stable_id> \
  --version 1.0 \
  --check-id <check_id> \
  --policy-version <policy> \
  --harness-id codex \
  --harness-version 0.140.1 \
  --provider-version 1.2.3 \
  --test-case-id <case_id> \
  --result passed \
  --output ./attestation.json \
  --confirm \
  --json
```

Обязательны: `--id`, `--version`, `--check-id`, `--policy-version`, `--harness-id`, `--harness-version`, `--provider-version`, `--test-case-id` (повторяемый), `--result` (`passed` или `failed`), `--output`, `--confirm`. `--tool-version` — повторяемый `name=version`.

Поля успеха: `object_digest`, `subject`, `check_id`, `policy_version`, `harness_id`, `harness_version`, `provider_version`, `test_case_ids`, `result`, `account_id`, `device_id`, `attested_at`, `signature`, `output_path`, `attestation_digest`.

Передайте `--output` в `publication plan --attestation-file` позже. Не помещайте секреты в файл аттестации.

## План публикации

```bash
ai-stp publication plan --id <stable_id> --version 1.0 --json
ai-stp publication plan \
  --id <stable_id> \
  --version 1.0 \
  --attestation-file ./attestation.json \
  --json
```

`--id` — стабильный идентификатор выпущенного компонента. `--version` — точный локальный `X.Y`. `--attestation-file` повторяемый.

Версия должна быть уже выпущена (`component version release`). Устройство активной сессии должно совпадать с подписантом любой прикреплённой аттестации.

Поля успеха: `plan_id`, `plan_hash`, `state`, `object_kind`, `stable_id`, `version`, `content_digest`, `component_verified`, `policy_version`, `actor_id`, `device_id`, `effects`, `evidence`, `expires_at`. Читайте `effects` перед подтверждением. `component_verified` здесь — это записанный бит плана, а не причина пропустить проверку хеша.

## Статус

```bash
ai-stp publication status --plan-id <plan_id> --json
```

`--plan-id` обязателен. Ответ — то же представление publication-plan. Подтверждайте только неистёкший план, чей `plan_hash` по-прежнему совпадает.

## Подтверждение

```bash
ai-stp publication confirm \
  --plan-id <plan_id> \
  --plan-hash sha256:... \
  --confirm \
  --json
```

`--plan-id` и `--plan-hash` обязательны. `--confirm` — явный флаг. Хеш — тот, что вернул `plan`. Изменившийся план — это новый план.

Ответ — представление плана в его новом `state`. Следуйте через `publication status`, если конверт говорит ждать, или через `owner version show`, чтобы увидеть публичную версию.

## Счастливый путь

Компонент:

```text
component passport validate --id <id>
→ component version release --id <id>
→ attestation sign … --output ./attestation.json --confirm   # когда требуются доказательства
→ publication plan --id <id> --version <X.Y> --attestation-file ./attestation.json
→ publication status --plan-id <plan_id>
→ publication confirm --plan-id <plan_id> --plan-hash <hash> --confirm
→ owner version show --kind component --id <id> --version <X.Y>
```

Встроенный участник:

```text
component publish --from-setup <setup> --setup-version <X.Y> --component-id <id>
→ publication confirm --plan-id <plan_id> --plan-hash <hash> --confirm
```

Весь граф сетапа: [Команды сетапа](setup.md) `setup publish plan`, затем `setup publish confirm --set-digest … --confirm`.

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `attestation sign` | `output_path`, `attestation_digest`, `signature`, `result` |
| `publication plan` / `status` / `confirm` | `plan_id`, `plan_hash`, `state`, `effects`, `evidence`, `expires_at` |

Также читайте `content_digest`, `component_verified` и `policy_version` в плане. Они должны совпадать с версией, которую вы планировали.

## Отказы

| Что вы видите | Что это означает | Что делать |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | нет выполненного входа | `auth login` |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` был пропущен | передайте `--confirm` после чтения `effects` |
| `AI_STP_VALIDATION_ERROR` | отсутствует `--id`, `--version`, `--plan-id` или `--plan-hash` | прочитайте дескриптор |
| `AI_STP_PRECONDITION_FAILED` | аттестация не привязана к этой версии, устройству и учётной записи | подпишите снова на этом устройстве после входа |
| `AI_STP_PLAN_STALE` / истёкший `expires_at` | план больше не актуален | `publication plan` снова |
| `AI_STP_PERMISSION_DENIED` | эта учётная запись не может публиковать данный id | `owner object show` |
| `AI_STP_CONFLICT` | параллельная публикация той же версии | `publication status`; не подтверждайте второй хеш |
| `AI_STP_NOT_FOUND` | версия никогда не была выпущена локально, или id плана неизвестен | `component version list` |
| интерпретация `component_verified` как безопасности | происхождение и проверки, а не гарантия | читайте [Доверие и безопасность](../trust-and-safety/index.md) |

Публичная версия должна происходить из публичного репозитория GitHub на точном коммите и подпути. Происхождение только из локальных источников отклоняется на этапе планирования.

## Связанные ссылки

- [Публикация компонента](component-publish.md)
- [Команды сетапа](setup.md)
- [Объекты владельца](owner.md)
- [Оценка](eval.md)
- [Публикация](../publishing/index.md)
- [Авторство](../publishing/authoring.md)
- [Проверки безопасности](../security-checks.md)
- [Доверие и безопасность](../trust-and-safety/index.md)
- [Карта команд](commands.md)

## Справка для машины — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды публикации для удобства поиска. Установленный CLI является источником флагов, схем и `next_actions`. Если эта страница и CLI расходятся, следуйте CLI.
