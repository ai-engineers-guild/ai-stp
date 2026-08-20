---
description: "Решение считать публичное использование через короткоживущую дедупликацию без пользовательской аналитики."
last_verified: "2026-08-16"
---

# ADR-0097: Публичные usage counters без пользовательского трекинга

Статус: принято.

## Контекст

Каталогу нужны сопоставимые просмотры detail и загрузки artifacts, но стабильный
visitor identifier создаёт историю поведения, а browser analytics требует
согласия. Download также не доказывает успешную установку provider.

## Решение

Platform считает успешный публичный ответ detail и успешную выдачу байтов артефакта.
Повторы подавляются в коротком окне keyed digest, который нельзя связать между
окнами; raw network и account/device identifiers не сохраняются. Dedup rows имеют
короткий retention, публична только сумма.

Это necessary anti-abuse, не optional analytics. Feature flag одновременно
отключает запись и projection. Download не используется как install success,
verification, trust или eligibility.

## Последствия

Aggregate приблизителен и не равен числу уникальных людей. Card, detail и API
читают одну проекцию. PostgreSQL обеспечивает unique dedup key и транзакционный
increment; browser fingerprint и analytics vendor не нужны.

## Условия пересмотра

Решение пересматривается для аналитики когорт с согласием, `provider install receipt`
или иного юридического срока хранения.
