---
description: "SPEC-031: Публичные документы, версионированные политики и error pages."
last_verified: "2026-08-08"
---

# SPEC-031: Документы, политики и error pages

## Цель

Сайт даёт отдельный полезный для людей и агентов раздел документации, а также
локализованные юридические и сервисные документы. Тексты имеют версию, язык,
provenance и отдельные public API/pages; техническая документация импортируется
из закреплённого repository source, а не копируется вручную в web. Публичный
пользовательский source живёт в `user-docs/`; внутренний `docs/` остаётся
нормативным контуром репозитория.

## Границы

Входят: docs portal, Markdown import/render, public document API, policy
revision storage, privacy/cookie/service/licensing policies, 404 и global 500
pages. Не входят: свободный CMS для пользователей, browser Git authoring,
юридическая консультация, acceptance workflow или arbitrary remote Markdown.

## Термины

- `PublicDocument` — документ с stable slug, kind и language.
- `DocumentRevision` — immutable локализованная revision с digest и source.
- `Technical source` — allowlisted repository path и exact commit, из которого
  CI импортирует документацию.
- `Policy` — public document kind с lifecycle `draft`/`published`/`superseded`.

## Требования

- `REQ-3101`: Public docs nav содержит обзор продукта, CLI/agent quickstart,
  catalog guide, setup/component guide, trust/security guide,
  troubleshooting и docs for authors.
  Каждая страница указывает revision источника, время обновления и язык; agent paths
  имеют компактный machine-readable index без скрытого содержимого prompt.
- `REQ-3102`: Technical docs получают source только из allowlisted repository,
  путь и exact commit в CI import scenario. Web/API не получает необработанное содержимое Git
  по пользовательскому URL или во время request path.
- `REQ-3103`: Policy kinds включают `privacy`, `cookies`, `service_rules` и
  `author_content_and_license`. Последняя ясно отделяет лицензию платформы от
  авторского content, запрещает незаконный/вредоносный upload и не обещает
  платформенную проверку безопасности content.
- `REQ-3104`: PublicDocument и DocumentRevision хранят slug, kind, locale,
  source type/ref/path, content digest, Markdown source, renderer version,
  lifecycle, published_at и supersession link. Изменение published text создаёт
  новую revision; старый published URL остаётся доступен с указанием successor.
- `REQ-3105`: API возвращает только published revision запрошенной locale или
  явно объявленный fallback. Draft/pending policy, editor identity, internal
  review and source credentials не попадают в public API/cache.
- `REQ-3106`: Markdown documents используют renderer/policy из SPEC-029.
  Технические docs и policies имеют оглавление, стабильные якоря заголовков,
  copy link, print-friendly view и доступную иерархию заголовков.
- `REQ-3107`: `/[locale]/not-found` — полноценная 404 page с переходами к
  каталогу, документации и home. Root `global-error` — минимальная 500 page,
  не раскрывающая error message/stack, с retry, request/correlation reference
  при наличии и safe support/docs links. Обе доступны без session.
- `REQ-3108`: Site footer ссылается на current published policy revisions и
  Страница лицензирования. Ссылки видимы на публичных и авторизованных поверхностях; locale
  parity и archive history сохраняются.

## Состояния и ошибки

Неизвестный public slug и unavailable locale не раскрывают существование draft и дают
404. Ошибка render/import оставляет прежнюю published revision и создаёт
наблюдаемый результат оператора; public read при dependency failure возвращает
безопасное состояние unavailable. Страница 500 никогда не serializes server exception.

## Безопасность и приватность

Текст policy не содержит secrets, данных внутренних инцидентов или personal data.
Импорт репозитория проверяет разрешённый список, закрепление коммита, обход пути и digest.
Кэш public docs инвалидируется только после atomic publish; пользовательский
Markdown не присоединяется к корпусу документации platform.

## Совместимость и миграция

Repository `user-docs/**` становится canonical public technical source;
`docs/**` остаётся canonical internal normative source. Импортированная ревизия
не заменяет исходный checkout. Таблицы policy и public APIs добавляются
аддитивно. Никакое обязательное согласие с новой policy не вводится без
отдельного ADR и product decision.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-3101`–`REQ-3102` | CI import test доказывает exact commit/path/digest и agent index. |
| `REQ-3103`–`REQ-3105` | Contract/storage tests доказывают locale, immutable revisions, fallback и redaction drafts. |
| `REQ-3104` | Проверка хранения доказывает неизменяемость revision, digest, source ref и supersession link. |
| `REQ-3106` | Markdown/a11y snapshots проверяют ToC, anchors и renderer policy. |
| `REQ-3107` | Browser tests доказывают locale 404, root 500, retry и отсутствие stack data. |
| `REQ-3108` | Route test проверяет footer links на published policy revisions в RU/EN. |
