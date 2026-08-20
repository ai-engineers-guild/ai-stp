---
description: "SPEC-047: Web/backend consumer surfaces for canonical CLI contracts and catalog delivery."
last_verified: "2026-08-15"
---

# SPEC-047: Web/backend consumer surfaces

## Цель

Довести до общего продукта потребительские срезы канонических CLI copy и
`deep links`. Periodic GitHub archive evidence и account blast radius на
server/Web заменены `SPEC-049` и `ADR-0096`. Ни одна из этих проекций не
меняет `immutable passport`, `lifecycle`, `eligibility` или `target`.

## Границы

Входит delivery-слой для issues #241, #307, #309, #344 и #347:

- порождённая и проверенная web-проекция шаблонов CLI copy;
- реально исполняемый `catalog coverage gate`;
- web-потребитель `deep_link_v1`;
- server-owned cache и public projection для `GitHub archive evidence`
  (доставка снята: `SPEC-049`);
- `versioned authenticated API/web projection` для отчётов blast radius
  (доставка снята: `SPEC-049`). Account impact API может оставаться read-only,
  но Web не показывает установленную основу, угаданную сервером.

Не входит:

- изменение грамматики `deep_link_v1` из `SPEC-030`;
- изменение локального поведения CLI из `SPEC-043` и `SPEC-044`;
- автоматическая смена `lifecycle`, `blocked/deprecated state` или установка;
- GitHub credentials, private repository polling и внешний tokenizer;
- redesign web brand или новый визуальный мир;
- browser authoring паспортов, setup selection и install flow.

Нормативные владельцы уже существующих смыслов остаются прежними:

- `SPEC-030` и `ADR-0064` владеют `deep-link grammar` и `target semantics`;
- `SPEC-043` владеет estimator, capability delta и `blast-radius semantics`;
- `SPEC-044` и `ADR-0082` владеют `GitHub observation semantics`;
- `SPEC-034` и `SPEC-037` владеют `catalog UX`, `copy actions`, localization и
  `responsive interaction`.

Эта спецификация владеет только серверной/web доставкой этих смыслов и
интегрированным `completion gate`.

## Термины

- **Потребительская проекция (`consumer projection`)** — read-only представление уже принятого контракта на
  другой поверхности без новой доменной интерпретации.
- **Публичная сводка архива (`public archive summary`)** — ограниченная web/API проекция последнего
  server-owned GitHub observation без raw response и credentials.
- **Отчёт влияния аккаунта (`account impact report`)** — server-scoped версия отчёта, ограниченная текущим
  account и его разрешёнными synced entities.
- **Канонический источник копирования (`canonical copy source`)** — один
  machine-readable источник для шаблонов CLI copy, порождённых web-констант и
  contract tests.
- **Ограниченный gate (`scoped gate`)** — отдельный проверяемый quality gate с
  фиксированным include scope, обязательный для `just web-check`.

## Требования

- `REQ-4701`: Web-шаблоны CLI copy используют canonical contract source. В
  `apps/web` не остаётся hand-written копии command grammar, distribution name,
  placeholders или provider names. Порождённая проекция либо механическая
  проверка drift должна завершать сборку ошибкой при несовпадении с
  `packages/contracts`.

- `REQ-4702`: `just web-test` запускает scoped catalog coverage config вместе с
  обычным web coverage. Gate имеет фиксированный набор включаемых production-файлов из
  `vitest.catalog.config.ts`, требует не менее 95% statements, branches,
  functions и lines и возвращает ненулевой exit code при нарушении любого
  порога. Удаление файла, уменьшение порога или расширение exclusions не
  считается исправлением.

- `REQ-4703`: Web-потребитель deep links использует тот же packaged positive и
  negative corpus, что и contracts/CLI. Parser остаётся pure: не делает
  catalog lookup, не подтверждает существование target и не превращает URL в
  источник enumeration. Он принимает только маршруты `deep_link_v1` и
  возвращает нормализованный target, `cli_argv` и безопасную human projection.

- `REQ-4704`: Component, setup, exact-version и publisher web surfaces дают
  canonical `Copy URL` и `Copy CLI command` там, где target доступен текущей
  проекции. Exact-version surface содержит `#report` anchor для report intent.
  Hidden/private/inaccessible target не раскрывает существование и не создаёт
  копируемую ссылку поверх authorization boundary.

- `REQ-4705`: Server/Web delivery периодических GitHub archive observations
  заменена `SPEC-049` `REQ-4902`…`REQ-4905`. Локальный CLI evidence остаётся
  у `SPEC-044`.

- `REQ-4706`: Periodic worker refresh каталога заменён on-demand metadata
  request из `SPEC-049`. Catalog list не инициирует внешний GitHub вызов.

- `REQ-4707`: Public catalog больше не несёт `github_archive` summary. Stars и
  условный `Archived` badge принадлежат `SPEC-049`.

- `REQ-4708`: Отсутствие GitHub metadata не скрывает catalog object и не
  создаёт false warning; детали — `SPEC-049` `REQ-4903`/`REQ-4904`.

- `REQ-4709`: Локальные v1 `SelectionImpactReport` и `BlastRadiusReport`
  сохраняют `local_snapshot` / `local_registry`. Account blast-radius server
  contract снят `SPEC-049` `REQ-4906`.

- `REQ-4710`: `GET /v1/selection/blast-radius` снят. `GET /v1/selection/impact`
  остаётся read-only authenticated resource без Web baseline projection.

- `REQ-4711`: Impact API не выдумывает нулевую стоимость и не раскрывает
  чужие private objects. Web не читает installed/selected state (`SPEC-049`
  `REQ-4911`).

- `REQ-4712`: Web не показывает account blast radius и не выдаёт action как
  auto-update/uninstall. Context budget и CLI copy принадлежат `SPEC-049`.

- `REQ-4713`: Все новые web states и labels имеют RU/EN parity и keyboard-first
  behavior. Каждый интерактивный control имеет состояния `default`, `hover`, `focus`,
  `active`, `disabled`, `loading` и `error`; `loading` использует skeleton, а `stale`,
  unavailable, private и validation cases объясняют следующее безопасное
  действие. Layout сохраняет текущую дизайн-систему, semantic tokens, visible
  focus, reduced motion и WCAG 2.2 AA.

- `REQ-4714`: Каждый новый API field, endpoint, migration, worker job и
  generated client имеет source contract, negative tests, public/private
  matrix, migration/recovery evidence и traceability к одному из #241/#307/#309/
  #344/#347. Issue нельзя закрыть только по unit tests без exact SHA и
  наблюдаемого `just web-check`/`just back-check` результата.

## Состояния и ошибки

### Canonical copy и deep links

- `ready` — canonical source и generated web projection совпадают;
- `copy_failed` — clipboard отказал, но URL/command остаются доступны как text;
- `invalid_reference` — parser отклонил URL/argv без normalization;
- `inaccessible` — web сохраняет non-enumeration поведение.

### GitHub archive

Состояния periodic archive projection сняты. On-demand metadata: `SPEC-049`.

### Selection impact

- `ready` — report complete for declared authority boundary;
- `partial` — отдельная measurement unavailable, причина видна;
- `stale` — source revision или evidence устарели;
- `invalid_graph` — exact graph refused before partial report;
- `forbidden/not_found` — existing authorization and non-enumeration semantics.

## Безопасность и приватность

- Клиент GitHub в worker не принимает credential из request, passport или web.
- Public API не возвращает raw GitHub payload, различие private repository,
  session/device identifiers либо закрытые artifact bytes.
- Запросы `account impact` сначала проверяют принадлежность account, затем
  загружают private rows и не используют скрытые на клиенте поля для authorization.
- UI badges не превращают `external observation` в `trust claim`. Действия
  копирования не помещают токены, локальные пути, учётные данные или состояние
  сессии в URL/argv.
- Аудит и журналы хранят идентификатор операции и ограниченную категорию ошибки,
  но не тело ответа, заголовки с учётными данными или содержимое bytes.

## Совместимость и миграция

1. Сначала публикуются contracts и generated artifacts; старые CLI/web clients
   продолжают читать существующие v1 responses.
2. Затем добавляется nullable storage для наблюдений архива и обработчик worker;
   отсутствие rows означает `unavailable`, а не migration failure.
3. После применения migration API начинает отдавать optional `github_archive`.
   Старые clients игнорируют новое поле по существующей additive policy.
4. Server impact v2 включается отдельным endpoint/response schema; v1 local
   CLI output не меняется.
5. Rollback приложения не удаляет observation history. Rollback migration
   выполняется только по `SPEC-020` backup/downgrade procedure и не должен
   маскировать уже опубликованный catalog object.

## Критерии приёмки

| Requirement | Исполнимый oracle |
|---|---|
| `REQ-4701` | Web tests render every copy template and pass it through the real CLI parser; generated drift check fails on deliberate divergence. |
| `REQ-4702` | `just web-test` runs both configs; catalog suite reaches all four 95% thresholds and a deliberate branch regression fails. |
| `REQ-4703` | Shared positive/negative corpus and pure parser tests cover canonical and hostile URLs. |
| `REQ-4704` | Component/a11y tests and public/private Playwright matrix cover URL, CLI copy, exact-version report anchor and non-enumeration. |
| `REQ-4705` | Oracle принадлежит `SPEC-049`: periodic archive evidence больше не доставляется. |
| `REQ-4706` | Oracle принадлежит `SPEC-049`: catalog list не вызывает GitHub. |
| `REQ-4707` | Oracle принадлежит `SPEC-049`: public catalog не несёт сводку архива. |
| `REQ-4708` | Oracle принадлежит `SPEC-049`: отсутствие metadata не скрывает объект. |
| `REQ-4709` | CLI v1 schemas остаются; generated API не содержит account blast radius. |
| `REQ-4710` | Generated inventory не содержит `/selection/blast-radius`. |
| `REQ-4711` | Impact API сохраняет non-enumeration; Web не читает installed/selected state. |
| `REQ-4712` | Web panel не показывает blast radius и destructive update/uninstall actions. |
| `REQ-4713` | RU/EN parity, keyboard/focus, loading/error states and desktop/narrow viewport browser smoke pass. |
| `REQ-4714` | `just docs-check`, `just back-check`, `just web-check`, generated diff review and issue evidence run on the feature SHA. |
