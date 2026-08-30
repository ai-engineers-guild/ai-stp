---
description: "Порядок реализации серверного SEO-контура без смешивания domain publication и model-enrichment."
last_verified: "2026-08-29"
---

# План реализации серверного SEO-контура

Нормативные владельцы: `SPEC-053`, `ADR-0131` и
`docs/contracts/seo-publication-projection.md`. Этап считается завершённым только
после `just docs-check`, `just back-static`, `just back-test`, `just web-check` и
просмотра diff в публичном checkout.

## 1. Expand: persistence и contracts

1. Добавить additive таблицы `seo_fact_snapshot`, `seo_revision` и
   `seo_active_revision`, unique constraints для snapshot/revision identity и
   generation counter без удаления существующих полей.
2. Добавить Pydantic/OpenAPI contracts profile v1, state/error enums и public
   модели чтения; перегенерировать contract artifacts.
3. Добавить `seo_build` и `seo_enrich` в закрытый job registry и handler stubs,
   которые пока не ставятся production flow.
4. Подключить active `ArticleRevision` по `SPEC-054` как subject статьи; import,
   публикация staff и владение source остаются за публикацией content.
5. Расширить curated service presentation обязательными для индексации
   description и public source URL, сохранив существующие записи readable и
   `noindex` до enrichment данных.

Откат этапа: старый код игнорирует добавленные таблицы и необязательные поля service.

## 2. Deterministic base

1. Реализовать allowlist-сборщики фактов для пяти видов subject и canonical
   digest агрегата.
2. Реализовать один profile builder с kind-specific templates, index decision,
   links, social facts и JSON-LD.
3. Поставить `seo_build` из component/setup publication, смены active
   `ArticleRevision` по `SPEC-054` и service mutation в общей транзакции с
   изменением источника; country rebuild выводить из изменившихся relations.
4. Активировать base revision и generation атомарно; повтор job и конкурентная
   доставка должны иметь один эффект.
5. Backfill существующих public subjects ограниченными keyset batches; thin
   service/country subjects получают `noindex`, а не AI-заполнитель.

Exit: каждая фикстура имеет активный base profile без сетевого доступа.

## 3. Serving и discovery

1. Перевести `generateMetadata` component/setup/service/country/article на одну
   публичную SEO-модель чтения с текущим presenter как миграционным fallback.
2. Рендерить видимые rich sections и JSON-LD из одной profile revision; сохранить
   current human/machine route semantics `ADR-0076`.
3. Заменить статический sitemap projection на generation-aware index/shards.
4. Добавить root/detail LLM routes и пагинируемый NDJSON manifest.
5. Добавить revision-addressed OG route и object-store/cache materialization.
6. Проверить HTTP 200/404, robots, canonical, hreflang, ETag, public cache и
   отсутствие cookie/session на каждом discovery route.

Exit: crawler может пройти от sitemap/hub обычными links до каждой eligible
fixture, а metadata, HTML, JSON-LD, OG и Markdown согласованы.

## 4. Необязательное улучшение через LiteLLM

1. Добавить отдельный compose profile `seo_enrichment` с LiteLLM и optional
   CLIPROXY upstream; API и основной worker стартуют без него.
2. Добавить настройки worker только для URL LiteLLM, credential процесса и alias модели,
   таймаута и флага включения; upstream credentials принадлежат proxy deployment.
3. Реализовать versioned prompt, строгий структурированный ответ и проверку фактов.
4. Добавить stale guard перед и после вызова, bounded retry и атомарную активацию
   accepted candidate; отказ оставляет base active.
5. Собрать фиксированный RU/EN eval corpus по всем видам subject: точные факты,
   запрещённые утверждения, prompt injection, дубликаты, неверный JSON, timeout и
   stale response. Выбор локальной модели выполняется по этому corpus; имя модели
   не закрепляется продуктовым контрактом.

Exit: выключение/падение обоих proxy не меняет публикацию и serving; accepted
output не содержит фактов вне snapshot.

## 5. Rollout и evidence

1. Развернуть схему и dual-read, выполнить base backfill, сравнить текущий и
   новый HTML/metadata на production-like corpus.
2. Переключить reads на active SEO revisions; оставить fallback на окно rollback.
3. Включить enrichment сначала для малой deterministic cohort и одного locale,
   затем расширять только при приемлемых rejection/cost/latency.
4. Зарегистрировать sitemap в Google Search Console и Yandex Webmaster; снять
   crawl/index evidence, не выдавая submission за index success.
5. Наблюдать путь публикация→допуск→sitemap→обход→индекс→клик→действие каталога по
   агрегатам вида subject и locale; исходный запрос и subject ID не нужны метрикам платформы.
6. После окна совместимости удалить fallback отдельным PR и migration contract
   phase; новые таблицы не удалять в rollback текущего rollout.

## Минимальная тестовая матрица

| Срез | Обязательное доказательство |
|---|---|
| Платформа | Точный snapshot, идемпотентные jobs, stale guard, атомарный pointer, возобновление backfill. |
| API contracts | Closed enums, public/private boundary, conditional fields, stable errors. |
| Web | Metadata, JSON-LD, HTML links, sitemap shards, LLM Markdown, OG dimensions/cache. |
| Security | Secret/private-field exclusion, prompt injection corpus, URL allowlist, safe Markdown. |
| Degradation | No model, timeout, malformed output, dead-letter, API outage and last-active serving. |
| Migration | Old web/new schema, new web/no active revision, rollback and resumed backfill. |

## Явно отложено

- keyword-volume providers и Search Console query ingestion — до наличия
  измеренного решения о данных, доступе и retention;
- автоматические FAQ rich results — до отдельного visible FAQ contract;
- социальная публикация — SEO profile только готовит preview;
- отдельный SEO microservice, broker и vector database — до измеримой нагрузки,
  которую не выдерживают platform/worker/PostgreSQL;
- массовые country×service×component посадочные страницы — до доказанного уникального
  intent и данных каждой страницы.
