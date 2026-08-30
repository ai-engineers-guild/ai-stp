---
description: "Минимальные сигналы для диагностики CLI, sync, публикации и providers."
last_verified: "2026-08-29"
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
- Результат и задержка SEO build/enrichment, доля active base/enriched, причины rejection/stale, решение об индексации, generation/cache age sitemap и расход модели по operator alias без prompt, body и subject ID (`SPEC-053`).

### Safety-scan signals (`safety_*`)

Источник: in-process counters в worker/API процессе (`ai_stp_platform.safety.metrics`),
плюс structured log event `safety_scan` / `safety_cli`. Снимок:

```text
python -c "from ai_stp_platform.safety.metrics import snapshot; print(snapshot())"
```

| Metric | Решение |
|--------|---------|
| `safety_scan_total` | объём validate/scan |
| `safety_scan_duration_ms_avg/max/p50/p95/p99` | деградация suite / hard cap |
| `safety_scan_duration_ms_buckets` | bounded latency distribution; `+Inf` — выше hard-cap bucket |
| `safety_check_total` | число исполнений каждого `check_id` |
| `safety_check_result_total`, `safety_check_result_by_id_total` | failed/not_run/degraded balance globally and per check |
| `safety_check_duration_ms_avg/max`, `safety_check_duration_ms_buckets` | per-check cost and tail |
| `safety_finding_total` | family:severity pressure |
| `safety_cli_timeout_total` | зависания внешних CLI |
| `safety_sandbox_mode_total` | bwrap vs env_only coverage |
| `safety_queue_claim_total`, `safety_queue_empty_poll_total` | polling pressure |
| `safety_queue_claimed_total`, `safety_queue_wait_ms_*` | queue throughput and wait |
| `safety_queue_job_*` | handler duration/result |
| `safety_queue_requeued_total` | drain/stale-lease pressure |

Secrets и raw finding bodies в метрики не входят.

### Safety performance evidence

Нормативный offline smoke/load corpus запускается без сети и без внешних CLI:

```text
just safety-benchmark --iterations 3 --concurrency 1
```

Результат — JSON с `schema_version`, exact local `commit`, фиксированным
`case_order`, profile, artifact digests, mandatory failures и metrics snapshot.
Corpus/order/profile deterministic; `wall_ms` зависит от CPU, filesystem и
текущей нагрузки и используется для сравнения одинакового окружения, а не как
межмашинный критерий успеха. Для production-оповещений используются ожидание очереди, хвост scan,
tail, `degraded/not_run`, `+Inf` buckets и рост requeue; отсутствие exporter не
удаляет локальный structured event и не превращает отсутствие evidence в success.

## Провайдер и логи

Server mode использует провайдер OpenTelemetry с конфигурируемым экспортёром и структурный лог в дневной файл по `ADR-0039`; недоступный экспортёр не роняет приложение. `trace_id` связывается со спаном и попадает в конверт ответа рядом с `request_id`. Токены и персональные данные в лог не входят по `SPEC-013`.

## Принцип

Сигнал создаётся только если по нему принимается решение. Нельзя логировать `success` до durable commit или provider verification.
