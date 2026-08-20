---
description: "Проводная семантика публичных detail view и artifact download counters."
last_verified: "2026-08-17"
---

# Catalog usage metrics

При включённом feature публичные component card/detail/version responses получают
nullable `usage_metrics` с неотрицательными `detail_views_count` и
`artifact_downloads_count`. Все поверхности читают aggregate `stable_id`;
отсутствие означает выключенный feature или недоступное значение, а не ноль.

Просмотр detail — успешный публичный ответ. Загрузка артефакта — успешная выдача
bytes после проверок доступа и целостности. HEAD, preflight, ошибка, незавершённый
stream и получение download URL не считаются. Download не является install success.

Dedup key строится из action, `stable_id`, окна и keyed digest минимального сетевого
признака. Raw IP, user-agent, account/device id и cross-window digest не хранятся.
Окно, срок хранения и ротация секрета задаются серверной конфигурацией; public API не
возвращает events или unique-user estimate.

Default anti-abuse window — `1 h`, retention dedup rows — `25 h`, rotation secret
— каждые `24 h` с перекрытием текущего окна. Значения bounded server configuration:
окно `5 min..24 h`, retention не меньше окна и не больше `7 d`, rotation не реже
срока хранения. Изменение defaults требует проверки приватности и граничных тестов.

## Эксплуатация

API включает сбор через `AI_STP_CATALOG_USAGE_ENABLED`; Web показывает aggregate
только при одновременном build-time feature
`AI_STP_FEATURE_CATALOG_USAGE_METRICS`. Параметры API:

- `AI_STP_CATALOG_USAGE_SECRET` — обязательный секрет keyed digest при включении;
- `AI_STP_CATALOG_USAGE_WINDOW_SECONDS` — окно dedup;
- `AI_STP_CATALOG_USAGE_RETENTION_SECONDS` — срок хранения dedup rows;
- `AI_STP_CATALOG_USAGE_SECRET_ROTATION_SECONDS` — период ротации.

Секрет ротируется с перекрытием активного окна: прежнее значение сохраняется до
истечения окна, затем удаляется. Cleanup удаляет только dedup rows старше retention;
aggregate не уменьшается. Если конфигурация невалидна, API не стартует. Для rollback
сначала выключают Web feature, затем `AI_STP_CATALOG_USAGE_ENABLED`; публичная
проекция становится nullable/отсутствующей, накопленные aggregate не удаляются.
