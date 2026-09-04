---
title: "Установка"
description: "Спланировать, одобрить, применить, отменить, восстановить и продолжить установку."
---

# Установка

Install считает неизменяемый план, записывает одобрение против digest этого
плана и просит public provider harness применить его. CLI сам нативное
состояние harness не пишет.

У плана нет собственного эффекта. Approve — решение пользователя. Apply —
запись provider, журналируемая здесь. Recover и resume осматривают или
завершают проверку результата; они не применяют план снова.

## Таблица команд

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp install plan` | `plan` | `none` | посчитать неизменяемый план установки |
| `ai-stp install approve` | `apply` | `plan_digest` | одобрить один план по его точному digest |
| `ai-stp install apply` | `apply` | `plan_digest` | выполнить один одобренный план через его provider |
| `ai-stp install cancel` | `apply` | `none` | отменить план до того, как что-либо применено |
| `ai-stp install status` | `read` | `none` | операции, остановившиеся без завершённого исхода |
| `ai-stp install recover` | `read` | `none` | что оставила одна остановившаяся операция; сама ничего не восстанавливает |
| `ai-stp install resume` | `apply` | `none` | закончить проверку результата, которую прерванный apply так и не сделал |

`--json` глобальный. Всегда передавайте его.

Approve подтверждается `--plan-digest` плана, который видел пользователь.
Apply **не** берёт флаг digest: одобрение уже привязало этот digest к
операции. В этой группе нет `--confirm`. Нет `--expected-plan-digest` у
`install plan`, `approve` или `apply`.

## Plan

Ровно одно из `--proposal` или `--setup` обязательно. `--setup` — это
`<stable_id>@<X.Y>`, и тогда обязателен `--project`. `--provider` обязателен
всегда.

```bash
ai-stp install plan \
  --proposal <proposal_id> \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

Из подготовленной версии сетапа:

```bash
ai-stp install plan \
  --setup setup_...@1.0 \
  --project . \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

`--action` — `install`, `update`, `backup`, `remove` или `rollback`.
Опустите для обычной установки. `--backup-ref` обязателен для rollback
протокола v3. `--scope` — `global` (по умолчанию), `project` или
`user_root`. `--target` обязателен для протокола v2/v3 и когда `--scope`
равен `project` или `user_root`.

`--provider-manifest` обязателен для протокола v3, если не дан
`--unverified-provider`. `--provider-build-attestation` проверяет точные
байты provider через репозиторий, source commit и signer workflow,
закреплённые локальной политикой. `--provider-attestation-bundle` —
необязательный локальный GitHub attestation bundle для офлайн-проверки.
`--provider-release-recovery` явно восстанавливает более старый точный
релиз provider, уже проверенный на этой машине. `--permission-profile` —
объявленная provider поза исполнения, отдельно от идентичности сетапа.

Намеренный backup:

```bash
ai-stp install plan \
  --action backup \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

Восстановление из копии, которой владеет provider, использует
`--action rollback` и `--backup-ref`. Это не `target rollback`, который
только **называет** предыдущую версию. См. [Target](target.md) и
[Сетапы](../setups/index.md).

## Approve

```bash
ai-stp install approve \
  --operation <operation_id> \
  --plan-digest sha256:... \
  --json
```

`--operation` и `--plan-digest` обязательны. Digest — подтверждение.
Флаг со смыслом «что сейчас передо мной» не принимается. Изменённый план —
новая операция.

## Apply

```bash
ai-stp install apply \
  --operation <operation_id> \
  --provider <exe> \
  --json
```

`--operation` и `--provider` обязательны. Операция уже должна быть
одобрена. Apply повторно проверяет target, даёт provider действовать,
записывает `applied_unverified` до взгляда, затем верифицирует. Прерванный
вызов provider — `partial`, никогда не угаданный отказ: таймаут не доказывает,
что ничего не случилось.

После неподтверждённого таймаута читайте `install status` и
`install recover`. Не применяйте снова, пока не знаете, что операция всё
ещё `approved`.

## Cancel, status, recover, resume

```bash
ai-stp install cancel --operation <operation_id> --reason "changed composition" --json
ai-stp install status --json
ai-stp install recover --operation <operation_id> --json
ai-stp install resume --operation <operation_id> --provider <exe> --json
```

Cancel отклоняется, как только применение началось. `--reason` необязателен.

`status` перечисляет операции, остановившиеся без завершённого исхода.
`partial` появляется здесь, хотя он терминальный: кому-то всё равно нужно
восстанавливать.

`recover` — read. Сообщает `operation_id`, `state`, `backup_ref`,
`effects_recorded`, `next_actions`. Ничего не восстанавливает.

`resume` заканчивает проверку результата, которую прерванный apply так и
не сделал. Ничего не применяет. `--operation` и `--provider` обязательны.

## Happy path

```text
select confirm --proposal <id>
→ install plan --proposal <id> --provider <exe> --provider-manifest <path> --protocol-version 3 --target <dir>
→ прочитать operation_id и plan_digest
→ install approve --operation <id> --plan-digest sha256:...
→ install apply --operation <id> --provider <exe>
→ target status --project <id> --harness <id>
```

Намеренное восстановление из заранее снятой копии:

```text
install plan --action backup … → approve --plan-digest → apply
→ target backups --project <id> --harness <id>
→ install plan --action rollback --backup-ref <exact> …
→ approve --plan-digest → apply
→ target status
```

## Именованные поля успеха

Каждый ответ plan / approve / apply / cancel / resume — вид установки.
Читайте как минимум:

| Поле | Смысл |
| --- | --- |
| `operation_id` | id журнала, который передаёте дальше |
| `plan_digest` | точный digest, который `approve` должен повторить |
| `action` | `install`, `update`, `backup`, `remove`, `rollback` |
| `state` | `planned`, `approved`, `applying`, `applied_unverified`, `verified`, `partial`, `failed`, `stale`, `cancelled`, `rolled_back` |
| `backup_ref` | копия provider, если план её снял |
| `expected_target_digest` | чем должен стать target |
| `provider_plan_digest` | собственные байты плана provider |
| `provider_release_trusted` | приняла ли закреплённая политика этого provider |
| `provider_release_trust` | `verified_publisher`, `signed`, `build_attested` или `unverified` |
| `effects` | перечисленные эффекты плана |
| `managed_paths` | пути, которыми будет владеть provider |
| `steps` | append-only журнал этой операции |
| `expires_at` | когда ещё planned операция станет stale |

`recover` добавляет `next_actions` и `effects_recorded` для одной
остановившейся операции. `status` перечисляет их как `stopped`.

## Отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | оба или ни одного из `--proposal` / `--setup`, или нет `--target` для v2/v3 | назвать ровно один источник; добавить `--target` |
| `AI_STP_USER_DECISION_REQUIRED` | на approve не передали `--plan-digest` | передать digest, который нёс ответ плана |
| `AI_STP_PLAN_STALE` | байты плана или предусловия изменились | планировать снова; старый digest не переносится |
| `AI_STP_PRECONDITION_FAILED` | apply до approve, или target сдвинулся | `install status`; не выдумывать digest |
| `AI_STP_CONFLICT` | другую операцию держит эта пара | подождать или recover другой операции |
| `AI_STP_TIMEOUT_UNCONFIRMED` | apply истек без подтверждённого эффекта | `install recover`; пока не apply снова |
| `AI_STP_PARTIAL_OPERATION` | provider остановился посреди записи | `recover`, затем `resume` или новый план, как скажет `next_actions` |
| `AI_STP_UNSUPPORTED_APPLY` | этот harness так применять нельзя | остановиться; не подменять другим harness |
| cancel после начала apply | cancel отклоняется | recover; не удалять backup руками |
| `--expected-plan-digest` на approve | этого флага здесь нет | использовать `--plan-digest` |

Не удаляйте target и backup руками, пока восстановление не закончено.
Не восстанавливайте один компонент: восстановление возвращает target
целиком.

## Связанные страницы

- [Выбор](select.md)
- [Target](target.md)
- [Provider](provider.md)
- [Команды сетапа](setup.md)
- [Сетапы](../setups/index.md)
- [Телеметрия установки](telemetry.md)
- [Диагностика](../troubleshooting/index.md)
- [Карта команд](commands.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды установки, чтобы человек их нашёл.
Установленный CLI — источник флагов, схем и `next_actions`. Если страница
и CLI расходятся, следуйте CLI.
