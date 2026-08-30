---
description: "Решение свести repository import и staff API к одному серверному потоку публикации статей."
last_verified: "2026-08-29"
---

# ADR-0132: Один серверный поток публикации статей для Git и API

Статус: принято.

## Контекст

Content hub читает repository Markdown непосредственно из web image. Новая или
изменённая статья поэтому требует сборки сайта, а server не имеет общей истории
ревизий, через которую можно безопасно добавить материал без изменения Git.

Платформа уже использует PostgreSQL, immutable revisions и публичный API. Новый
способ авторинга через staff API не должен создавать второй serving path: иначе
web, Atom, sitemap и machine-проекция будут самостоятельно объединять Git и БД,
разрешать коллизии и по-разному переживать отказ одного источника.

## Варианты

1. **Оставить Git в web и подмешивать DB entries на request.** Не требует
   миграции repository content, но создаёт два источника истины во всех public
   projections и отдельные правила кэша, удаления и конфликтов.
2. **Писать API-материалы обратно в Git.** Сохраняет один файловый источник, но
   публикация зависит от Git credentials, commit/push и нового web deploy.
3. **Импортировать Git snapshot в platform и читать все опубликованные статьи
   через API.** Принято: Git и staff API остаются двумя authoring sources, а
   platform становится единственным serving source.

## Решение

Стабильная `Article` принадлежит ровно одному source owner: `repository` или
`staff`. Оба источника создают immutable локализованные `ArticleRevision`, а
активные указатели выбирают опубликованные RU/EN revisions. Совпадение identity
`{type}:{slug}` у разных owners отклоняется и никогда не разрешается приоритетом
или last-write-wins.

Web-сборка валидирует `apps/web/content/hub` и создаёт детерминированный полный
снимок `snapshot` с точным коммитом репозитория, путями источников, digest содержимого и digest
всего snapshot. Сборка не обращается к API или PostgreSQL. При deploy одноразовый importer
после миграций и готовности API передаёт snapshot через отдельную
аутентифицированную operation. Platform атомарно заменяет только активный набор
источника `repository`; повторный snapshot идемпотентен, а отсутствующие entries снимаются с публикации без
удаления истории.

Staff-публикация использует отдельную API operation со списком разрешённых accounts и атомарно
публикует строгую RU/EN пару. Она не может изменить repository-owned identity.
Конкурентное изменение защищается ожидаемым active digest; account редактора
остаётся в private audit и не входит в public response.

Страницы content, индекс, Atom и human/machine projections читают только public
content API. Next.js server формирует HTML из той же опубликованной ревизии.
`content_hub` остаётся build-time feature по `ADR-0089`: выключенный web image не
обращается к content API и не публикует маршруты раздела.

Доменная публикация статьи не зависит от SEO materialization. Успешная смена
active revision ставит событие `SPEC-053`; последний SEO profile может догнать
новую статью асинхронно, не откатывая её публикацию.

## Последствия

- Git-статья меняется новым commit и deploy import; staff-статья — API-вызовом
  без пересборки web.
- PostgreSQL и public content API становятся обязательными для serving content
  hub; repository snapshot остаётся восстановимым источником только своих entries.
- Deploy получает one-shot import step и отдельный ограниченный credential; его
  отсутствие или отказ не меняют прежний active repository set.
- История revisions сохраняется при update, unpublish и удалении Git-файла.
- Web больше не объединяет filesystem и DB records и не определяет source
  precedence.
- Откат web возвращает предыдущий image; откат repository content повторно
  импортирует snapshot предыдущего exact commit. Staff revisions при этом не
  изменяются.

## Условия пересмотра

- Появляется третий authoring source, которому недостаточно того же snapshot или
  staff publication contract.
- Измеренная нагрузка делает обслуживание через API неприемлемым даже с действующим public
  cache boundary.
- Появляется редакторский workflow с ролями, согласованием или расписанием;
  тогда lifecycle CMS проектируется отдельно от текущей операции публикации.
