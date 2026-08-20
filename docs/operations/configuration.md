---
description: "Конфигурация локального CLI и серверного контура."
last_verified: "2026-08-12"
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
| RustFS/S3 | endpoint, bucket, credentials, region |
| Resend | API key, sender, callback URLs |
| GitHub/Google | OAuth client IDs/secrets and redirect URIs |

Конфигурация dev и prod задаётся отдельными env-файлами: в репозиторий попадают только образцы без секретов, а реальные `.env.dev` и `.env.prod` исключены из индекса по `SPEC-019`. Полный `.env.example` добавляется вместе с первым исполнимым server code. До этого документация не изображает несуществующие переменные.
