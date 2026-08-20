---
description: "SPEC-044: GitHub archived state как локальное evidence устаревания."
last_verified: "2026-08-13"
---

# SPEC-044: GitHub archive evidence

## Цель

Для точной локальной версии с публичным GitHub source CLI получает официальный
`archived` state репозитория и сохраняет его как датированное внешнее evidence.
Сигнал предупреждает об устаревании, но сам не меняет lifecycle, eligibility,
опубликованные байты или установленный target.

## Границы

Первая реализация — machine CLI и локальный registry. Публичная catalog/detail
проекция принадлежит platform/web. Поддерживается только `github.com` и официальный
REST endpoint. Первая версия не принимает GitHub credential и запрашивает только
public metadata; private repository получает неразличимый `unavailable`.

## Термины

- **Observation** — неизменяемая строка одного ответа GitHub с временем и TTL.
- **Repository identity** — числовой GitHub repository id, переживающий rename и
  transfer.
- **Proposal** — механическое предложение lifecycle без автоматического эффекта.
- **Freshness** — сравнение времени чтения со сроком сохранённого observation.

## Требования

- `REQ-4401`: Refresh принимает точные `stable_id` и `X.Y`, читает source из
  сохранённого immutable passport и отказывает для local, отсутствующего,
  credentialed или не-GitHub source.
- `REQ-4402`: Успешное наблюдение сохраняет immutable GitHub repository id,
  canonical `full_name`, исходную coordinate, `archived`, `fetched_at`, TTL и
  необязательный ETag. Redirect, rename и transfer принимаются только из
  официального ответа с тем же repository id после первого наблюдения.
- `REQ-4403`: `archived=true` возвращает только предложение `deprecated` и
  предупреждение. Он никогда не создаёт `blocked`, не меняет lifecycle, bytes,
  паспорт, выбор, установку или target и не выполняет замену.
- `REQ-4404`: Каждое изменившееся наблюдение добавляется в append-only history.
  `unarchive` не стирает прежний archived факт; повторный `304` обновляет freshness
  отдельным observation без выдуманного изменения состояния.
- `REQ-4405`: Offline show использует последнее наблюдение и помечает его `fresh`
  либо `stale`. Отсутствие evidence имеет состояние `unavailable`; 404, 403,
  ограничение частоты, неверный ответ и транспортный отказ не превращаются в
  deprecation и не уничтожают сохранённое evidence.
- `REQ-4406`: Refresh использует conditional GET, закрытый response model,
  ограниченный размер ответа и не более одного запроса. Credential не принимается,
  не читается из окружения и не появляется в registry либо ответе.
- `REQ-4407`: Machine CLI использует общие строгие схемы для refresh/show/history;
  history ограничена, упорядочена и содержит attribution и freshness.

## Состояния и ошибки

Evidence имеет `fresh`, `stale` или `unavailable`; repository state — `active`,
`archived` или `unavailable`; proposal — `none` либо `deprecated`. Ошибка сети
возвращает типизированный отказ и не заменяет последний хороший снимок.

## Безопасность и приватность

Запрос строится только из проверенного публичного source passport. Redirect
не следует автоматически. Ответ ограничен по размеру и проходит строгую схему.
Первая версия намеренно не имеет credential surface.

## Совместимость и миграция

SQLite получает append-only observation table. Существующие версии не меняются;
без refresh их ответ честно `unavailable`. Новые provider hosts и lifecycle
автоматизация требуют отдельного решения.

## Критерии приёмки

| Требование | Исполнимое доказательство |
|---|---|
| `REQ-4401` | Fixtures точной версии принимают GitHub source и отклоняют local/unknown coordinate до HTTP. |
| `REQ-4402` | Mock отвечает rename/transfer с тем же id и collision с другим id; сохраняются точные coordinates. |
| `REQ-4403` | Archived fixture возвращает proposal без изменений version, selection, installation и target. |
| `REQ-4404` | Archived → unarchived → 304 остаются тремя упорядоченными observations. |
| `REQ-4405` | Clock-controlled tests различают fresh/stale, а 404/rate-limit/outage сохраняют прежний снимок. |
| `REQ-4406` | Transport test фиксирует conditional header, один запрос, bounded body и отсутствие credential surface. |
| `REQ-4407` | Registry, generated schemas и machine help объявляют один evidence refresh и две read-only команды. |
