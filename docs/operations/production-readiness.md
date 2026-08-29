---
description: "Операторская процедура evidence-gated готовности production и опционального OpenObserve."
last_verified: "2026-08-28"
---

# Готовность production

Нормативные требования принадлежат `SPEC-032` и `ADR-0071`. Эта процедура не
разрешает production action: owner approval остаётся отдельным действием на
актуальном наборе evidence.

## Optional OpenObserve profile

OpenObserve — диагностический single-node profile. Он не является dependency
`/v1/health/ready`, audit store или backup source. Запускать его только вместе с
base stack и только с секретами в gitignored runtime environment:

```bash
docker compose -f docker-compose.prod.yml \
  -f deploy/docker-compose.observability.yml \
  --env-file .env.prod up -d openobserve
```

UI привязан к loopback host. Для доступа использовать SSH tunnel или уже
утверждённую административную границу; не публиковать UI или OTLP наружу. API
использует отдельную учётную запись ingestion через runtime header. Initial root
account не передаётся приложению. Остановка profile не удаляет его named volume;
удаление данных является отдельной destructive operation с owner confirmation.

`AI_STP_OPENOBSERVE_IMAGE` обязателен и содержит owner-approved immutable image
digest. Compose намеренно откажется запускать profile без него: floating tag не
является release identity.

При недоступном exporter приложение продолжает работать, но выпускное evidence
должно зафиксировать failed telemetry/alert check и не может быть `complete`.

## Evidence checklist

Перед owner approval записать exact commit, schema/config/policy revisions,
timestamp/expiry, safe outcomes и остаточные риски. Нельзя включать значения env,
учётные данные, tokens, raw logs, персональные данные или object bytes.

| Проверка | Команда / наблюдение | Ожидаемый результат |
| --- | --- | --- |
| Base topology | `docker compose -f docker-compose.prod.yml config` | В выводе нет OpenObserve и public OTLP port. |
| Profile isolation | compose config с override | Только loopback UI; OTLP не опубликован. |
| Health | `curl -fsS "$ORIGIN/v1/health/ready"` | `200` без зависимости от exporter. |
| Telemetry failure | развёрнутая среда с недоступным endpoint | API остаётся доступным; evidence records failure. |
| Recovery | `deploy/backup.sh` → isolated `restore.sh --yes` | PostgreSQL/RustFS integrity и readiness. |
| Rollback | `deploy/rollback.sh --yes` на развёрнутой среде | Previous exact artifact under lock; no downgrade. |
| Abuse | deterministic API test | `429` и `Retry-After`; signal не меняет lifecycle. |

## Принятая policy single-node MVP

До отдельного пересмотра действуют следующие значения: доступность API —
`99.5%` за 30 дней; p95 задержки public API — не более `750 ms`; бюджет ошибок —
`0.5%`. Telemetry OpenObserve хранится `14 days`, а оператор оставляет не менее
`20%` свободного места на файловой системе тома. Evidence действует `24 hours`.

Rate limit — `100` запросов за `60 seconds` на весь процесс и `1000` запросов
за `3600 seconds` с одного транспортного адреса, с не более `2048` ключами в
таблице адресов (`ADR-0128`). Это намеренно базовая single-node защита: browser
state и forwarded headers не становятся источником полномочия. Для входа, жалоб и
чувствительных изменений до production approval требуется отдельный класс policy
и проверка на server boundary.

Alert routes остаются local/test receiver до явного выбора owner внешнего
канала. Отсутствие реального receiver или recovery rehearsal делает evidence
`incomplete`, а не неявно успешным.
