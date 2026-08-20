---
description: "SPEC-028: Авторский публичный профиль, безопасные аватары и предпросмотр."
last_verified: "2026-08-08"
---

# SPEC-028: Публичный профиль, media и предпросмотр

## Цель

Автор управляет самостоятельным публичным профилем, видит его до публикации и
может выбрать проверенный avatar из связанной Google/GitHub identity либо
загрузить собственный. Анонимный читатель видит только опубликованную ревизию;
черновик, identity и media-оригиналы не раскрываются.

## Границы

Входят: отдельный `PublicProfile`, черновые и опубликованные ревизии, owner-only
preview, name, plain-text bio, HTTPS links, avatar, API-опосредованная загрузка
в RustFS/S3, нормализация и проверка media, публичная publisher page.

Не входят: социальный граф, подписки, комментарии, произвольные поля профиля,
синхронизация содержимого паспорта разработчика, browser editor setup или
выдача доступа по profile link.

## Термины

- `PublicProfile` — самостоятельный авторский объект аккаунта, не паспорт.
- `ProfileRevision` — неизменяемый снимок профиля; один может быть опубликован.
- `ProfileDraft` — последняя неопубликованная ревизия владельца.
- `AvatarAsset` — обработанный вариант изображения, связанный с profile revision.
- `Public projection` — точная allowlist-проекция опубликованной ревизии.

## Требования

- `REQ-2801`: Один account имеет не более одного PublicProfile. Пустой
  опубликованный профиль отсутствует из public catalog, а не отображается пустой
  карточкой.
- `REQ-2802`: Поля profile revision строго ограничены `display_name` (1–80
  символов), `bio` (0–1500 символов ограниченного безопасного Markdown),
  `links` (0–8 уникальных нормализованных HTTPS URL с label 1–60 символов) и
  `avatar_asset_id` или отсутствующим avatar. Bio не принимает HTML или
  небезопасные URI.
- `REQ-2803`: Пользовательский web-flow не показывает отдельный черновик:
  `Save changes` сохраняет изменения и делает их текущим опубликованным
  профилем через серверную ревизию. Preview в форме является временным
  frontend-only состоянием и не создаёт backend draft.
- `REQ-2804`: `GET` owner-profile, создание/обновление draft, preview и publish
  являются отдельными contract-first API scenarios. Все mutations требуют
  ключ идемпотентности; публикация возвращает идентификатор операции. Веб не
  синтезирует профиль из account или OAuth claims.
- `REQ-2805`: Owner preview использует тот же renderer и public projection, что
  анонимная publisher page, но доступен только владельцу. Preview явно маркирует
  draft/published state и никогда не индексируется, не получает public cache и
  не выдаёт URL, работающий анонимно.
- `REQ-2806`: Пользователь может выбрать avatar только из связанных identities,
  которые сервер уже прочитал в OAuth flow, либо создать собственный AvatarAsset.
  Provider URL не становится публичным avatar URL: сервер получает разрешённый
  источник, создаёт нормализованный asset и сохраняет его в object storage.
- `REQ-2807`: Собственный upload идёт через API с allowlist `image/jpeg`,
  `image/png`, `image/webp`; сервер ограничивает размер до 5 MiB и декодируемые
  пиксели, убирает metadata/EXIF, преобразует к ограниченному набору размеров и
  ставит asset в quarantine до успешной проверки. Неуспешный, неподдерживаемый
  или слишком большой файл никогда не становится доступен публично.
- `REQ-2808`: Для URL из OAuth применяются provider allowlist, HTTPS, redirect
  limit, лимиты bytes/pixels и защита от SSRF. Клиент не передаёт произвольный
  remote URL как источник загрузки.
- `REQ-2809`: Маршрут публичного профиля возвращает только account id,
  опубликованные поля профиля, безопасный адрес обработанного avatar и
  опубликованные объекты. Он не раскрывает linked identity, email, source URL,
  ключ объекта, draft, asset original или состояние проверки.
- `REQ-2810`: Form показывает field-level validation до submit и canonical API
  errors после submit; links нормализуются сервером, дубликаты и не-HTTPS URL
  отклоняются. Удаление avatar и всех fields — явное действие с preview.

## Состояния и ошибки

Profile бывает `absent`, `draft`, `published` или `asset_processing`; asset —
`processing`, `ready`, `rejected`, `deleted`. Конфликт revision даёт
`AI_STP_PRECONDITION_FAILED`; неверное поле — `AI_STP_VALIDATION_ERROR`;
чужой profile/asset — неразличимый `AI_STP_NOT_FOUND`; media dependency failure
— `AI_STP_DEPENDENCY_UNAVAILABLE`. Повтор publish с тем же ключом возвращает
первичный outcome.

## Безопасность и приватность

PublicProfile отделён от DeveloperPassport по ADR-0023. Исходные байты,
карантин и object keys не публичны. Разбор media ограничен ресурсами; публичный
  рендерер экранирует биографию и метки ссылок. Аудит фиксирует участника, digest ревизии и
operation id, но не OAuth URL, исходные байты или EXIF.

## Совместимость и миграция

Текущие seed profiles мигрируются в published ProfileRevision. До появления
public profile API маршрут `/publishers/[account]` не может выдавать fixture как
производственную истину. Новые OpenAPI models и routes аддитивны; generated client
пересобирается только из контракта.

## Критерии приёмки

| Требование | Исполнимый oracle |
|---|---|
| `REQ-2801` | Интеграционная проверка доказывает, что account получает не более одного PublicProfile и пустой профиль не попадает в каталог. |
| `REQ-2802` | Контрактные проверки принимают безопасный Markdown bio до 1500 символов и отвергают HTML, небезопасные URI, не-HTTPS links, лимиты и дубликаты. |
| `REQ-2803` | Web-проверка доказывает, что preview в форме не пишет backend, а Save changes публикует текущие поля. |
| `REQ-2804` | Контрактная матрица проверяет раздельные сценарии owner-profile, draft, preview и publish с idempotency key. |
| `REQ-2805` | Браузерная проверка сравнивает sanitized preview и public rendering и доказывает owner-only access. |
| `REQ-2806`–`REQ-2808` | Проверки хранилища покрывают provider import, upload, EXIF strip, limits, SSRF и quarantine. |
| `REQ-2807` | Проверки upload покрывают allowlist image MIME, размер, пиксели, очистку EXIF и quarantine. |
| `REQ-2809` | Проверка редактирования доступа доказывает отсутствие identity, email, source URL и object key. |
| `REQ-2810` | RU/EN доступные form tests покрывают validation, delete и conflict recovery. |
