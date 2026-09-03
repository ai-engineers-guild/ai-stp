---
title: "Провайдер"
description: "Проверить, загрузить, оценить доверие и заменить бинарник, который пишет нативное состояние harness."
---

# Провайдер

Провайдер — это публичный менеджер сетапов NDDev для одного харнеса. Он является единственным записывающим финальное состояние этого харнеса. Эти команды проверяют, что установлено, получают аттестованный релиз, сообщают о доверии и сетевой изоляции, а также заменяют или переустанавливают бинарный файл по тому же пути.

Они не устанавливают сетап. После того как байты провайдера привязаны, компоновка и применение по-прежнему идут через [Select](select.md) и [Install](install.md).

## Таблица команд

| Команда | Изменяемость | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp provider check` | `read` | `none` | установленный провайдер каждого харнеса и наличие более нового релиза |
| `ai-stp provider conformance` | `read` | `none` | проверка одного провайдера по явно выбранному протоколу |
| `ai-stp provider fetch` | `apply` | `none` | загрузка аттестованного провайдера OpenNetwork и привязка закрытого манифеста релиза |
| `ai-stp provider trust` | `read` | `none` | отчёт о закреплённой политике доверия и проверка одного релиза по ней |
| `ai-stp provider network` | `read` | `none` | наблюдаемая сетевая изоляция protocol-v2 на этой машине |
| `ai-stp provider update plan` | `read` | `none` | описание замены провайдера одного харнеса на новейшую выпущенную версию |
| `ai-stp provider update apply` | `apply` | `plan_digest` | выполнение ровно той замены, которую описал план |
| `ai-stp provider reinstall plan` | `read` | `none` | описание переустановки одной точной версии провайдера по тому же пути |
| `ai-stp provider reinstall apply` | `apply` | `plan_digest` | выполнение ровно той переустановки, которую описал план |
| `ai-stp provider forget` | `apply` | `none` | сброс записанного выбора провайдера, чтобы конфигурация и обнаружение решали снова |

`--json` — глобальный флаг. Передавайте его всегда.

`update plan` и `reinstall plan` — это `read`, а не `plan`. Они описывают замену. Они не записывают операцию установки. Apply подтверждается через `--expected-plan-digest` этого описания. В этой группе нет `--confirm`.

## Проверка

```bash
ai-stp provider check --json
ai-stp provider check --harness codex --json
ai-stp provider check --harness codex --offline --json
```

`--harness` можно указывать повторно. Опустите его для каждого поддерживаемого харнеса. `--offline` читает то, что установлено, не обращаясь к источнику релизов. Неудавшийся запрос не сообщается как «нет обновлений».

Поля успеха: `installations`, `source_consulted`. Каждая установка содержит `harness_id`, `provider_id`, `provider_version`, `path`, `status`, `source`, `repository`, `latest_tag`, `latest_commit`, `candidates`, `reason`, `checked_at`.

## Соответствие

```bash
ai-stp provider conformance \
  --harness codex \
  --executable <exe> \
  --json
ai-stp provider conformance \
  --harness codex \
  --executable <exe> \
  --target <dir> \
  --protocol-version 3 \
  --unverified-provider \
  --json
```

`--harness` и `--executable` обязательны. `--protocol-version` по умолчанию — замороженный v1. `--unverified-provider` проверяет исполняемый файл, не покрытый подписанным или аттестованным релизом, например, собранный вами самостоятельно. Изоляция не ослабляется: проверка по-прежнему выполняется под лаунчером, доказанным системой.

Поля успеха: `conforms`, `harness_id`, `protocol_version`, `reported_version`, `cases`. Каждый кейс содержит `name`, `subject`, `passed`, `exercised`, `detail`.

## Загрузка

```bash
ai-stp provider fetch --harness codex --json
ai-stp provider fetch --harness codex --tag <tag> --directory <dir> --json
ai-stp provider fetch \
  --harness codex \
  --artifact <existing-file> \
  --attestation-bundle <bundle> \
  --json
```

`--harness` обязателен. `--tag` — точный тег релиза; опустите его для привязки текущего релиза GitHub после разрешения его тега. `--directory` принимает артефакт и привязанный манифест. `--artifact` привязывает существующий файл вместо загрузки. `--attestation-bundle` — необязательный локальный пакет аттестации GitHub для оффлайн-проверки.

Поля успеха: `harness_id`, `provider_id`, `provider_version`, `tag`, `commit`, `repository`, `artifact`, `artifact_digest`, `artifact_url`, `manifest`, `protocol_version`, `sequence`, `trust_level`.

## Доверие и сеть

```bash
ai-stp provider trust --json
ai-stp provider trust --manifest <release-manifest> --json
ai-stp provider network --json
```

Без `--manifest` trust сообщает закреплённую политику. С ним тот же ответ также говорит, принят ли данный релиз.

Поля trust: `policy_id`, `policy_schema_version`, `signature_subject`, `allowed_keys`, `allowed_publishers`, `allowed_repositories`, `revoked_keys`, `pinned_releases`, `build_attestations`, `minimum_sequence`, `known_sequence`, `accepted`, `refusals`.

Поля network: `os_name`, `launcher_id`, `network_enforcement`, `protocol_version`, `local_actions_available`, `v3_local_phase`, `v3_local_phase_reasons`, `evidence`.

## Обновление и переустановка

Обе команды замены принимают `--harness` (обязателен), `--executable` (обязателен, когда установлено более одного провайдера) и `--adopt` (заменяет провайдер, который ai-stp не устанавливал; ничто другое не перезаписывает чужой). Apply добавляет `--expected-plan-digest`. Reinstall также принимает `--version`: опустите его для переустановки той версии, которая уже есть. Переход на новейший релиз — это `provider update`, а не reinstall.

```bash
ai-stp provider update plan --harness codex --json
ai-stp provider update apply \
  --harness codex \
  --expected-plan-digest sha256:... \
  --json

ai-stp provider reinstall plan --harness codex --version <tag> --json
ai-stp provider reinstall apply \
  --harness codex \
  --version <tag> \
  --expected-plan-digest sha256:... \
  --json
```

Когда установленный бинарный файл был размещён не этим CLI:

```bash
ai-stp provider update plan --harness codex --executable <exe> --adopt --json
ai-stp provider update apply \
  --harness codex \
  --executable <exe> \
  --adopt \
  --expected-plan-digest sha256:... \
  --json
```

Поля plan: `operation`, `harness_id`, `path`, `plan_digest`, `provider_id`, `provider_version`, `current_version`, `current_digest`, `tag`, `commit`, `repository`, `artifact_url`, `artifact_digest`, `artifact_bytes`, `backup`, `foreign`, `trust_level`, `idempotency_key`.

Поля apply: `operation`, `outcome`, `harness_id`, `path`, `plan_digest`, `provider_version`, `previous_version`, `tag`, `artifact_digest`, `backup`.

## Сброс выбора

```bash
ai-stp provider forget --json
ai-stp provider forget --harness codex --json
```

`--harness` можно указывать повторно. Опустите его для каждого поддерживаемого харнеса. Forget сбрасывает записанный выбор, чтобы конфигурация и обнаружение решали снова. Он не удаляет бинарный файл. Ответ — то же представление installations, что и у `check`.

## Счастливый путь

```text
provider check
→ provider trust
→ provider fetch --harness <id>
→ provider conformance --harness <id> --executable <exe>
→ install plan --provider <exe> --provider-manifest <path> …
```

Замена текущей установки:

```text
provider update plan --harness <id>
→ provider update apply --harness <id> --expected-plan-digest sha256:...
→ provider check --harness <id>
```

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `check` / `forget` | `installations`, `source_consulted` |
| `conformance` | `conforms`, `cases` |
| `fetch` | `artifact`, `manifest`, `artifact_digest`, `trust_level` |
| `trust` | `accepted`, `refusals`, `policy_id` |
| `network` | `network_enforcement`, `launcher_id`, `v3_local_phase` |
| `update` / `reinstall` plan | `plan_digest`, `path`, `tag`, `backup`, `foreign` |
| `update` / `reinstall` apply | `outcome`, `previous_version`, `provider_version` |

## Отказы

| Что вы видите | Что это означает | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | отсутствует `--harness` или `--expected-plan-digest` | прочитайте дескриптор |
| `AI_STP_PLAN_STALE` | байты на диске больше не совпадают с планом | спланируйте снова |
| `AI_STP_USER_DECISION_REQUIRED` | замена чужого бинарного файла требует `--adopt` | передайте `--adopt` после проверки пути |
| `AI_STP_PRECONDITION_FAILED` | политика доверия отказала релизу | прочитайте `provider trust --manifest`; не используйте `--unverified-provider`, чтобы скрыть это |
| `AI_STP_DEPENDENCY_UNAVAILABLE` | источник релизов недоступен | `--offline` на check, или повторите, если `retryable: true` |
| `conforms: false` | исполняемый файл не прошёл кейс протокола | прочитайте `cases`; не устанавливайте через него |
| `accepted` false | закреплённая политика отклонила манифест | остановитесь; не обходите политику через fetch |
| придумывание `--confirm` | apply подтверждается через `--expected-plan-digest` | передайте дайджест, а не булево значение |

`--unverified-provider` записывает, что закреплённая политика ничего не проверяла. Это не делает бинарный файл доверенным. Планы установки, использующие его, записывают `provider_release_trusted` false.

## Связанные ссылки

- [Установка](install.md)
- [Цель](target.md)
- [Программа харнеса](harness.md)
- [Инструментарий](toolchain.md)
- [Доверие и безопасность](../trust-and-safety/index.md)
- [Харнесы](../harnesses.md)
- [Карта команд](commands.md)

## Справка для машины — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды провайдера для удобства поиска. Установленный CLI является источником флагов, схем и `next_actions`. Если эта страница и CLI расходятся, следуйте CLI.
