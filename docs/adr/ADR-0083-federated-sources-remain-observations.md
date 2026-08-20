---
description: "Решение разделить local ports и metadata adapters общим descriptor без передачи им доверия или target."
last_verified: "2026-08-13"
---

# ADR-0083: Федеративные источники остаются внешними наблюдениями

Статус: принято.

## Контекст

SX/APM предоставляют локальные setup-store snapshots, а GitHub и каталоги
экосистемы — удалённые metadata. Если назвать их одним marketplace, исчезают
различия между локальными байтами, внешним заявлением, паспортом ASTP и правом
изменить харнесс. Слияние по имени дополнительно допускает source takeover.

## Решение

Принимается общий versioned `federated-source/1`, но с разными kind:
`local_port` и `metadata_adapter`. Descriptor всегда является
`external_observation`, не повышает оси verification и запрещает target write.
Local port может лишь подготовить отдельный подтверждённый import private draft;
metadata adapter остаётся read-only.

Identity совпадает только по provider и exact external identifier. Один объект
может иметь несколько references, но похожие названия и metadata не создают
auto-merge. Паспорт ASTP остаётся единственным владельцем нормативных данных.

## Последствия

Новый источник получает собственный bounded parser, attribution, TTL/error
политику и conformance fixture. Состояния `stale` и `unavailable` не ломают
основной registry. Популярность не становится trust score. Итоговый target
по-прежнему пишет только публичный provider харнесса.

## Условия пересмотра

Решение пересматривается при появлении криптографически проверяемой внешней
authority, нового вида источника или безопасного протокола межпровайдерной identity.
