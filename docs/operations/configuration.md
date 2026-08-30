---
description: "Конфигурация локального CLI и серверного контура."
last_verified: "2026-08-29"
---

# Конфигурация

## Правила

- обязательное значение проверяется при старте;
- секрет не имеет небезопасного значения по умолчанию;
- неизвестный ключ вызывает ошибку для внутренних конфигов;
- секреты не печатаются;
- CLI и server имеют отдельные settings models;
- локальные пути абсолютны и принадлежат пользователю;
- provider/runtime paths не разрешаются через непроверенный ambient `PATH`.

## Группы

Пользовательские настройки CLI живут в одном глобальном конфиге. Перечень полей, значения по умолчанию и приоритет источников принадлежат `docs/contracts/cli-config.md` и здесь не повторяются.

| Группа | Содержание |
|---|---|
| CLI | data/state/cache directories, каталог и его адрес, синхронизация, поиск, discovery roots, timeout, output mode |
| API | database URL, object storage, OAuth, session keys, CORS, catalog usage counters (`docs/contracts/catalog-usage-metrics.md`) |
| Worker | database, concurrency, timeout, retry ceilings |
| Worker safety | `AI_STP_SAFETY_EXTERNAL_CLI`, `AI_STP_SAFETY_SANDBOX`, `AI_STP_OSV_OFFLINE_DIR`, `AI_STP_OSV_MAX_AGE_HOURS`, `AI_STP_OSV_REQUIRE_FRESH` (runbook `safety-scan.md`) |
| Worker SEO enrichment | `AI_STP_SEO_ENRICHMENT_ENABLED`, `AI_STP_SEO_ENRICHMENT_URL`, `AI_STP_SEO_ENRICHMENT_CREDENTIAL`, `AI_STP_SEO_ENRICHMENT_MODEL_ALIAS`, `AI_STP_SEO_ENRICHMENT_TIMEOUT_SECONDS` по `SPEC-053`. CLIPROXY `AI_STP_CLIPROXY_URL` (по умолчанию `http://cliproxy:8317/v1`), `AI_STP_CLIPROXY_API_KEY`, `AI_STP_CLIPROXY_MODEL` принадлежат LiteLLM-контейнеру профиля `seo_enrichment` и не передаются worker. Сессия — JSON в `deploy/cliproxy/auths/`, runbook `seo-publication.md` |
| Content import | scoped bearer `AI_STP_CONTENT_IMPORT_TOKEN` для `POST /v1/content/repository/import`; пустое значение запрещает import, API при этом стартует. One-shot importer повторяет GET state / POST snapshot при `URLError` и HTTP 502/503/504: `AI_STP_CONTENT_IMPORT_ATTEMPTS` (по умолчанию 8) и `AI_STP_CONTENT_IMPORT_RETRY_SECONDS` (по умолчанию 1); 4xx не повторяется |
| RustFS/S3 | endpoint, bucket, credentials, region |
| Resend | API key, sender, callback URLs |
| GitHub/Google | OAuth client IDs/secrets and redirect URIs |

Конфигурация dev и prod задаётся отдельными env-файлами: в репозиторий попадают только образцы без секретов, а реальные `.env.dev` и `.env.prod` исключены из индекса по `SPEC-019`. Полный `.env.example` добавляется вместе с первым исполнимым server code. До этого документация не изображает несуществующие переменные.
