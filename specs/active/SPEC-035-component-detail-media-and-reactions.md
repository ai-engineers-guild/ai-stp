---
description: "Сгруппированная страница компонента, media-галерея автора и reactions."
last_verified: "2026-08-17"
---

# SPEC-035: Страница компонента, media и reactions

## Цель

Публичная страница компонента должна быстро отвечать, что это, кто автор, где
исходник, как использовать объект и как менялись версии. Автор может оформить
галерею, не расширяя паспорт версии и не раскрывая внутренности object storage.

## Границы

Спецификация охватывает публичную detail-страницу компонента, отдельные media-
метаданные компонента, безопасную выдачу media, aggregate likes компонентов и
сетапов и переход в
существующий report flow. Редактор паспортов, публичные комментарии, произвольные
embed и раскрытие списка отреагировавших аккаунтов не входят.

## Термины

- `Media item` — упорядоченная запись галереи с одним допустимым источником.
- `Preview item` — единственный media-элемент, используемый как обложка компонента.
- `Reaction` — приватная idempotent связь account с component или setup; публична
  только сумма.
- `Storage asset` — проверенный объект, выдаваемый через ограниченную публичную проекцию.

## Требования

- `REQ-3501`: Первый экран содержит имя, текущую версию, метки доверия и
  поддержки, число лайков, источник GitHub и действия копирования, лайка и жалобы.
- `REQ-3502`: Факт показывается ровно в одном смысловом разделе; технические
  метаданные не повторяют первый экран, поддержку или совместимость.
- `REQ-3503`: Страница показывает публичную карточку автора и отдельную историю
  всех доступных версий с датой, жизненным циклом и ссылкой на неизменяемую версию.
- `REQ-3504`: Автор может сохранить до пяти упорядоченных media-элементов и выбрать
  ровно один элемент предпросмотра при непустой галерее.
- `REQ-3505`: Media-элемент имеет один источник: загрузку, закреплённый raw-файл
  GitHub или video ID YouTube. Произвольный HTML/embed запрещён.
- `REQ-3506`: Upload принимает JPEG, PNG, WebP, GIF, MP4 или WebM до 25 MiB.
  Worker проверяет MIME/magic bytes, resource bounds и удаляет audio tracks у
  видео до публикации.
- `REQ-3507`: GitHub source использует HTTPS, allowlisted GitHub host, exact
  commit SHA и прямой путь файла. Fetch защищён от SSRF и redirect escape.
- `REQ-3508`: Public projection не содержит object key, quarantine URL или
  исходный upload URL. Storage assets выдаются через короткоживущую подпись.
- `REQ-3509`: Превью в галерее не запускает видео и не показывает controls.
  Lightbox содержит native/custom controls; autoplay только если lightbox открыт,
  элемент активен и документ/секция видимы. Смена слайда, закрытие, скрытая
  вкладка и выход из viewport останавливают воспроизведение. Reduced motion и
  ограничения браузера соблюдаются (`muted`, `playsInline`).
- `REQ-3510`: Like является idempotent authenticated reaction account/object,
  а public API показывает только неотрицательный aggregate `likes_count`.
- `REQ-3511`: Report action ведёт в существующий preview-first закрытый report
  flow и не создаёт публичный GitHub issue.
- `REQ-3512`: RU/EN, keyboard navigation, reduced motion, mobile layout и
  подписи внешних/storage links покрываются web tests.
- `REQ-3513`: Аутентифицированный владелец компонента может из owner workspace
  и публичной detail-страницы изменить только catalog bio и media. Паспорт,
  digest, имя, тип, теги, source и версии этой операцией не меняются; чужой
  `stable_id` отвечает неразличимым `AI_STP_NOT_FOUND`.
- `REQ-3514`: Аутентифицированный пользователь видит собственные reactions на
  отдельной странице, может перейти к ней из меню аккаунта и удалить reaction
  повторным действием на detail-странице. Список не раскрывает reactions других
  аккаунтов.

## Состояния и ошибки

Media проходит состояния `pending`, `ready`, `rejected` и `deleted`; публичная
проекция возвращает только `ready`. Ошибки различают недопустимый источник,
формат, размер, нарушение preview-инварианта, отказ проверки и недоступность
хранилища. Повторный like не увеличивает aggregate сверх одной реакции аккаунта.

## Безопасность и приватность

Upload считается недоверенным до проверки MIME и magic bytes. GitHub fetch
разрешён только с allowlisted host и exact commit, с повторной проверкой каждого
redirect и защитой от SSRF. Object keys, quarantine URLs, исходные upload URLs,
account IDs реакций и внутренние причины модерации не входят в public projection.
Произвольные HTML, scripts, embed и audio tracks запрещены.

## Совместимость и миграция

Паспорта и неизменяемые версии объектов не меняются: `media` и `reactions` хранятся
как отдельные платформенные записи. При rollback новые таблицы и UI отключаются,
а существующая `component detail route`, `report flow` и публичная проекция без `media`
остаются работоспособными. Старые компоненты отображаются с пустой галереей и
нулевым `likes_count`.

## Критерии приёмки

| Требование | Исполнимый oracle |
| --- | --- |
| `REQ-3501` | Component/E2E test находит имя, версию, метки, aggregate, source и три действия. |
| `REQ-3502` | Component test подтверждает единственное отображение каждого факта по semantic section. |
| `REQ-3503` | Component/E2E test находит карточку автора и ссылки каждой версии timeline. |
| `REQ-3504` | Contract/API tests отклоняют шестой элемент и нарушение единственного preview. |
| `REQ-3505` | Contract tests принимают три разрешённых source variant и отклоняют смешанный источник/embed. |
| `REQ-3506` | Worker tests проверяют allowlist форматов, границу 25 MiB, magic bytes, bounds и удаление audio. |
| `REQ-3507` | Adapter tests отклоняют не-HTTPS, чужой host, branch ref, private address и redirect escape. |
| `REQ-3508` | Projection tests доказывают redaction внутренних полей и ограниченный срок storage URL. |
| `REQ-3509` | Browser/component test проверяет отсутствие autoplay у превью, controls и autoplay только в активном lightbox, стрелки клавиатуры, focus trap и закрытие Escape. |
| `REQ-3510` | API scenario повторяет like одного account и наблюдает aggregate без account IDs. |
| `REQ-3511` | E2E test проходит preview-first report route без создания публичного issue. |
| `REQ-3512` | Locale parity, a11y и desktop/mobile browser tests проходят для detail и gallery. |
| `REQ-3513` | API test меняет bio/media владельца, проверяет неизменность паспорта и отклоняет чужой account. |
| `REQ-3514` | API test проверяет idempotent like, приватный список и unlike; web test покрывает страницу и ссылку меню. |
