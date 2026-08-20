---
description: "План реализации web/backend пачки #241, #307, #309, #344 и #347."
last_verified: "2026-08-15"
---

# Web/backend feature plan: #241, #307, #309, #344, #347

## Решение пачки

Ветка: `feature/web-backend-issues-241-307-309-344-347` от
`letya999@94130175`.

Пачка объединена не по визуальной теме, а по одному техническому принципу:
web и API становятся потребителями уже готовых canonical/shared contracts и
перестают создавать локальные копии смысла.

Нормативная спецификация: `SPEC-047`.
Архитектурное решение: `ADR-0094`.
Исходные владельцы смысла: `SPEC-030`, `SPEC-034`, `SPEC-037`, `SPEC-043`,
`SPEC-044`, `ADR-0064`, `ADR-0082`.

## Текущий gap в коде

| Issue | Уже есть | Чего нет |
|---|---|---|
| #344 | `packages/contracts` и real CLI parser уже знают правильные команды | Web держит divergent `cli-copy.ts`, неверные landing messages и не парсит новые placeholders |
| #347 | `vitest.catalog.config.ts`, 7 test files и 95% thresholds | `just web-test` не запускает config; observed branch coverage — 89.74% |
| #241 | CLI `link web`, `deep_link_v1`, positive/negative corpus, существующие routes | Web parser/consumer, canonical actions на detail/version/publisher/report surfaces |
| #309 | CLI observation schema/history/refresh, ADR-0082 | Server storage/worker refresh, catalog API projection, archived/stale UI |
| #307 | Shared v1 schemas, CLI `select impact` и `select blast-radius` | Server account-scoped response version, API routes, web evidence panel и privacy matrix |

## Технический дизайн

### #344 — canonical CLI copy

1. Определить generated web artifact из `packages/contracts.cli_copy`; не
   переносить Python grammar вручную в TypeScript.
2. Подключить artifact к `install-command`, landing messages, object pages,
   empty states, machine projection и `presenters.ts`.
3. Все object pages получают explicit `kind`, `stable_id`, optional exact
   version; блок входа получает явно заданный provider; пустые owner-состояния
   получают только canonical next step.
4. Contract test рендерит каждый шаблон и прогоняет результат через настоящий
   CLI command registry. Отдельно проверяется, что distribution — `ai-stp-cli`,
   а console script — `ai-stp`.

Закрывающая проверка: намеренный drift в generated source ломает web test, а все
кнопки копирования дают команду, которую можно разобрать.

### #347 — catalog gate

1. Сохранить отдельный `vitest.catalog.config.ts` как changed-scope gate.
2. Исправить branch gaps до подключения gate; порог не снижать и exclusions не
   расширять.
3. Запускать `bun run test:coverage:catalog` из `just web-test` после обычного
   web coverage либо отдельной командой с тем же non-zero failure semantics.
4. Добавить regression check, который изменяет одну ветвь и подтверждает, что
   scoped gate действительно падает.

Закрывающий oracle: обычный `just web-check` без ручного дополнительного
скрипта запускает 95% catalog gate.

### #241 — web deep-link consumer

1. Подключить эталонный corpus к web-парсеру и formatter.
2. Вынести отображение маршрутов в один чистый модуль: object component/setup,
   exact version, publisher и report fragment.
3. Добавить `Copy URL`, `Copy ID`, `Copy CLI command` в существующее menu/action
   vocabulary; не создавать новый визуальный паттерн.
4. Сохранить report anchor `#report` и проверить direct navigation после
   hydration.
5. Проверить public anonymous, hidden/private, foreign origin, query,
   credentials, encoded separators и invalid locale.

Периодическое свидетельство архива GitHub и радиус поражения аккаунта на
сервере и в Web заменены `SPEC-049` и `ADR-0096`. Заметки ниже остаются
исторической записью реализации #309 и #307.

### #309 — server GitHub archive projection

1. Добавить отдельные ORM entities и Alembic migration для latest/history
   observation; `RepositoryMetric` не расширять archive semantics.
2. Вынести bounded GitHub public metadata client рядом с существующим
   `github_api_url`, но без worker token и без redirect.
3. Добавить `JobType` и handler с idempotency/freshness policy; refresh trigger
   — publication/explicit maintenance path, catalog GET — read-only.
4. В catalog projection добавить optional `github_archive` summary в list/detail/
   exact-version models; raw payload не отдавать.
5. Проверить archived, unarchive, rename/transfer, 304, 403/404/429/5xx,
   malformed response, stale cache и private source.

#### Proposed public summary

```text
github_archive: {
  provider: "github",
  state: "active" | "archived" | "unavailable",
  freshness: "fresh" | "stale" | "unavailable",
  observed_at: timestamp | null,
  repository_full_name: string | null,
  source_url: https URL | null,
  proposal: "none" | "deprecated",
  attribution: string
} | null
```

`repository_id`, ETag, failure details и raw response остаются server-internal.

### #307 — server impact projection

1. Не менять local v1 models. Добавить отдельную семью server v2 response с явными
   `authority_boundary=account`, `freshness`, source revision и `action=none`.
2. Реализовать:

   - `GET /v1/selection/impact` — exact candidate setup, optional exact
     baseline и owner-scoped project selector;
   - `GET /v1/selection/blast-radius` — exact component/version и scenario.

3. Собрать account scope из server sync/read model; не обещать global/org
   полноту там, где сервер ещё не хранит соответствующий entity.
4. Для недоступных artifact/graph/baseline возвращать explicit unavailable,
   а не 0. Для unauthorized target сохранять existing non-enumeration.
5. Generated API client и web presenter используют response schema, а не
   локально собранные `Record<string, unknown>`.

## UI brief по `$impeccable`

Это Operate/readable evidence UI внутри существующего catalog/detail/account
мира. Новый visual world не нужен.

### Архитектура поверхности

- Archive status — компактный secondary evidence row рядом с source/provenance,
  но отдельно от trust/security badges.
- Impact — раскрываемый evidence panel после основного object identity и перед
  destructive/owner actions; report не должен конкурировать с главным CTA.
- Внутри panel: baseline, абсолютный бюджет, signed delta, добавленные и удалённые
  capabilities, blast-radius counts/links, freshness и authority boundary.
- На narrow viewport панель становится последовательным блоком, без
  горизонтальной таблицы и без потери labels/actions.

### Обязательные состояния

- loading: skeleton rows, без spinner-only блокировки detail;
- ready: evidence values с source и timestamp;
- stale: warning tone и понятное «последняя проверка»;
- unavailable: нейтральное объяснение, без нулей и без failed badge;
- private/inaccessible: generic not-found/non-enumeration state;
- copy success/failure: live-region feedback, clipboard fallback text;
- keyboard: focus visible, Escape закрывает menu/panel, focus возвращается к trigger;
- reduced motion: no decorative animation.

### Визуальные и accessibility constraints

- Использовать существующие tokens, icons и card/menu primitives; raw hex и
  новые ad-hoc colors запрещены.
- Archive — предупреждение о состоянии, а не оранжевая основная CTA и не метка verification.
- Impact fields читаются при light/dark theme, RU/EN и 360–430px width.
- Labels, tooltips, dates, `aria-describedby`, `role=status` и error copy имеют
  полный RU/EN parity.
- Component tests проверяют semantic names, keyboard path и absent-data states;
  Playwright проверяет desktop/narrow public and signed-in routes.

## Порядок работы

### Phase 0 — contracts and gates

- Добавить или скорректировать порождённые источники контрактов для web copy и server v2 impact.
- Add positive/negative fixtures.
- Wire #347 only after its coverage gaps are covered.

### Phase 1 — low-risk web correctness

- Close #344.
- Close #241.
- Keep #347 green in every subsequent web change.

### Phase 2 — server evidence

- Migration, model, bounded GitHub client, worker handler, projection.
- API and catalog tests for #309.
- Web archive row and states.

### Phase 3 — account impact

- Server v2 contracts and account-scoped queries.
- API auth/non-enumeration matrix.
- Web impact/blast-radius panel and responsive/a11y tests.

### Phase 4 — integrated closure

- Run generated checks and inspect diff.
- Run `just docs-check`, `just back-check`, `just web-check` in the real
  checkout; записать exact commands и результаты в PR.
- Verify migration upgrade/repeat/downgrade/upgrade and no data leak fixtures.
- Закрывать issues отдельно только после exact evidence по их acceptance criteria;
  не закрывать пять issues автоматически по имени ветки.

## Test matrix

| Layer | Required evidence |
|---|---|
| Contracts | deep-link/copy corpus, v2 impact/archive schemas, generated schema drift |
| Platform | ORM projection, archive observation state machine, no-trust/no-lifecycle mutation |
| API | anonymous catalog, authenticated owner, outsider, stale/unavailable, invalid graph, non-enumeration |
| Worker | 200/304/403/404/429/5xx/malformed/private/rename/unarchive and bounded retry |
| Web unit/component | copy templates, parser, archive/impact states, RU/EN parity, keyboard/focus |
| Web browser | public detail, exact version, report anchor, signed-in impact, 360–430px |
| Gates | `just docs-check`, `just back-check`, `just web-check`, final diff review |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Server v2 accidentally changes CLI v1 | Separate response models and explicit authority/freshness fields |
| GitHub outage changes public catalog | Read-through cache; no network in catalog request; last good observation |
| Private data leaks through blast radius | Owner-scoped query, server-side auth before row loading, negative tests |
| Web copy drifts again | Generated projection plus parser-backed contract test |
| 95% gate is bypassed | Invoke scoped config from `just web-test`, deliberate failure test |
| UI hides uncertainty | Required stale/unavailable/private states and visible provenance |

## Definition of done

The branch is ready for review only when:

1. `SPEC-047`, `ADR-0094`, generated indexes and impacted contracts agree;
2. #344 and #347 have executable web evidence;
3. #241 has shared corpus and public/private browser evidence;
4. #309 has migration, worker, API and catalog/detail evidence;
5. #307 has server v2 contract, auth-bound API and web evidence panel;
6. ни один test не снижает threshold и не считает unavailable data успехом;
7. все обязательные checks запущены на feature SHA, а diff не содержит
   несвязанных изменений.
