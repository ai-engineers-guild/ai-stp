---
description: "Минимальные сигналы для диагностики CLI, sync, публикации и providers."
last_verified: "2026-08-12"
---

# Наблюдаемость

## Локальный CLI

Каждая изменяющая операция имеет:

- operation ID;
- plan digest;
- entity/device/provider IDs;
- started/finished timestamps;
- состояние;
- безопасный error code;
- append-only steps;
- recovery instruction.

Raw secrets, prompts и source content в журнал не входят.

## Server mode

Нужны измерения:

- API requests, errors and duration;
- auth/login/link failures;
- sync accepted/rejected/conflict;
- publish validation outcome;
- worker queue depth/retry/dead letter;
- object storage errors;
- provider release download failures;
- объём жалоб, время триажа и действия модерации;
- rate-limit and abuse signals;
- platform safety-scan counters (`safety_*`, see runbook `safety-scan.md`).

### Safety-scan signals (`safety_*`)

Источник: in-process counters в worker/API процессе (`ai_stp_platform.safety.metrics`),
плюс structured log event `safety_scan` / `safety_cli`. Снимок:

```text
python -c "from ai_stp_platform.safety.metrics import snapshot; print(snapshot())"
```

| Metric | Решение |
|--------|---------|
| `safety_scan_total` | объём validate/scan |
| `safety_scan_duration_ms_avg/max` | деградация suite / hard cap |
| `safety_check_result_total` | failed/not_run/degraded balance |
| `safety_finding_total` | family:severity pressure |
| `safety_cli_timeout_total` | зависания внешних CLI |
| `safety_sandbox_mode_total` | bwrap vs env_only coverage |

Secrets и raw finding bodies в метрики не входят.

## Провайдер и логи

Server mode использует провайдер OpenTelemetry с конфигурируемым экспортёром и структурный лог в дневной файл по `ADR-0039`; недоступный экспортёр не роняет приложение. `trace_id` связывается со спаном и попадает в конверт ответа рядом с `request_id`. Токены и персональные данные в лог не входят по `SPEC-013`.

## Принцип

Сигнал создаётся только если по нему принимается решение. Нельзя логировать `success` до durable commit или provider verification.
