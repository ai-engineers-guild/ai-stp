---
description: "SPEC-053: Серверные SEO-ревизии для компонентов, сетапов, статей, сервисов и стран."
last_verified: "2026-08-29"
---

# SPEC-053: Серверный SEO-контур публичных сущностей

## Цель

Каждая публикация или содержательное обновление публичного компонента, сетапа,
статьи либо сервиса автоматически создаёт согласованную rich page projection:
HTML metadata, JSON-LD, social preview, sitemap membership, внутренние связи и
LLM-readable документ. Детерминированная версия становится доступной независимо
от модели; необязательное AI-обогащение улучшает только presentation-текст.

## Границы

Входят серверные snapshots и SEO-ревизии, пять видов subject, два job type,
решение об индексации, варианты locale, индекс/shards sitemap, Open Graph image,
`llms.txt`/detail Markdown, repository article import, service presentation
metadata, LiteLLM adapter, factual validation, observability, migration и
rollback. Точный публичный формат принадлежит
`docs/contracts/seo-publication-projection.md`, а архитектурное решение —
`ADR-0131`.

Не входят CMS, редактор статей в web, keyword scraping, покупка ссылок,
автопубликация в социальные сети, гарантии позиции в выдаче, model-generated
доменные факты, изменение passport digest и отдельный брокер сообщений.

## Термины

- **SEO subject** — публичная сущность вида `component`, `setup`, `article`,
  `service` или `country`.
- **SeoFactSnapshot** — неизменяемый набор публичных фактов exact subject revision
  и locale с canonical digest.
- **SeoRevision** — неизменяемое presentation-представление snapshot со своим
  происхождением генератора и состоянием.
- **Base revision** — полностью рабочая детерминированная SEO-ревизия без модели.
- **Enriched revision** — кандидат, полученный через LiteLLM и прошедший
  механическую и factual проверку.
- **Index eligibility** — серверное механическое решение о включении canonical URL
  в sitemap и выдаче `index,follow`.

## Требования

### События и хранение

- `REQ-5301`: Успешная публикация component/setup транзакционно ставит `seo_build`
  для точных stable ID, version, locale и source digest; повторная доставка с теми
  же координатами не создаёт второй snapshot или повторный активный эффект.
- `REQ-5302`: Активация или снятие с публикации `ArticleRevision` по `SPEC-054`
  идемпотентно ставит `seo_build` для exact article revision/source digest;
  Импорт repository и staff publication не зависят от завершения SEO job.
- `REQ-5303`: Создание или изменение публичного service, его стран либо связей с
  опубликованными objects вычисляет digest всего публичного агрегата и ставит
  `seo_build` для service и затронутых country pages.
- `REQ-5304`: `SeoFactSnapshot` хранит subject kind/id/revision, locale,
  `source_digest`, schema version, публичные facts и время снимка; secret-bearing,
  private и artifact-body поля отвергаются до записи.
- `REQ-5305`: `SeoRevision` хранит snapshot ID, state, profile document,
  версии template/prompt, вид генератора, model alias при его наличии, времена и
  безопасный error code; одна `SeoActiveRevision` существует на subject/locale.
- `REQ-5306`: Активация новой ревизии и увеличение SEO generation происходят
  атомарно; незавершённая или stale ревизия никогда не читается как активная.

### Базовая проекция

- `REQ-5307`: `seo_build` первым шагом формирует base revision без сети и модели,
  содержащую title, description, H1, canonical, locale alternates, robots,
  taxonomy tags, breadcrumbs, social metadata, JSON-LD, план секций,
  внутренние ссылки, факты изображения и решение об индексации.
- `REQ-5308`: Недоступность LiteLLM, CLIPROXY или любой модели не задерживает
  доменную публикацию, активацию базовой ревизии, sitemap и отображение rich page.
- `REQ-5309`: Canonical принадлежит stable subject page; version pages и query
  variants не становятся самостоятельными canonical URL без отдельного
  содержательного контракта.
- `REQ-5310`: Locale alternate объявляется только для существующей активной
  locale revision; отсутствующий перевод не получает вымышленный hreflang URL.
- `REQ-5311`: JSON-LD и visible HTML строятся из одного profile; structured data
  не содержит скрытого FAQ, рейтинга, отзыва, цены, совместимости или verification,
  которых нет в видимой странице и snapshot.
- `REQ-5312`: Профиль компонента/сетапа показывает назначение, совместимость,
  requirements, permissions, credentials, verification evidence, source, author,
  versions и реальные relations; профиль статьи — author/dateModified/body/related
  subjects; профиль service/country — только реально связанные public objects.

### Индекс, обнаружение и social

- `REQ-5313`: `index_eligible` вычисляется без модели по lifecycle, visibility,
  HTTP availability, минимальной полноте kind-specific facts, canonical uniqueness
  и наличию уникального содержимого; отрицательное решение хранит stable reasons.
- `REQ-5314`: Неeligible страница отвечает `noindex,follow` и отсутствует во всех
  shards sitemap; eligible canonical отвечает `index,follow` и присутствует ровно
  один раз.
- `REQ-5315`: `/sitemap.xml` является sitemap index либо sitemap текущего малого
  набора и перечисляет кэшируемые shards по виду subject/locale, абсолютные canonical,
  фактический `lastmod` и существующие alternates; один shard не превышает 50 000 URL.
- `REQ-5316`: Активация ревизии инвалидирует generation-aware sitemap/LLM cache;
  один job не дописывает общий XML или текстовый файл и конкурентные активации не
  теряют URL.
- `REQ-5317`: Social profile содержит Open Graph и Twitter title, description,
  canonical URL, locale, имя сайта, URL изображения и alt; маршрут изображения адресуется
  immutable revision ID, возвращает 1200×630 asset и допускает долговечный public
  cache.
- `REQ-5318`: Корневой `/llms.txt` остаётся компактным индексом; `/llms-full.txt`
  описывает продукт и stable разделы, а каждый active subject доступен отдельным
  canonical Markdown document и через пагинируемый catalog manifest, не требуя
  помещать весь растущий каталог в один файл.
- `REQ-5319`: Public HTML содержит crawlable `<a href>` links по хранимым relations;
  search form и client event не являются единственным путём к индексируемому
  сущности subject.

### Model enrichment

- `REQ-5320`: После base activation конфигурация может поставить `seo_enrich`;
  выключенная конфигурация завершает поток состоянием `base_active` без ошибки.
- `REQ-5321`: Worker вызывает только настроенный OpenAI-compatible LiteLLM URL по
  alias модели; маршрутизация к CLIPROXY и резервному provider не кодируется в обработчике задания.
- `REQ-5322`: Запрос модели содержит versioned instruction, закрытую output schema и
  публичный `SeoFactSnapshot`; credentials, private profile, raw artifact и
  validation finding body не передаются.
- `REQ-5323`: Model output может менять только разрешённые presentation fields и не
  может задать canonical, robots, решение об индексации, lifecycle, trust, verification,
  source links или numeric facts. Модель может объяснять известные публичные инструменты
  и технические категории из общих знаний, но object-specific утверждения обязаны
  следовать из snapshot.
- `REQ-5324`: Candidate проходит JSON Schema, limits, locale, URL allowlist,
  поиск секретов, проверку неподтверждённых утверждений, сходство дубликатов,
  предметность title/description, полезность search intents, обязательное покрытие
  доступных фактов секциями своего subject kind и точный source digest; failure
  сохраняет safe code и оставляет base active. Worker делает не более пяти
  попыток исправления rejected candidate с безопасной причиной отказа. Service
  без собственного description и source URL не получает model enrichment.
  Search description, близкий к машинному source description, считается rejected:
  enrichment обязан переводить паспортные термины в пользовательскую задачу.
  Для workflow/orchestration subject с фактами о roles, topology или review кандидат
  обязан явно описать agent outcome в title или search description, а не оставить
  внутренние термины без расшифровки или спрятать смысл только в body.
- `REQ-5325`: Ответ для старого source digest получает `stale` и не активируется;
  retry с тем же snapshot/template/prompt/model имеет один idempotency key.
- `REQ-5326`: Operator может отключить enrichment и атомарно вернуть любой subject
  на последнюю valid base revision без изменения доменного объекта.

### Кэш, безопасность и эксплуатация

- `REQ-5327`: Public SEO read не читает session/cookies и следует public cache
  boundary; preview/admin status является private и `no-store`.
- `REQ-5328`: HTML, JSON-LD, Markdown и текст модели проходят действующий safe
  Markdown/escaping profile; ответ модели не вставляет raw HTML или script.
- `REQ-5329`: Model credential существует только в deployment secret для worker;
  payload задания, DB, ответ API, structured log, метрики и пример репозитория его
  не содержат.
- `REQ-5330`: Метрики различают build/enrich latency и outcome, active base/enriched,
  stale/rejected candidates, index eligibility reasons, sitemap generation, model
  requests/tokens/cost alias и cache age без prompt, тела контента или идентификаторов.
- `REQ-5331`: Public route сохраняет последнюю active revision при временной ошибке
  API, worker или model; отсутствие active revision использует текущий server-side
  deterministic presenter и `noindex` до materialization, а не soft-404.
- `REQ-5332`: Rebuild по новой template/prompt version создаёт новую revision того
  же snapshot ограниченной партией и не меняет domain `updated_at` или sitemap
  `lastmod`, пока visible primary content не изменилось.

## Состояния и ошибки

SEO revision проходит `building`, `base_ready`, `enriching`, `validating`,
`active`, `rejected`, `failed` или `stale`. Active pointer ссылается только на
`base_ready`/прошедший enriched candidate, который в той же транзакции становится
`active`; прежняя active revision остаётся доступной для rollback.

Stable error codes: `AI_STP_SEO_FACTS_INVALID`, `AI_STP_SEO_OUTPUT_INVALID`,
`AI_STP_SEO_ENRICHMENT_UNAVAILABLE`, `AI_STP_SEO_SOURCE_STALE` и
`AI_STP_SEO_RENDER_FAILED`. Model unavailability является деградацией enrichment,
а не ошибкой domain publication или public page.

## Безопасность и приватность

Snapshot строится allowlist-проекцией публичных полей. Model boundary считается
внешним egress даже при локальном upstream: endpoint и credential принадлежат
оператору, HTTPS обязателен вне внутренней compose network. Prompt injection в
article/component description является данными, а versioned instruction запрещает
исполнять содержащиеся в них указания. Raw prompt/response сохраняется только в
отдельном выключенном по умолчанию redacted diagnostic режиме без credential и
private facts.

AI-текст имеет provenance `model`, но не получает evidence semantics. Factual
validator принимает только утверждения, выводимые из snapshot; неизвестное удаляет
candidate целиком, а не публикует с предупреждением.

## Совместимость и миграция

Rollout выполняется expand/migrate/switch/contract: добавить таблицы и nullable
presentation-поля service; включить двойное чтение с текущим presenter; backfill base
revisions для существующих public subjects; сравнить HTML/metadata; переключить
web/sitemap/LLM reads; включить enrichment последним. Старый web image игнорирует
новые таблицы. Новый web при отсутствии active revision использует fallback по
`REQ-5331`.

Article authoring, revisions, repository import и public serving принадлежат
`SPEC-054`; SEO принимает только событие exact active revision. Откат enrichment
возвращает текущий presenter, не меняя active article set; новые SEO tables
сохраняются до конца окна совместимости.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-5301` | Интеграционный тест повторно доставляет публикацию component/setup и получает один snapshot и один активный эффект. |
| `REQ-5302` | Integration test получает один SEO effect на новую active article revision и unpublish и сохраняет domain publication при failed worker. |
| `REQ-5303` | Тест изменения service relation ставит rebuild только service и затронутых country subjects с новым digest агрегата. |
| `REQ-5304` | Schema/property test принимает только публичный allowlist snapshot и отклоняет secret/private/artifact body. |
| `REQ-5305` | Миграционный тест проверяет поля revision и unique active pointer на subject/locale. |
| `REQ-5306` | Конкурентный тест активации не теряет generation и не показывает незавершённую или stale revision. |
| `REQ-5307` | Параметризованный тест пяти видов subject и двух locales строит полный base profile без сети. |
| `REQ-5308` | E2E с недоступными LiteLLM/CLIPROXY публикует domain object, активирует base и отдаёт sitemap/page. |
| `REQ-5309` | Web test проверяет stable canonical и отсутствие самостоятельного canonical у version/query variants. |
| `REQ-5310` | Locale matrix объявляет hreflang только для существующей active revision. |
| `REQ-5311` | Snapshot test сравнивает visible HTML и JSON-LD и не находит скрытых claims. |
| `REQ-5312` | Kind-specific fixtures показывают все обязательные секции только из фактов snapshot. |
| `REQ-5313` | Матрица lifecycle/fullness/availability возвращает deterministic eligibility и stable reasons. |
| `REQ-5314` | Eligible и non-eligible fixtures проверяют согласованность robots и sitemap membership. |
| `REQ-5315` | Генератор выдаёт absolute canonical, реальный lastmod, существующие alternates и делит 50 001 URL на два shards. |
| `REQ-5316` | Конкурентные активации инвалидируют общий generation cache без lost URL и записи общего файла из handler. |
| `REQ-5317` | Web test читает OG/Twitter metadata и 1200×630 immutable image с public cache headers. |
| `REQ-5318` | E2E проходит от компактного `llms.txt` через manifest к detail Markdown, не загружая весь каталог одним документом. |
| `REQ-5319` | Crawler test доходит от hubs до каждого eligible fixture только по серверным `<a href>`. |
| `REQ-5320` | Выключенная конфигурация не ставит enrichment и завершает поток активной base revision без ошибки. |
| `REQ-5321` | HTTP contract test видит один вызов configured LiteLLM URL по alias и не видит routing logic upstream в handler. |
| `REQ-5322` | Captured request соответствует schema и не содержит credential, private facts, artifact или finding body. |
| `REQ-5323` | Adversarial response с canonical/trust/index полями отклоняется целиком. |
| `REQ-5324` | Табличный corpus отдельно отклоняет неверные schema/locale/URL, secret, unsupported claim, duplicate, водяной snippet, слабые intents и неполное kind-specific покрытие; integration test принимает исправленный candidate после bounded retry. |
| `REQ-5325` | Ответ старого digest становится `stale`, а повтор тех же координат использует один idempotency key. |
| `REQ-5326` | Operator test отключает enrichment и атомарно возвращает subject к последней base revision. |
| `REQ-5327` | Public read test не обращается к session/cookies и имеет public cache, private preview — `no-store`. |
| `REQ-5328` | XSS/prompt-injection corpus не создаёт raw HTML/script в HTML, JSON-LD или Markdown. |
| `REQ-5329` | Secret scan DB/job/log/API/repository и dependency closure CLI не находят model credential/client. |
| `REQ-5330` | Metrics snapshot содержит перечисленные агрегаты без prompt, body, subject ID или job payload. |
| `REQ-5331` | Fault-injection test продолжает отдавать последнюю active revision, а pending materialization получает fallback `noindex`, не soft-404. |
| `REQ-5332` | Bounded rebuild новой generator version создаёт revision и не меняет domain `updated_at`/sitemap `lastmod` при неизменном visible content. |
