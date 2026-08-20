---
description: "Изменяемое представление компонента в каталоге без изменения паспорта версии."
last_verified: "2026-08-10"
---

# Представление компонента

Catalog presentation принадлежит владельцу компонента и хранится отдельно от
неизменяемого паспорта. Изменение presentation не создаёт версию и не меняет
`passport_document`, `passport_digest`, `name`, `component_type`, `tags`,
`source` или publication state.

## Owner API

- `GET /v1/owner/objects/component/{stable_id}/presentation` возвращает текущее
  представление только владельцу;
- `PUT /v1/owner/objects/component/{stable_id}/presentation` атомарно заменяет
  `bio` и весь упорядоченный список `media`;
- `POST /v1/owner/objects/component/{stable_id}/presentation/media` принимает
  binary upload автора и возвращает ready public path `/v1/media/component/{id}`;
- `GET /v1/media/component/{media_id}` отдаёт ready bytes без object key;
- отсутствие объекта и обращение чужого аккаунта дают одинаковый `404`;
- cookie-authenticated mutating routes требуют double-submit CSRF.

Запрос имеет `schema_version: 1`, `bio` длиной до 2000 символов и не более пяти
`media`-элементов. Элемент содержит `kind`, `url`, обязательный `alt` и
необязательный `caption`. Для `youtube` поле `url` содержит 11-символьный video
ID. Для `image` и `video` разрешены:

- upload path `/v1/media/component/{media_id}` после owner upload;
- HTTPS URL `raw.githubusercontent.com`, закреплённый на точный commit.

Upload allowlist: JPEG, PNG, WebP, GIF, MP4, WebM до 25 MiB (REQ-3506).
Произвольные embed, HTML и внешние hosts запрещены.

Публичная catalog projection использует `bio`, если владелец его сохранил, и
иначе возвращает `description` текущего паспорта. Публичная media projection
по-прежнему содержит только элементы в состоянии `ready`.
