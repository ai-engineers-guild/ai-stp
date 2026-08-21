---
description: "Runbook: platform safety-scan для publication validate."
last_verified: "2026-08-21"
---

# Runbook: platform safety-scan

Серверный набор проверок безопасности на шаге публикации `validate`
(issues #268 / #270 / #281). Источник evidence: `platform_safety_scan`.
Версия политики: `safety-1`.

## Образ worker и внешние CLI

В dev и prod compose публикационный worker собирается из
`Dockerfile.worker-safety` (target `worker-safety`) с переменными:

- `AI_STP_SAFETY_EXTERNAL_CLI=1`
- volume `osv_offline` → `/var/lib/ai_stp/osv`
- `AI_STP_OSV_OFFLINE_DIR` и `OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY` (один путь;
  osv-scanner читает offline packs только из второго)
- `AI_STP_OSV_MAX_AGE_HOURS`

Сервисы API и migrate/seed остаются на target `worker`/`api` без бинарников
сканеров.

## Лимит времени одной проверки

Сколько отведено конкретной проверке, решает её `timeout_seconds` в
`safety/policy.py`. `safety/adapters/_cli.py` держит потолок
`MAX_TIMEOUT_SECONDS` — защиту от неверного аргумента, а не вторую политику;
тест запрещает объявить больше потолка. Весь набор дополнительно ограничен
собственным бюджетом в `safety/orchestrator.py`.

Раньше потолок был 25 секунд молча, при объявленных 30 и 60. Разницу никто не
сообщал, поэтому повышение лимита ничего не меняло, а убитый по времени сканер
записывался как находка: объект отклонялся за опасное содержимое, которого
никто не видел. Проверка, не успевшая закончиться, теперь `degraded` и называет
причину.

Ручная сборка:

```text
docker build -f Dockerfile.worker-safety --target worker-safety -t ai-stp-worker-safety .
```

Пины версий лежат в `scripts/safety/versions.env`; установка — в
`scripts/safety/install_scanners.sh`. Образ включает:

| Инструмент | Роль |
|------|------|
| gitleaks | секреты (вторично к in-proc heuristic) |
| opengrep | SAST с vendored rules в `safety/policy_pack/opengrep/` |
| shellcheck | shell-сценарии |
| bandit | Python SAST |
| pip-audit | Python SCA |
| gosec | Go SAST |
| govulncheck | Go SCA (обязателен в образе) |
| cargo audit | Rust SCA (если на хосте есть cargo) |
| eslint | JS/TS SAST (по наличию) |
| npm audit | JS SCA |
| cargo deny | Rust policy (strict) |
| osv-scanner | SCA (`--offline`, когда задан `AI_STP_OSV_OFFLINE_DIR`) |
| pdf in-proc | проверка `document_pdf` для /JavaScript /Launch и т.п. |
| clamscan | malware (профиль strict) |
| yara | malware IOC pack (strict; in-proc marker всегда) |
| skillspector | skill static (`--no-llm`, NVIDIA SkillSpector, обязателен) |
| skill-scanner | skill static, второй движок (Cisco `cisco-ai-skill-scanner`, обязателен) |
| bwrap | Linux network namespace для дочерних external CLI |

Без флага `AI_STP_SAFETY_EXTERNAL_CLI` по-прежнему работают in-proc адаптеры
(denylist, secrets heuristic, MCP/hook static, PI/stego, owned skill patterns,
malware test marker).

## Изоляция (sandbox)

- Переменная: `AI_STP_SAFETY_SANDBOX=auto|off` (по умолчанию `auto`).
- На Linux с рабочим `bwrap` (unprivileged user namespaces) argv CLI
  оборачивается `--unshare-net` и RW bind каталога workdir скана.
- Если `bwrap` отсутствует или не создаёт namespaces (часто на Docker Desktop
  по умолчанию), режим падает в env-only deny: `AI_STP_SAFETY_NETWORK=deny`,
  proxy-переменные очищены. Детали probe — в `doctor_tools()` / `sandbox_status()`.
- Сетевая политика контейнера остаётся основным контролем egress; `bwrap` —
  дополнительный слой защиты.
- Жёсткое включение namespaces на Docker Desktop: поддержка kernel userns и
  non-default security profile; production Linux workers обычно работают с `auto`.

## Обновление offline баз

Offline-база OSV (compose volume `osv_offline`):

```text
export AI_STP_OSV_OFFLINE_DIR=/var/lib/ai_stp/osv
export OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=/var/lib/ai_stp/osv
/opt/ai_stp/scripts/safety/refresh_osv_db.sh
```

- Скрипт выставляет `OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$DEST`, чтобы packs
  легли на volume (`{dir}/osv-scanner/{ecosystem}/all.zip`).
- Не пишет `.ai_stp_osv_refreshed_at`, если zip packs не появились (без ложной
  свежести).
- Ежедневный cron на хосте или job, который пишет в shared volume.
- Причины doctor: `not_configured`, `directory_missing`, `no_files`, `no_stamp`,
  `stale`, `ok`.
- SCA-адаптер: нет packs → `not_run` / `offline_db_missing` (не `tool_missing`).
- Возраст: `AI_STP_OSV_MAX_AGE_HOURS` (по умолчанию 36). Опциональный hard gate:
  `AI_STP_OSV_REQUIRE_FRESH=1` (API readiness остаётся optional; для worker-only
  probes).
- Подписи ClamAV: `freshclam` daily, когда clam включён.

## Аутентификация хранилища

- `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` должны совпадать с
  `AI_STP_STORAGE_ACCESS_KEY_ID` / `AI_STP_STORAGE_SECRET_ACCESS_KEY` при первом
  старте volume RustFS.
- Compose healthcheck: `curl -sf http://127.0.0.1:9000/minio/health/live`.
- API и worker: `depends_on: rustfs (service_healthy)`.

## Честность checks summary

`build_checks_summary` — статусы:

| status | смысл |
|--------|---------|
| `pending` | обязательная проверка ещё `not_run` / `degraded` / `running` |
| `incomplete` | optional engines в плане, но missing (`not_run`); percent учитывает все запланированные проверки |
| `available` | coverage complete; percent 0–100 по passed/failed/warning |
| `empty` | нет bindings |

Поля: `coverage_complete`, `not_run`, `checks_passed_percent` (доля `passed`
среди всех запланированных проверок кроме `skipped` и `not_applicable`).

## Пины setup

Проверка setup читает `checks_summary` каждого pin из `components[]` в
`catalog_metadata` и запускает `setup_pin_aggregate` (без повторного скана
объединённого дерева). Отсутствующий или проваленный обязательный pin валит
gate setup.

## Диагностика и метрики

```text
python -c "from ai_stp_platform.safety import doctor_tools, safety_diagnostics; import json; print(json.dumps(safety_diagnostics(), indent=2, default=str))"
```

Счётчики в процессе (structlog + snapshot, без зависимости Prometheus):

- `safety_scan_total`, `safety_scan_cache_hit_total`
- `safety_scan_duration_ms_*`
- `safety_check_result_total` по result
- `safety_finding_total` по `family:severity`
- `safety_cli_timeout_total`, `safety_cli_missing_total`
- `safety_sandbox_mode_total`

Готовность API (`/v1/health/ready`) зависит только от database/migrations/storage,
чтобы отсутствие сканеров не роняло публичный API. Операции worker используют
`doctor_tools`.

## Scenario matrix (in-proc)

Unit-сценарии в `tests/unit/platform/test_safety_scenario_matrix.py`:

| Fixture | Ожидаемый сигнал gate |
|---------|----------------------|
| clean skill | нет mandatory `failed` |
| secret skill (`ghp_…`) | secrets family fails |
| toxic skill (pipe shell / PI) | skill gate fails |
| clean MCP | путь mcp_config не даёт mandatory-fail |

Внешние CLI для этой matrix не обязательны.

## Типичные сбои

| Симптом | Действие |
|---------|--------|
| Все publish блокируются с `not_run` | Нет байтов artifact на validate; проверить fetch из object-store |
| Зависание external CLI | `AI_STP_SAFETY_EXTERNAL_CLI` только в worker-safety; лимит объявляет проверка, потолок раннера — `MAX_TIMEOUT_SECONDS` |
| Проверка `degraded`, а в `reason` — `did not finish within Ns` | Сканер не успел, а не нашёл. Смотреть нагрузку worker и объявленный `timeout_seconds` этой проверки, не содержимое объекта |
| Host AV блокирует temp files | Не класть полный EICAR; маркер `AI_STP_MALWARE_TEST_MARKER_V1` |
| OSV stale | Запустить `refresh_osv_db.sh`; сверить stamp с `AI_STP_OSV_MAX_AGE_HOURS` |
| Sandbox всегда env_only | Установить `bubblewrap` в worker image (уже в Dockerfile.worker-safety) |
