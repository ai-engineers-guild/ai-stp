---
description: "Проверенный порядок разделения и интеграции PR #214 через актуальную линию dev."
last_verified: "2026-08-08"
---

# Интеграционный handoff для PR #214

Статус: заменён. PR `#214` закрыт без слияния, и его работа пришла в `dev` отдельной линией. Порядок ниже сохранён как исторический разбор и действующей инструкцией не является.

## Область и статус снимка

Этот документ — датированный снимок, а не живой статус GitHub. Перед выполнением
команд владелец платформенной ветки повторно получает refs и проверяет exact SHA.

Проверенный снимок:

- `dev@f10d8d2f9721251ee6bc82ee93952f866e17d6fc`;
- `main@cf911bb9172d55307bf760dc1ca269bac3f021d0`;
- `letya999@93f7d8239e3d773231bae76d27d4cf13f98da202`;
- локальный проверенный CLI/CI base
  `7f56432393fe1248cfc027a22ee9ad79de5a5641`;
- PR #214 открыт против `main`, хотя каноническая интеграционная линия — `dev`;
- `dev...letya999`: 62 коммита только слева и 10 только справа;
- merge-base: `26939fccbcf67f83b43a90e041fb71173fef01d1`.

Владелец CLI не переписывает `letya999`, не исправляет платформенные файлы и не
сливает PR #214. Владелец платформы переносит свою работу в новые ветки от
актуального `origin/dev`.

## Что доказано

Latest exact-head run `31227891551` остановил оба job на `docs-static` до
Python/platform тестов. Причина — 22 документальные ошибки:

- English-only строки в файлах BRAND.md и DESIGN.md каталога docs/product;
- несинхронизированный `docs/product/index.md`;
- отсутствующие index.md в каталогах docs/references и
  docs/references/prototypes.

Поэтому красный run не доказывает дефект sync-кода, но и не даёт доказательства
его работоспособности.

Read-only моделирование сначала поверх опубликованного `dev`, а затем поверх
локального CLI/CI base показало:

- прямой merge имеет текстовый конфликт в `docs/contracts/index.md`;
- два brand-коммита применяются чисто, но воспроизводят 22 docs-ошибки;
- отдельный sync-коммит поверх CLI/CI base имеет конфликты только в трёх
  generated index: `docs/adr/index.md`, `docs/contracts/index.md` и
  `specs/active/index.md`;
- `just docs-gen` разрешает эти конфликты, а `just back-gen` не создаёт
  дополнительного generated drift;
- sync-split проходит 41 contract/unit тест, 15 PostgreSQL API-тестов, четыре
  migration-теста, полный `docs-check`, `back-static` и `back-check`;
- полный Python gate на exact tree `7f56432 + d7022c1`: 1892 passed, 13 skipped,
  coverage 95.85%, без SQLite ResourceWarning; wheel install и `uv tool`
  install/uninstall regressions прошли.

Итоговый sync gate всё равно повторяется после публикации обоих коммитов: локальная
модель не является CI или staging evidence будущего exact head.

## Обязательное разделение

PR #214 заменяется двумя независимо проверяемыми PR:

1. sync server, migration, contracts, generated schemas и tests;
2. brand, design, UI, fonts, prototypes и их docs.

Server artifact route #212 в PR #214 отсутствует. Он остаётся отдельной
платформенной задачей после интеграции sync-split и до live CLI fetch/sync E2E.

## Перенос sync владельцем платформы

После попадания текущего CLI/CI package в `dev` владелец платформы выполняет:

```bash
git fetch origin
git switch --create letya999/sync-on-dev origin/dev
git cherry-pick d7022c1dc292f6b069ec94bb355de25917aa481c
```

Ожидаемые конфликты — три generated index, перечисленные выше. Их нельзя разрешать
выбором целиком `ours` или `theirs`: indexes восстанавливаются генератором.

```bash
just docs-gen
git add docs/adr/index.md docs/contracts/index.md specs/active/index.md
just back-gen
git add schemas/v1
git add skills/projections
git add apps/cli/src/ai_stp_cli/skills
git cherry-pick --continue
```

Перед публикацией ветки:

```bash
git diff origin/dev...HEAD --check
just docs-check
just back-static
```

С настроенной одноразовой PostgreSQL базой обязательны:

```bash
uv run pytest --no-cov \
  tests/contract/test_openapi.py \
  tests/unit/platform/test_sync_cursor.py \
  tests/unit/platform/test_sync_head_machine.py \
  tests/unit/platform/test_sync_validation.py

uv run pytest --no-cov \
  tests/api/platform/test_sync_ledger.py \
  tests/api/platform/test_devices_lifecycle.py \
  tests/integration/platform/test_schema_migrations.py \
  tests/unit/platform/test_migrations.py

just check
```

Второй блок требует `AI_STP_TEST_DB_URL`; пропуск PostgreSQL-тестов не считается
успехом. После последней правки `just check` запускается повторно на exact head.
Новый PR направляется в `dev`, не в `main`.

## Перенос brand/UI владельцем платформы

Отдельная ветка создаётся от актуального `origin/dev`; sync-код в неё не входит:

```bash
git fetch origin
git switch --create letya999/brand-on-dev origin/dev
git cherry-pick c2af878b488742a6b32ab520c99950fc65f93fb8
git cherry-pick c8450ca5474acb7d0c3fb0a1b1d9ba2338964d3f
```

До запуска широких тестов владелец переводит материал docs на русский и
восстанавливает generated indexes:

```bash
just docs-gen
just docs-check
just web-check
just check
```

Бинарные fonts проверяются на лицензию и происхождение отдельным review evidence.
Brand/UI PR также направляется в `dev` и не зависит от закрытия sync PR, если не
меняет общий контракт.

## Приёмка интеграции

Интеграция завершена только когда:

- оба PR имеют зелёные exact-head checks;
- итоговый tree сохраняет текущий CLI/provider/install контур;
- generated schemas и OpenAPI воспроизводятся без diff;
- история миграций имеет один head и проходит upgrade, повторный upgrade,
  downgrade и upgrade;
- sync push/pull, conflict, tombstone и revoked-device сценарии проходят с
  реальной PostgreSQL базой;
- новый интегрированный `dev` проходит полный gate без SQLite ResourceWarning;
- staging evidence записано на deployed exact SHA;
- #212 реализован и CLI получает те же artifact bytes и digest;
- только после этого #180 проверяется против staging, а не закрывается по mock.
