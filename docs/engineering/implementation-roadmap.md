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
| Release | все пять Python-пакетов опубликованы как `0.0.12`; public `check` и CodeQL зелёные на проверенном main; host тянет `deploy/prod` |
| Catalog | опубликованы семь harness families и четыре postures; старые review-задачи `#408`, `#456`, `#460`, `#461` закрыты реализацией |

## Проверенный снимок 2026-08-31

- canonical development checkout: `ai-engineers-guild/ai-stp`; private
  underscore tree импортирует его штатным `public-sync` и отдельно хранит
  private deployment history;
- опубликованные Python-пакеты: `0.0.12`, пять exact distributions с PyPI
  Trusted Publishing, attestations, SBOM/checksums и clean install smoke.
  `0.0.11` и раньше не могут установить программу харнесса: они отказывают на
  отсутствующем `plan_digest` в ответе software apply уже после того, как
  программа установлена;
- активный выпуск провайдеров: `0.0.48`, семь выпусков по шесть нативных бинарников и
  `SHA256SUMS`;
- core provider surface/binaries: 7 × 6 строк Linux/Windows/macOS ×
  `x86_64`/`arm64`;
- software lifecycle и exact-current provider operations: семь systems × 6/6;
- live deploy восстановлен после `AI_STP_CONTENT_IMPORT_FORBIDDEN`: внутренний
  token задан owner-only, content-import завершён, API/web готовы. Deployer
  теперь проверяет token до build/migrate/recreate, поэтому тот же пропуск не
  останавливает работающий web.

Точные SHA и run IDs намеренно остаются в Git/GitHub/evidence artifacts. Этот
раздел датирован и заменяется целиком при следующем аудите, а не накапливает
срезы.

## Оставшаяся работа

### P0. Provider release 0.0.49 закрывает эхо plan_digest

`apply-operation` у выпущенных `0.0.48` не возвращает `plan_digest` для
`software_*`, хотя конфигурационный apply его возвращает и
`docs/contracts/provider-protocol.md` требует «те же журнал, backup и
plan-digest». Consumer требовал эхо у всех операций, поэтому каждый
`harness install/update/remove` через `ai-stp` отказывал **после** того, как
программа уже установлена, оставляя операцию `applied_unverified` над рабочим
префиксом.

Ни один producer-тест этого не видел: провайдер делает ровно то, что утверждает
его собственный набор. Нашёл потребительский срез, которого раньше не было.

Порядок — tolerate-then-emit. Consumer-половина выпущена: `0.0.12` принимает
отсутствие эха для программных операций и по-прежнему отказывает на
несовпадающем. Provider-половина у владельца `NDDev-it-com/setup-systems`:
`0.0.49` добавляет эхо обеим формам ответа, после чего оно начинает
проверяться реально, а не толерироваться.

Доказано концом в конец тем, что лежит на PyPI: `ai-stp-cli==0.0.12` в чистом
venv ставит выпущенный cursor `0.0.48` через `harness install` —
`state=verified`. Тот же вызов на `0.0.11` отказывал.

После `0.0.49` нужен переимпорт каталога: 15 из 28 опубликованных сетапов
отстали от источника (все семь `nddev-builder` и все `full-auto`, кроме
antigravity), поэтому `install plan` показывает описание постуры, которая ещё
просит подтверждений.

### P1. Account-dependent live evidence

1. Завершить настоящий browser device flow для двух отдельных file credential
   stores и прогнать fast-forward/replay/conflict/merge sync scenarios.
2. Тем же аккаунтом проверить owner/publication/grant/report read surface и
   локальные attestation/preview/reachability scenarios.
3. Проверить catalog install для семи harnesses/postures и записать content gaps
   без фиктивных объектов. Anonymous live, provider 0.0.48, citation и
   six-native release evidence уже выполнены.

### P2. Native evidence для того, что уже реализовано, но не измерено

1. `just evidence-software <tag>` ведёт семь выпущенных провайдеров через
   потребительский путь (`harness install/status/update/remove`). Против
   `0.0.48` на Linux `x86_64` выполнен: 7/7 `passed`, `clean`. На остальных
   пяти нативных строках — нет.
2. Windows job object и sweep оставленных grant реализованы и покрыты тестами,
   но не измерены на нативном раннере под настоящим kill родителя.
3. macOS `(deny file-write*)` не прогонялся против семи реальных провайдеров на
   обеих архитектурах.

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
