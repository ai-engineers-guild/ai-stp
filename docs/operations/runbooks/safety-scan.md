---
description: "Runbook: platform safety-scan для publication validate."
last_verified: "2026-08-24"
---

# Runbook: platform safety-scan

Серверный набор проверок безопасности на шаге публикации `validate`
(issues #268 / #270 / #281). Источник evidence: `platform_safety_scan`.
Версия политики: `safety-2`.

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

## Что получает движок скиллов

`skill-scanner` загружает **пакет скилла** — каталог, в котором
лежит `SKILL.md`, — а не корень артефакта. Артефакт `ai-stp-component-tree/1`
распаковывается в `component.json` и `files/`, поэтому корень пакетом не
является: `skill-scanner` отвечает `Error loading skill: SKILL.md not found`,
выходит с кодом 1 и не печатает отчёт.

Гейт передавал именно корень и читал этот отказ как находку «сканер сообщил о
рисках». На корпусе это отклонило 96 компонентов из 103 за содержимое, которого
никто не читал, и заблокировало все сетапы, их закрепляющие. Теперь каждый
движок получает по каталогу на найденный `SKILL.md`; `skill_packages` в
`detail` говорит, сколько их было. Ноль означает, что загружать было нечего —
например, у компонента вида `agent` — и движки не запускались вовсе.

Отдельно: `skill-scanner` требует во frontmatter `name` и `description`.
`SKILL.md` без них не загружается, и это тоже `degraded` с причиной, а не
находка.

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
| skill-scanner | skill static + `--use-behavioral` data-flow (Cisco `cisco-ai-skill-scanner`, обязателен вместе с независимыми правилами платформы) |
| bwrap | Linux network namespace для дочерних external CLI |

Без флага `AI_STP_SAFETY_EXTERNAL_CLI` по-прежнему работают in-proc адаптеры
(denylist, secrets heuristic, MCP/hook static, PI/stego, owned skill patterns,
malware test marker), а также offline `network_intent` и bounded decoding
обфускации (не более двух слоёв, 32 кандидатов и 64 KiB на кандидат).

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
- Production compose по умолчанию загружает только поддержанные safety policy
  экосистемы `PyPI,npm,Go,crates.io`; расширение задаётся через
  `AI_STP_OSV_ECOSYSTEMS` вместе с поддержкой нового package manifest.
- Не пишет `.ai_stp_osv_refreshed_at`, если zip packs не появились (без ложной
  свежести).
- Ежедневный cron на хосте или job, который пишет в shared volume.
- Причины doctor: `not_configured`, `directory_missing`, `no_files`, `no_stamp`,
  `stale`, `ok`.
- SCA-адаптер: нет packs → `not_run` / `offline_db_missing` (не `tool_missing`).
- Возраст: `AI_STP_OSV_MAX_AGE_HOURS` (по умолчанию 36). Опциональный hard gate:
  `AI_STP_OSV_REQUIRE_FRESH=1` (API readiness остаётся optional; для worker-only
  probes).
- Подписи ClamAV обновляет отдельный `clamav-refresh` в shared read-only для
  worker volume; worker стартует только после появления непустой `.cvd`/`.cld`.

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
- `safety_scan_duration_ms_*` включая buckets и p50/p95/p99
- `safety_check_total`, `safety_check_result_total`, `safety_check_result_by_id_total`
- `safety_check_duration_ms_*` по `check_id`
- `safety_finding_total` по `family:severity`
- `safety_cli_timeout_total`, `safety_cli_missing_total`
- `safety_sandbox_mode_total`
- `safety_queue_claim_*`, `safety_queue_wait_ms_*`, `safety_queue_job_*`,
  `safety_queue_requeued_total`

Для проверяемого offline performance evidence:

```text
just safety-benchmark --iterations 3 --concurrency 1
```

Команда принудительно устанавливает `AI_STP_SAFETY_EXTERNAL_CLI=0` и
`AI_STP_SAFETY_SANDBOX=off`, не обращается к сети, использует фиксированные ZIP
bytes и печатает JSON. `wall_ms` сравнивается только между одинаковыми
окружениями; обязательными инвариантами остаются schema, case order, digest,
profile, disabled network/CLI и отсутствие mandatory failures.

Adversarial corpus и JSON-отчёт:

```text
just safety-corpus --output .work/safety-corpus-report.json
```

Команда последовательно материализует ZIP каждого component fixture, запускает
тот же `run_safety_suite`, которым пользуется publication validation, и отдельно
проверяет setup через `setup_pin_aggregate`. Успех требует полного совпадения
ожидаемых `check_id`/`rule_id` и отсутствия findings на clean controls. Сырые
байты fixture в отчёт не попадают.

Corpus v2 содержит 156 файловых сценариев: 134 вредоносных и 22 чистых. В него
входят классы MCPTox для предусловий в метаданных и подмены аргументов, изменение
MCP tool/schema, затенение tool, отравление resource/prompt/output, опасные цепочки,
атаки через сабагентов и память, закрепление, цепочка поставки, ограниченное
многослойное кодирование, Unicode Tag Block, омоглифы и структурное скрытие в
Markdown. Контроли фиксируют стабильные снимки MCP, ограниченную делегацию и
защитный текст, который описывает запрещённую атаку.

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
| Sandbox всегда `env_only`, worker `unhealthy` | См. раздел ниже. `bwrap` уже в образе; не ставить повторно. |

### Worker `unhealthy`: probe `bwrap` даёт `env_only`

`safety_readiness()` требует `detect_sandbox_mode() == "bwrap"`. На проде
2026-08-24 инструмент на месте, OSV свежий, `AI_STP_SAFETY_EXTERNAL_CLI=1`,
а probe отвечает `bwrap: Failed to make / slave: Permission denied` и режим
становится `env_only`. Healthcheck красный; каждый внешний CLI при
`AI_STP_SAFETY_REQUIRE_BWRAP=1` выходит с кодом 126.

На Ubuntu 24.04 это не отсутствие бинарника. Хост держит
`kernel.apparmor_restrict_unprivileged_userns=1`. `seccomp=unconfined` в
compose недостаточно: профиль `docker-default` всё ещё запрещает mount.
Снятие AppArmor с контейнера меняет ошибку на `loopback: Failed RTM_NEWADDR`.
Как uid `10001` даже `cap-add ALL` loopback не настраивает: без user namespace
нет `CAP_NET_ADMIN` внутри netns.

На этом хосте probe проходит только как root с `SYS_ADMIN` и `NET_ADMIN`
(плюс `apparmor=unconfined`) либо после снятия sysctl. Репозиторий ни то ни
другое не включает: sysctl — решение оператора, root+capabilities — расширение
границы изоляции worker. Пока одно из двух не сделано, публикационный validate
не исполняет внешние сканеры.
