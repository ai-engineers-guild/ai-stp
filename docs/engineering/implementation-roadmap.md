---
description: "Текущее состояние ai_stp и единый порядок оставшихся работ."
last_verified: "2026-08-31"
---

# Текущее состояние и план

Это единственный владелец текущего плана. GitHub issues остаются backlog, ADR
хранят решения, specs — требования, а review/сессионные планы не продолжаются
буквально после изменения кода.

## Вижен, по которому принимаются решения

- семь setup systems владеют нативной записью своих харнессов и реальным
  software install/update/remove; `ai-stp` вызывает тот же lifecycle машинно;
- существующая конфигурация становится управляемой только через явный adopt с
  exact plan, без молчаливого присвоения;
- current component vocabulary содержит восемь видов и может быть расширен
  новой спецификацией, когда появится доказанная нативная форма;
- release target — Linux, Windows и macOS на обеих архитектурах с real-product
  evidence; bundle переносим между ОС;
- агент сам выбирает инженерный путь внутри задачи. Digest, rollback,
  provenance и совместимость остаются механической целостностью, но не создают
  дополнительный круг вопросов.

## Что уже реализовано

| Область | Наблюдаемое состояние |
|---|---|
| Local-first CLI | SQLite registry, passports/revisions, discovery/adopt, selection, bundle, install/status/diff/update/rollback/recovery, machine help и canonical Skill |
| Platform | `/v1`, PostgreSQL, object storage, queue, auth/devices, sync, publication, grants/reports, public catalog, article и SEO projections |
| Web | landing, catalog/detail, account/device/owner surfaces, content hub, machine projections и три-ОС test matrix |
| Providers | семь protocol-v3 systems, native configuration layouts, backup/recovery, software lifecycle capabilities и пять complete launch capabilities |
| Release | все пять Python-пакетов опубликованы как `0.0.10`; public `check` и CodeQL зелёные на проверенном main; host тянет `deploy/prod` |
| Catalog | опубликованы семь harness families и четыре postures; старые review-задачи `#408`, `#456`, `#460`, `#461` закрыты реализацией |

## Проверенный снимок 2026-08-31

- canonical development checkout: `ai-engineers-guild/ai-stp`; private
  underscore tree импортирует его штатным `public-sync` и отдельно хранит
  private deployment history;
- активный выпуск провайдеров: `0.0.48`, семь выпусков по шесть нативных бинарников и
  `SHA256SUMS`;
- core provider surface/binaries: 7 × 6 OS/arch строк;
- software lifecycle и exact-current provider operations: семь systems × 6/6;
- live deploy восстановлен после `AI_STP_CONTENT_IMPORT_FORBIDDEN`: внутренний
  token задан owner-only, content-import завершён, API/web готовы. Deployer
  теперь проверяет token до build/migrate/recreate, поэтому тот же пропуск не
  останавливает работающий web.

Точные SHA и run IDs намеренно остаются в Git/GitHub/evidence artifacts. Этот
раздел датирован и заменяется целиком при следующем аудите, а не накапливает
срезы.

## Оставшаяся работа

### P1. Exact current provider wave

1. Provider-kit `0.2.7` vendored в released setup-systems `0.0.48`; 35 status
   samples (семь × пять состояний) проходят Draft 2020-12.
2. Включить отказ
   consumer для malformed status отдельным compatible change.
3. После consumer enforcement повторить cross-repository conformance; schema
   publication и enforcement являются двумя последовательными окнами
   совместимости, не одним коммитом.

### P2. Release-candidate и live evidence

1. Собрать пять exact Python packages, SBOM/checksums/provenance и install smoke
   вне checkout на шести строках.
2. Прогнать repository-independent `evidence-*` против exact deployed SHA:
   anonymous live, account sync, publication, providers и recovery.
3. Проверить catalog install для семи harnesses/postures и записать content gaps
   без фиктивных объектов.

### P4. Agent-first cleanup как постоянная практика

1. Любой handler, читающий скрытый `confirm`, должен ломать registry parity test.
2. Local reversible operation использует exact expected value как
   confirmation; новый boolean добавляется только для класса риска `ADR-0118`.
3. Старый plan/review не копируется в активную документацию. Новая сессия читает
   этот roadmap, specs и machine help, затем проверяет их против текущих bytes.

## Что намеренно не входит в текущий проход

Открытые задачи дорожной карты — корпоративный hub, SSO/GitLab, защита от
ботов, malware integrations, стандарты discovery, иллюстрации и возможные новые
виды компонентов — остаются backlog. Они не являются дефектами текущего релиза и
не закрываются ради пустого счётчика. Первым действием при их продвижении будет
проверка против актуального продукта и формулировка новой active spec.

## Готовность

Работа считается завершённой, когда текущие public/private bytes синхронны,
заявленные six-leg evidence исполнены на точных releases, live slices относятся
к deployed SHA, документация сгенерирована из владельцев, а итоговый diff и Git
state чисты. `not_verified` — честный оставшийся результат, а не повод добавить
ручной approval или скрыть строку матрицы.
