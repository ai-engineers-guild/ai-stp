---
description: "Решение хранить публичный профиль ревизиями и изолировать его media/preview."
last_verified: "2026-08-08"
---

# ADR-0069: Ревизии публичного профиля, media и preview

Статус: принято.

## Контекст

ADR-0023 отделил PublicProfile от DeveloperPassport, но текущий API не имеет
сценария чтения и записи профиля, страница издателя опирается на фикстуры, а
OAuth avatar живёт только у связанной identity. Нужны черновой предпросмотр,
собственный avatar и отсутствие утечки provider identity/media originals.

## Варианты

1. Производить profile из account/OAuth claims. Быстро, но нарушает ADR-0023 и
   меняет public page без явного решения автора.
2. Хранить одну mutable публичную запись. Меньше таблиц, но preview не имеет
   стабильной основы, а audit/rollback не воспроизводимы.
3. Хранить immutable profile revisions с draft/publish lifecycle и отдельными
   processed media assets.

## Решение

Принимается вариант 3 по SPEC-028. Public profile имеет owner-scoped draft,
одну published revision и content digest. Preview строится из той же sanitized
projection, что public route, но authorization не позволяет ему стать public
URL. Avatar никогда не является provider URL: выбранный OAuth image или owner
upload проходит server-side normalisation/quarantine и сохраняется в RustFS/S3
как ограниченный processed asset.

## Последствия

- Нужны profile/media tables, owner/public API scenarios, migrations, audit,
  generated client и redaction tests.
- Upload API ограничен avatar media; artifact object-store semantics не
  расширяются молча.
- Publish требует ETag, idempotency, preview confirmation и recheck digest.
- Существующие начальные profiles мигрируют в revisions; fixture projection
  нельзя оставлять производственной реализацией.

## Условия пересмотра

Решение пересматривается, если profile станет совместным объектом организации,
появятся non-image media или потребуется юридически обязательное profile review.
