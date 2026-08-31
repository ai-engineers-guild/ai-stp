---
description: "Модель угроз федеративных local ports и metadata adapters."
last_verified: "2026-08-31"
---

# Модель угроз федеративных источников

## Защищаемые границы

Канонический паспорт, обе оси verification, неизменяемые artifact bytes и local
registry и итоговый target не принадлежат внешнему источнику. Local port читает
только явно названный snapshot; metadata adapter возвращает только allowlist
наблюдений. Установка проходит обычный selection/compiler/provider lifecycle.

## Угрозы и механические ответы

| Угроза | Ответ |
|---|---|
| Poisoned metadata | closed schema, bounded body/records, безопасный parser, отсутствие исполнения и копирования artifact bytes |
| Identity collision | совпадение только exact provider/external id; другое имя или URL не создаёт merge |
| Source takeover | immutable external id закрепляется первым наблюдением; смена identity закрывается conflict |
| Stale либо outage | датированный snapshot помечается stale/unavailable и не удаляет паспорт или другой reference |
| Подмена доверия популярностью | descriptor механически фиксирует обе verification-оси false и authority external observation |
| Запись чужого состояния | target write всегда false; local import требует exact digest как подтверждение и создаёт только private draft |
| Утечка локальных данных | descriptor исключает path, secret, environment value, content и device identity |
| Dependency capture | SX, APM и remote catalogs остаются optional adapters, а не runtime dependencies core |

## Остаточный риск

Attribution и freshness позволяют потребителю оценить наблюдение, но не доказывают
истинность внешнего текста. Условия использования, ограничения частоты и производственная загрузка каждого
удалённого каталога проверяются до включения. Производственное включение
остаётся закрытым, пока не сохранены attribution, адрес условий использования
и разрешающий допуск политики. Нормативное требование принадлежит
`SPEC-050` `REQ-5007`.
