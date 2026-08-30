---
description: "Порядок перехода content hub на единое API serving для repository и staff публикаций."
last_verified: "2026-08-29"
---

# План реализации гибридной публикации статей

Нормативные владельцы: `SPEC-054`, `ADR-0132` и
`docs/contracts/article-publication.md`. `SPEC-053` получает только событие
активированной ArticleRevision и не владеет import или staff publication.

## 1. Expand: contracts и persistence

1. Добавить canonical contract models и OpenAPI operations public read,
   repository state/import и staff publish/unpublish; перегенерировать schemas и
   web client.
2. Выделить стабильную Article с source owner, неизменяемой локализованной
   ArticleRevision и active pointers. Расширить уже подготовленные article tables
   аддитивной migration вместо второй модели документов.
3. Сделать digest ревизии покрывающим метаданные, тело и происхождение, а active
   digest — точную RU/EN пару.
4. Добавить scoped import credential configuration и AuditEvent для import/staff
   mutations без тела или credential в записи.
5. Оставить существующее обслуживание из filesystem без изменений на этом этапе.

Exit: schema и API contracts разворачиваются рядом со старым web; старый image
игнорирует новые tables и routes.

## 2. Repository snapshot и atomic import

1. Переиспользовать текущий content loader для валидации и сериализации
   опубликованных entries в canonical snapshot; не писать второй Markdown parser.
2. Встроить snapshot и точный commit в release artifact без обращения к API/DB во
   время image build.
3. Перенести repository import из пространства SEO в сервис content publication;
   после успешной активации ставить SEO effect через узкий вызов `SPEC-053`.
4. Реализовать full-snapshot transaction: validate all, lock generation, reject
   отклонить конфликты источников, создать отсутствующие revisions, сменить pointers и снять отсутствующие
   repository entries, increment generation once.
5. Добавить one-shot importer, который читает state, передаёт expected generation
   и точный snapshot, а в лог пишет только commit, snapshot digest, счётчики и
   outcome.

Результат этапа: повтор точного snapshot является `no_op`; неверный или stale snapshot оставляет
active set и jobs неизменными.

## 3. Staff publication

1. Реализовать staff allowlist guard существующим account/session механизмом.
2. Публиковать RU/EN переводы и active pointers одной транзакцией с
   optimistic check по active digest.
3. Реализовать staff unpublish без удаления revision history.
4. Запретить staff mutation identity источника `repository` и перехват источником `repository`
   staff-owned identity общей source-owner проверкой.
5. Ограничить payload и применить действующую политику safe Markdown до записи.

Результат этапа: staff-статья появляется в public API без сборки web; stale update и source
collision не имеют частичного эффекта.

## 4. Public serving и web switch

1. Реализовать единые public list/detail reads активных repository и staff
   articles с ETag и redaction private provenance.
2. Перевести индекс content, detail и metadata на серверный API client; убрать
   поиск в filesystem из пути request и разрешить runtime slug из БД.
3. Перевести human/machine projection и Atom на тот же public read model.
   Discovery/SEO продолжает читать active ArticleRevision через `SPEC-053`.
4. Сохранить build-time gate `content_hub`: disabled image не публикует routes,
   навигацию или discovery и не делает запрос content.
5. Не добавлять client-side merge, fallback на repository files или отдельный
   cache service; использовать действующую public RSC/API cache boundary.

Результат этапа: одна API fixture одновременно показывает repository и staff articles во
всех projections; изменение DB не требует rebuild.

## 5. Порядок deploy и rollout

1. Добавить content importer как one-shot release service после `migrate` и
   healthy API. Новый web зависит от его успешного завершения.
2. Перед первым switch импортировать текущий snapshot и сравнить type/slug,
   локаль `locale`, metadata, body digest и публичное количество с источником filesystem.
3. Выполнить expand/import/switch: сначала schema/API, затем backfill snapshot,
   затем web API reads.
4. При неуспешном import не менять active repository generation; остановить deploy и
   вернуть предыдущий exact ref/image по действующему runbook.
5. После окна rollback удалить обслуживание из filesystem и старый build-time список routes
   отдельным изменением контракта; authoring repository и сборщик snapshot остаются.

Exit: новый release показывает snapshot своего exact commit плюс все ранее
опубликованные staff-статьи; откат release repository не меняет staff set.

## Минимальная тестовая матрица

| Срез | Обязательное доказательство |
|---|---|
| Snapshot | Determinism, exact commit/path, whole-content digest, bounds и locale parity. |
| Platform | Atomic replace, no-op repeat, add/update/remove, source conflict, stale generation и history retention. |
| Staff API | Allowlist, RU/EN atomicity, stale active digest, unpublish и audit redaction. |
| Public API | Единая сортировка, detail, отсутствие fallback, ETag, 404 и исключение private fields. |
| Web | SSR index/detail, metadata, human/machine/Atom parity и disabled feature 404. |
| SEO | Один effect на active change; publication сохраняется при failed worker. |
| Deploy | migrate→API ready→import→web ready, failed import и rollback previous snapshot. |

## Явно отложено

- браузерный редактор, интерфейс preview, роли согласования и отложенная публикация — до
  отдельного редакторского workflow;
- перенос Article между `repository` и `staff` — до явной auditable migration
  operation;
- загрузка media и библиотека assets — repository illustrations продолжают действовать
  по текущей safe Markdown policy;
- брокер сообщений, сервис CMS и отдельный content microservice — до измеримой
  нагрузки, которую не выдерживают API/PostgreSQL;
- pagination public content list — до измеримого размера, при котором bounded
  полный locale list перестаёт укладываться в текущий cache contract.
