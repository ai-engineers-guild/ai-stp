---
description: "SPEC-054: Единая серверная публикация repository- и staff-authored статей."
last_verified: "2026-08-29"
---

# SPEC-054: Гибридная публикация статей через platform

## Цель

Content hub показывает через один public API опубликованные статьи двух
источников авторинга: snapshot репозитория текущего выпуска web и staff API.
Repository-материалы обновляются при deploy, staff-материалы — без web rebuild;
server web строит human и machine страницы из одной активной DB revision.

## Границы

Входят стабильная identity статьи, неизменяемые локализованные revisions, владение
источником, сборка и import snapshot репозитория, публикация staff и unpublish,
публичные list/detail reads, атомарная активация, порядок deploy, identity cache,
аудит, migration и rollback. Точный wire contract принадлежит
`docs/contracts/article-publication.md`, архитектурное решение — `ADR-0132`, а
производные SEO revisions — `SPEC-053`.

Не входят редактор в браузере, approval workflow, scheduled publication, произвольный
Git URL import, пользовательские авторы, media upload и перенос identity между
sources без отдельной миграционной операции.

## Термины

- **Article** — стабильный content-hub материал с identity `{type}:{slug}` и
  source owner `repository` либо `staff`.
- **ArticleRevision** — immutable локализованное содержимое Article с canonical
  content digest и provenance.
- **Active article set** — опубликованные RU/EN revision pointers, читаемые
  public API.
- **Repository snapshot** — полный детерминированный список опубликованных
  entries одного exact repository commit.
- **Source owner** — единственный authoring source, которому разрешено менять
  active revisions Article.

## Требования

- `REQ-5401`: Article identity равна `{type}:{slug}`, где type входит в
  `article`, `blog_post`, `changelog`, `release_notes`; одна identity имеет одного
  неизменяемого source owner и строгую пару locales `ru`/`en`.
- `REQ-5402`: ArticleRevision хранит локаль, title, description, published date,
  tags, Markdown body, digest всей canonical revision, source kind/ref/path,
  время создания и private reference актора при staff publication; изменение
  любого public поля создаёт новую revision.
- `REQ-5403`: Web build валидирует `apps/web/content/hub` действующими content
  rules и создаёт полный snapshot exact commit без обращения к сети, API или БД;
  snapshot и entries имеют canonical digests, а порядок файлов не влияет на них.
- `REQ-5404`: Production deploy после schema migration и readiness API, но до
  переключения нового web image, передаёт встроенный snapshot через
  аутентифицированную operation импорта repository; importer не читает checkout на host и
  не отправляет произвольный путь или URL.
- `REQ-5405`: Импорт repository сначала проверяет schema, digests, точный commit,
  уникальность и locale parity всего snapshot, затем одной транзакцией создаёт
  revisions и меняет только repository-owned active set; ошибка оставляет
  прежний set и generation без изменений.
- `REQ-5406`: Повтор active snapshot является no-op. Изменённая entry создаёт
  revisions и новую generation, новая entry активируется, отсутствующая entry
  снимается с публикации; history и staff-owned active set сохраняются.
- `REQ-5407`: Repository import отклоняет identity, уже принадлежащую `staff`, а
  staff operation отклоняет identity `repository`; приоритет источников и
  автоматическое перехватывание ownership запрещены.
- `REQ-5408`: Staff allowlist account публикует или снимает с публикации Article
  через authenticated API без web rebuild. Публикация принимает RU/EN пару одной
  транзакцией и проверяет ожидаемый active digest; устаревший expected digest получает
  conflict без частичного эффекта.
- `REQ-5409`: Public API возвращает единый active list и detail независимо от
  source owner, исключает drafts/unpublished/history/private actor и выдаёт
  происхождение repository только как безопасные факты точных commit/path.
- `REQ-5410`: При включённом `content_hub` web server получает index и detail из
  публичный content API и из той же revision строит metadata HTML, human body и
  machine document; потребители Atom и discovery не имеют отдельного filesystem
  fallback или второго merge.
- `REQ-5411`: Staff publication становится доступна без web rebuild после
  обновления public cache identity. Repository publication становится доступна
  только после успешного deploy import; новый web image не считается готовым до
  завершения этого импорта.
- `REQ-5412`: Смена active revision или unpublish ставит идемпотентный article
  event для `SPEC-053`; SEO failure не отменяет domain transaction и не меняет
  активный набор articles.
- `REQ-5413`: Импорт repository использует отдельный deployment credential
  ограниченной области; изменение staff разрешено только account из списка
  `allowlist`. Размеры тела request и Markdown ограничены contract; raw body и
  credentials не попадают в логи, метрики или ответы с ошибкой.
- `REQ-5414`: Import и staff mutation записывают AuditEvent с operation ID,
  вид источника, digest snapshot/revision, outcome и безопасные счётчики; публичный
  read остаётся anonymous и public-cacheable.

## Состояния и ошибки

Article имеет active либо unpublished состояние serving; history состоит из
immutable revisions. Repository import проходит `validated`, `applied`, `no_op`
или `rejected`; промежуточное состояние не становится public.

Stable errors: `AI_STP_CONTENT_INVALID`, `AI_STP_CONTENT_SOURCE_CONFLICT`,
`AI_STP_CONTENT_STALE`, `AI_STP_CONTENT_IMPORT_FORBIDDEN` и действующий
`AI_STP_NOT_FOUND`. Validation, permission и stale failures не меняют active
pointers, generation или SEO jobs.

## Безопасность и приватность

Repository content является ограниченным входом владельца repository, но проходит ту же
политику safe Markdown, что staff payload. Credential импорта имеет только право
заменять repository-owned snapshot и не даёт staff, account или catalog
полномочий. Staff actor ID доступен только private audit. Public API не возвращает
credential, внутреннее положение source на узле host, identity редактора, draft или rejected
body.

## Совместимость и миграция

Rollout выполняется expand/import/switch: добавить additive article storage и
API; импортировать текущий repository snapshot и сверить identities/digests;
перевести web reads с filesystem на API. До switch текущий web продолжает читать
Git, новый API не меняет public routes. После switch URL
`/{locale}/content/{type}/{slug}` сохраняются.

Rollback возвращает прежний web image и repository serving без удаления новых
таблиц. Повторный import snapshot предыдущего exact commit откатывает только
repository-owned active set; staff-owned entries сохраняются. Contract phase и
удаление filesystem read выполняются отдельным изменением после окна rollback.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-5401`–`REQ-5402` | Migration/storage test проверяет identity, source owner, locale pair, immutable revisions и digest изменения каждого public поля. |
| `REQ-5403` | Две сборки одного commit с разным порядком обхода создают byte-identical snapshot без сетевого обращения. |
| `REQ-5404` | Production scenario доказывает порядок migrate→API ready→import→web ready и отказ готовности web при failed import. |
| `REQ-5405`–`REQ-5406` | Platform test повторяет snapshot, меняет, добавляет и удаляет entry и проверяет atomic active set, generation и сохранённую history. |
| `REQ-5407` | Conflict matrix для repository/staff отклоняет оба направления takeover без изменения owner или active revision. |
| `REQ-5408` | ASGI test публикует RU/EN pair, отклоняет stale expected digest и снимает staff article с публикации. |
| `REQ-5409` | Public contract test объединяет repository/staff entries и доказывает redaction unpublished, history и private actor. |
| `REQ-5410` | Web test строит index/detail/human/machine/Atom из API fixture и не читает `content/hub` на request path. |
| `REQ-5411` | E2E публикует staff article без rebuild и видит её после смены cache identity; repository article появляется только после import. |
| `REQ-5412` | Integration test получает один SEO effect на новую active revision и сохраняет публикацию при отказе SEO worker. |
| `REQ-5413`–`REQ-5414` | Security test проверяет scoped credentials, limits, forbidden Markdown, redacted logs и AuditEvent без body/token. |
