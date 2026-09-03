---
title: "Доступ"
description: "Приглашение, грант, принятие и отзыв доступа к major-линии."
---

# Доступ

Грант передаёт другому аккаунту доступ к одному конкретному объектному
**major-линии**. Это не установка сетапа, не запись в каталоге и не
редактирование паспорта. Локальные байты остаются на машинах, где они уже
есть. Отзыв работает только вперёд.

Эти команды требуют авторизованного аккаунта. Токен приглашения читается
из именованной переменной окружения. Он никогда не передаётся как флаг
командной строки.

## Таблица команд

| Команда | Изменяемость | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp grant list` | `read` | `none` | приглашения и гранты major-линии, принадлежащие текущему аккаунту |
| `ai-stp grant invite` | `apply` | `explicit_flag` | создать email-приглашение для одной точной major-линии объекта |
| `ai-stp grant direct` | `apply` | `explicit_flag` | выдать грант одной точной major-линии явному идентификатору аккаунта |
| `ai-stp grant accept` | `apply` | `explicit_flag` | принять приглашение по токену из именованной переменной окружения |
| `ai-stp grant invitation revoke` | `destructive` | `explicit_flag` | отозвать одно ожидающее приглашение без удаления локальных байтов |
| `ai-stp grant revoke` | `destructive` | `explicit_flag` | отозвать один активный грант только вперёд, сохраняя локальные байты |

`--json` — глобальный флаг. Всегда передавайте его. Каждая изменяющая команда
требует `--confirm` и `--idempotency-key`.

## List

```bash
ai-stp grant list --json
```

Поля успеха: `grants`, `invitations`. Каждый грант содержит `grant_id`,
`object_kind`, `stable_id`, `major`, `state`, `owner_account_id`,
`grantee_account_id`, `recipient`, `recipient_kind`, `created_at`,
`revoked_at`. Каждое приглашение содержит `invitation_id`, `object_kind`,
`stable_id`, `major`, `state`, `created_at`, `expires_at`.

## Invite

```bash
ai-stp grant invite \
  --kind component \
  --id <stable_id> \
  --major 1 \
  --email user@example.com \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--kind` — `component` или `setup`. `--id` — стабильный идентификатор объекта.
`--major` — точная major-линия. `--email` — верифицированный адрес получателя.
`--ttl-seconds` опционален; по умолчанию — семь дней.
`--idempotency-key` и `--confirm` обязательны.

Ответ — приглашение: `invitation_id`, `object_kind`, `stable_id`,
`major`, `state`, `created_at`, `expires_at`. Токен **не** содержится в
envelope. Он доставляется out-of-band.

## Direct

```bash
ai-stp grant direct \
  --kind setup \
  --id <stable_id> \
  --major 1 \
  --recipient-kind github_username \
  --recipient octocat \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--recipient-kind` — `github_username` или `user_id`. `--recipient` — значение
в этом пространстве имён. `--kind`, `--id`, `--major`, `--idempotency-key`
и `--confirm` обязательны.

Ответ — грант доступа: `grant_id`, `object_kind`, `stable_id`,
`major`, `state`, `owner_account_id`, `grantee_account_id`, `recipient`,
`recipient_kind`, `created_at`, `revoked_at`.

## Accept

```bash
ai-stp grant accept \
  --invitation-id <invitation_id> \
  --token-env AI_STP_GRANT_TOKEN \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--token-env` именует переменную окружения, содержащую токен приглашения.
Не передавайте токен как флаг. Ответ — грант доступа той же формы, что и
у `direct`.

## Revoke invitation, revoke grant

```bash
ai-stp grant invitation revoke \
  --invitation-id <invitation_id> \
  --reason "issued to the wrong address" \
  --idempotency-key <key> \
  --confirm \
  --json

ai-stp grant revoke \
  --grant-id <grant_id> \
  --reason "access no longer needed" \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--reason` опционален. Оба ответа содержат `revoked` и
`local_bytes_retained`. Локальные байты сохраняются. Отзыв не удаляет
установленный target.

`grant invitation revoke` и `grant revoke` — `destructive`. Это отдельное
решение, отличное от просмотра списка или приглашения.

## Счастливый путь

Приглашение:

```text
grant list
→ grant invite --kind component --id <id> --major 1 --email <addr> --idempotency-key <key> --confirm
→ grant list
```

Принятие на машине получателя:

```text
# токен уже в именованной переменной окружения
grant accept --invitation-id <id> --token-env AI_STP_GRANT_TOKEN --idempotency-key <key> --confirm
→ grant list
```

Direct:

```text
grant direct --kind setup --id <id> --major 1 --recipient-kind user_id --recipient <account_id> --idempotency-key <key> --confirm
```

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `list` | `grants`, `invitations` |
| `invite` | `invitation_id`, `expires_at`, `state` |
| `direct` / `accept` | `grant_id`, `grantee_account_id`, `major`, `state` |
| `invitation revoke` / `revoke` | `revoked`, `local_bytes_retained` |

## Отказы

| Что вы видите | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | нет авторизованного аккаунта | `auth login` |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` не передан | передайте `--confirm` после проверки kind, id и major |
| `AI_STP_VALIDATION_ERROR` | отсутствует `--idempotency-key`, `--token-env` или `--kind` | прочитайте descriptor; `--kind` — `component` или `setup` |
| `AI_STP_PERMISSION_DENIED` | этот аккаунт не владеет данной major-линией | `owner objects`; нельзя выдать грант на чужой объект |
| `AI_STP_NOT_FOUND` | приглашение, грант или объект неизвестны | `grant list` |
| `AI_STP_CONFLICT` | idempotency key уже именует другое намерение | используйте новый ключ или повторно применяйте ключ только для того же намерения |
| `AI_STP_PRECONDITION_FAILED` | приглашение истекло или уже отозвано | `grant list`; отправьте новое приглашение |
| токен в командной строке | такой опции не существует | поместите его в переменную окружения и укажите имя переменной |

Major-линия — граница доступа. `--major 1` не даёт доступ к `2.x`.
Открытие новой major-версии через `component version release --major` —
другая команда.

## Связанные ссылки

- [Owner objects](owner.md)
- [Sign-in](auth.md)
- [Publication](publication.md)
- [Web access](../web/access.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Command map](commands.md)

## Machine help — источник парсера

```bash
ai-stp help --agent --json
```

Эта страница группирует команды grant, чтобы человек мог их найти.
Установленный CLI — источник флагов, схем и `next_actions`. Если эта
страница и CLI расходятся, следуйте CLI.
