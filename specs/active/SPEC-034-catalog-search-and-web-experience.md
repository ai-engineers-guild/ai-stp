---
description: "SPEC-034: Сильный поиск каталога, компактный web UX и медиа профиля."
last_verified: "2026-08-17"
---

# SPEC-034: Поиск каталога и web experience

## Цель

Публичный каталог даёт компактный двуязычный интерфейс, строгий структурный
поиск и предсказуемую пагинацию, а landing, страницы объектов и профиль
используют одну доступную дизайн-систему и надёжный media flow.

## Границы

Входят landing и shell, каталог компонентов и сетапов, язык запросов, фильтры,
сортировка, card/list presentation, счётчики web-пагинации, страницы объекта,
публичный профиль, загрузка аватара и безопасный Markdown. CLI сохраняет режим cursor.
Browser editor сетапов и произвольный HTML не входят.

## Термины

- `Catalog QL` — ограниченный язык логических выражений над разрешёнными полями.
- `Page mode` — web-пагинация с номером страницы и точным total для текущего
  публичного среза.
- `Cursor mode` — стабильная keyset-пагинация без раскрытия total.
- `Refinement surface` — responsive оболочка поиска, фильтров, сортировки и
  выбора представления; спецификация задаёт поведение и доступность, а не
  конкретный виджет.
- `Verified only` — одновременно `author_verified=true` и
  `component_verified=true`; одна ось не заменяет другую.

## Требования

- `REQ-3401`: Авторизованный landing не показывает `Sign in`; header не
  показывает sign-out action и использует icon profile menu. Навигация имеет
  локализованные keyboard-доступные tooltips.
- `REQ-3402`: Landing hero использует большой brand mark, канонический слоган и
  autoplay-muted-loop preview с poster/fallback и reduced-motion режимом.
- `REQ-3403`: App shell удерживает footer у нижнего края короткой страницы и не
  перекрывает содержимое длинной страницы.
- `REQ-3404`: Search toolbar по умолчанию свёрнут до одной кнопки; состояние
  раскрывается без потери URL query и не занимает постоянную крупную область.
- `REQ-3405`: Resource, tags, harnesses, component types и authors являются
  searchable multiselect filters. `Verified only` и последний
  `Include experimental` являются checkbox. Каждый фильтр имеет отдельную
  доступную справку.
- `REQ-3406`: Structured refinement открывается по запросу в responsive
  refinement surface. На desktop допустимы inline/docked/attached panel, если
  результаты остаются доступны без перезагрузки. На узком экране surface
  является ограниченной модальной поверхностью с явным `Close`, закрытием по
  `Escape` и backdrop, удержанием фокуса и возвратом фокуса. Surface использует
  те же searchable multiselect, диапазон дат, сортировку и выбор представления,
  показывает `Reset all`, `Apply`, chips активных значений, validation errors и
  help.
- `REQ-3407`: Сортировка отделена от filters и поддерживает `relevance`,
  `updated_at` и `likes`, а направление `asc` / `desc` применяется сервером до
  page boundary. Направление входит в подпись cursor-запроса, чтобы продолжение
  нельзя было применить к другой сортировке. Каждая сортировка имеет стабильный tie-breaker;
  разворот только текущей страницы на клиенте запрещён.
- `REQ-3408`: Catalog QL поддерживает обычный текст, поля `NAME`, `TAGS`,
  `HARNESS`, `TYPE`, `AUTHOR`, `VERIFIED`, операторы `AND`, `OR`, `NOT`, `IN`,
  `NOT IN`, `:` и скобки. Backend является окончательной границей валидации;
  frontend возвращает совместимую раннюю ошибку с позицией. Autocomplete и
  простая correction являются opt-in/contextual assist и не переписывают
  plain-text query в reserved keywords без явного выбора пользователя.
- `REQ-3409`: Parser строит bounded typed AST и никогда не интерполирует input в
  SQL. Ограничены длина, число токенов, глубина и размер `IN`.
- `REQ-3410`: Web page mode возвращает `total_items`, `total_pages`, текущую
  страницу и bounded navigation: края, текущую окрестность и gaps, а не все
  страницы как отдельные controls. Cursor mode остаётся opaque и не смешивается
  с page mode.
- `REQ-3411`: Результаты имеют card/list view. Вся запись кликабельна, автор имеет
  отдельную ссылку, информация не дублируется, изображение зависит от object/type.
- `REQ-3412`: Страница объекта имеет компактную шапку, кнопку назад и иконку типа,
  локализованные даты и responsive metadata layout без чрезмерных отступов.
- `REQ-3413`: Account показывает `Edit profile` и `View public profile`; avatar
  проходит загрузку, проверку, объектное хранилище, привязку к черновику, публикацию и
  refresh, а оригинал не становится публичным.
- `REQ-3414`: Safe Markdown поддерживает headings, GFM tables, Unicode emoji и
  annotated inline links, запрещая raw HTML и опасные URL schemes.
- `REQ-3415`: Все видимые строки, состояния, tooltips, accessible names, даты и
  ошибки landing/catalog/detail/account имеют полный паритет `ru`/`en`.
- `REQ-3416`: Интерактивные элементы имеют semantic selectors; `data-testid`
  используется только когда role/name недостаточны.
- `REQ-3417`: Anonymous catalog читает только неотрицательный агрегат
  `likes_count`; сортировка по нему стабильна. Запись отдельных reactions и
  раскрытие account IDs не входят в эту спецификацию.
- `REQ-3418`: Web хранит исчерпывающий presentation registry видов компонентов:
  стабильный идентификатор, простую различимую иконку и локализованное имя.
  Registry не является доменным источником истины. При появлении управляемых
  типов метаданные переносятся в PostgreSQL, а версии изображений — в S3-compatible
  object storage по `ADR-0074`.
- `REQ-3419`: Страница объекта и точной версии показывает `View Source` только для
  допустимого GitHub origin и ведёт на закреплённые `commit + subpath`, а не на
  подвижную ветку или непроверенный внешний URL.
- `REQ-3420`: Кнопка share на странице объекта передаёт native Web Share API
  канонический URL точной версии и копирует тот же URL в clipboard, если API
  недоступен или завершился технической ошибкой.
- `REQ-3421`: Detail page структурированно показывает требования точной версии:
  имена и назначение env без значений, необходимость credentials/authorization,
  заявленные permissions и external endpoints; setup показывает агрегат паспорта.
- `REQ-3422`: Catalog read использует текущее account-level `author_verified`, а
  карточка показывает его кольцом avatar и check marker независимо от проверки content.
- `REQ-3423`: GitHub stars читаются из отдельного mutable cache по provenance
  repository, обновляются worker через ETag и bounded backoff, скрываются при
  отсутствии значения и никогда не влияют на trust.
- `REQ-3424`: Web получает явный consent `accept/reject/manage` для analytics и
  marketing, хранит выбор first-party cookie, а optional integrations остаются
  выключены до согласия; necessary cookies не отключаются.
- `REQ-3425`: Внешние продукты и сервисы являются изменяемыми метаданными
  представления, дедуплицируются по регистрируемому домену, имеют основной URL
  `HTTPS` глубиной не более одного сегмента, список стран `ISO 3166-1 alpha-2`
  из закреплённого в коде справочника и связь многие-ко-многим с версиями
  каталога. IP literals, userinfo и credentials запрещены; query и fragment
  удаляются. Создание сервиса и attach/detach доступны только owner Web API,
  CLI passport их не принимает. Public Web предоставляет `/services/{domain}`
  и `/countries/{code}`; весь раздел отключается feature flag без удаления данных.
  Публичный обзор стран и сервисов отличает выбранное состояние, показывает
  страну не только кодом ISO и даёт переход в каталог с уже применёнными
  фильтрами. Сентинел `unspecified` зависит от facet: service facet означает
  объект без связанного сервиса, country facet — объект со связанным сервисом
  без страны; между service/country facets действует `AND`, внутри facet — `OR`.
- `REQ-3426`: Карточка компонента и сетапа в list и cards сохраняет читаемый
  заголовок и область действий: профиль автора не вытесняет название и меню.
  Автор остаётся отдельной ссылкой с avatar и `author_verified`, если он есть.
  `likes_count` виден в обоих представлениях; GitHub stars только если значение
  доступно. Отсутствующая метрика не показывается как ноль. В центре —
  относительный итог security checks; `warning`, `failed` и `not-run` остаются
  видимыми. Если есть данные о риске, карточка добавляет короткую причину
  открыть запись и не смешивает метку автора с безопасностью содержимого.
- `REQ-3427`: `VerifiedAvatar` — единственный компонент метки автора: тонкая
  круглая обводка, маленькая галочка у нижнего края, без перекрытия фото или
  запасного знака, без изменения высоты строки, без сдвига имени и без
  локальных отрицательных смещений. Каталог, страница объекта и публичный
  профиль используют тот же компонент для фото и запасного знака.
- `REQ-3428`: Вертикальное меню трёх точек карточки содержит Copy URL, Copy ID,
  Copy CLI command, разделитель и Report component либо Report setup. Есть
  clipboard feedback, клавиатурное управление, закрытие по Escape и возврат
  фокуса. Основные действия карточки не дублируются. Report открывает
  существующий поток жалобы.
- `REQ-3429`: Поиск каталога принимает необязательные `updated_from` и
  `updated_to` как календарные даты `YYYY-MM-DD`. Допустимы один или оба края,
  очистка диапазона, chip каждого активного края, Reset all, сохранение в URL и
  client navigation без полной перезагрузки. Семантика UTC принадлежит
  `docs/contracts/http-api.md`: нижняя граница — начало указанного дня, верхняя —
  начало следующего дня; обратный диапазон — `AI_STP_VALIDATION_ERROR`. Подпись
  курсора включает заданные даты; пустые границы не входят в подпись, поэтому
  старые URL остаются действительными. Component и setup используют один
  контракт.
- `REQ-3430`: Каталог имеет явный режим Both/All наряду с `components` и
  `setups`. В Both используется один непрерывный список без отдельных секций:
  сначала идут setups, затем components; внутри каждого типа сохраняется
  выбранная сортировка. Тип различается внутри самой строки. Старые значения
  `resource=components` и `resource=setups` не ломаются. Web запрашивает две
  независимые проекции и сохраняет их page-границы в URL, но не превращает их в
  две визуально независимые выдачи. Пока остаются setup-страницы, component rows
  не опережают их; первая component page присоединяется к последней setup page,
  последующие component pages продолжают тот же список без повтора setups.
  Фильтры применяются только к
  соответствующему типу объекта.

## Состояния и ошибки

Ошибки QL содержат стабильный код, позицию и ожидаемый класс токена. Недопустимый
filter/sort/page отклоняется, а не игнорируется. Несовместимые `cursor` и `page`
дают ошибку проверки. Загрузка различает неподдерживаемый формат, превышение размера,
обработку, отказ хранилища и готовность. UI сохраняет применённый URL при сетевой ошибке.

## Безопасность и приватность

Search работает только по публичной проекции и не раскрывает hidden/private
count. `total_items` относится только к уже разрешённому публичному срезу.
QL компилируется только из allowlisted AST. Avatar проверяется по MIME и bytes;
оригинал приватен. Markdown sanitization запрещает raw HTML, scriptable URL и
event handlers. Like не раскрывает список account IDs.

## Совместимость и миграция

Существующие маршруты компонента и сетапа, а также параметры курсора
сохраняются. Режим страницы добавляется явно и не меняет семантику ответа
курсора. Старые одиночные фильтры принимаются как список из одного значения и
нормализуются вместе с list-параметрами до поиска и подписи курсора. Значение
`resource=both` принимается как общий режим. URL без `updated_from` и
`updated_to` сохраняют прежнюю выдачу. Откат отключает режим страницы, язык
запросов и флаги лайков без изменения опубликованных паспортов.

## Критерии приёмки

| Требование | Исполнимый oracle                                                                                |
| ---------- | ------------------------------------------------------------------------------------------------ |
| `REQ-3401` | Компонентная проверка различает анонимную и авторизованную шапку.                                |
| `REQ-3402` | Браузерная проверка видит логотип, слоган и autoplay preview.                                    |
| `REQ-3403` | Проверка двух высот viewport подтверждает положение footer.                                      |
| `REQ-3404` | Компонентная проверка подтверждает свёрнутый поиск и раскрытие кнопкой.                          |
| `REQ-3405` | Компонентная проверка покрывает все типы фильтров и справку.                                     |
| `REQ-3406` | Component/a11y tests подтверждают responsive refinement surface, одинаковые controls, reset/apply, close, focus containment на narrow и сохранение URL без full reload; `mobile-public-smoke.spec.ts` подтверждает keyboard/focus refinement на 360 и 430 px в `ru` и `en`. |
| `REQ-3407` | API unit test подтверждает стабильную сортировку трёх режимов.                                   |
| `REQ-3408` | Parser tests покрывают все поля, операторы и позиции ошибок; component tests — opt-in autocomplete/correction без переписывания plain text. |
| `REQ-3409` | Property tests проверяют границы длины, токенов, глубины и IN.                                   |
| `REQ-3410` | API tests проверяют totals и несовместимость page с cursor; component tests — bounded page window и отсутствие unbounded DOM controls. |
| `REQ-3411` | Компонентные проверки покрывают card/list и ссылки автора.                                       |
| `REQ-3412` | Браузерная проверка подтверждает компактную responsive detail page; `mobile-public-smoke.spec.ts` подтверждает 360/430 px в `ru`/`en` без document-level overflow и с видимыми install/view CTA. |
| `REQ-3413` | Сценарий выполняет upload → draft → publish → public read.                                       |
| `REQ-3414` | Golden/XSS tests покрывают таблицы, заголовки, emoji и ссылки.                                   |
| `REQ-3415` | i18n parity и locale E2E проходят для изменённых страниц.                                        |
| `REQ-3416` | Проверка доступности находит controls по role и name.                                            |
| `REQ-3417` | Projection/API tests доказывают публичный агрегат и стабильную сортировку.                       |
| `REQ-3418` | Component test проходит по всем contract component types и находит icon и локализации `ru`/`en`. |
| `REQ-3419` | Unit tests проверяют exact commit/subpath и отклоняют подвижные или подменённые URL.             |
| `REQ-3420` | Component test проверяет native share точного version-scoped URL и clipboard fallback.           |
| `REQ-3421` | Component test проверяет структурированные требования и отсутствие значений секретов.            |
| `REQ-3422` | Platform unit test проверяет current-state overlay, component test — независимый avatar marker.  |
| `REQ-3423` | Worker unit tests проверяют URL, ETag/cache; card test отделяет stars от trust.                  |
| `REQ-3424` | Unit/component tests проверяют persistence, reject и отсутствие optional consent по умолчанию.   |
| `REQ-3425` | Unit/API tests проверяют URL policy, domain conflict, owner-only mutation, country roof с objects, два значения `unspecified`, `AND` между facets и `OR` внутри facet; migration tests — M:N schema; component test — выбранное состояние, отличие страны от голого кода и catalog CTA с фильтрами. |
| `REQ-3426` | Component tests покрывают card/list, author вне title/action, likes в обоих видах, доступные stars, отсутствие ложного нуля, why-open и видимые warning/failed/not-run. |
| `REQ-3427` | Component test проверяет обводку, галочку у края, фото и placeholder, неизменный размер строки и отсутствие отрицательных offsets. |
| `REQ-3428` | Component test проверяет состав меню, clipboard, Escape, клавиатуру, возврат фокуса и раздельные названия Report. |
| `REQ-3429` | Parser/API tests покрывают один край, полный диапазон, обратный диапазон, UTC-границы и подпись курсора; web test — chip, reset и URL. |
| `REQ-3430` | Component/unit tests подтверждают один список, порядок setups затем components, отсутствие групповых секций, независимую сортировку типов, старые resource values и bounded page-границы. |
