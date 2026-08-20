---
description: "SPEC-043: Локальные отчёты бюджета контекста, capability delta и blast radius."
last_verified: "2026-08-15"
---

# SPEC-043: Selection impact reports

## Цель

До выбора или обновления точного `SetupVersion` агент может механически показать
изменение контекста и доступов, а для точного `ComponentVersion` — локальные
объекты, которых касается update или lifecycle-событие. Отчёт ничего не выбирает,
не меняет eligibility и не выполняет установку, обновление либо удаление.

## Границы

Первая реализация — локальный machine CLI и общий контракт. Персональный
baseline/delta и blast radius остаются локальными: Web не проецирует account
blast radius и не выводит установленную основу, угаданную сервером (`SPEC-049`).
Детерминированный estimator — одна shared-реализация для CLI и server; Web
получает только абсолютный budget видимой exact setup. Локальный ответ не
изображает полноту аккаунта. Отчёт не является проверкой eligibility, не
выбирает сетап и не пишет target.

## Термины

- **Estimator profile** — версия единицы и детерминированного метода подсчёта.
- **Price profile** — явно предоставленный снимок цены с источником и сроком.
- **Blast radius** — точные обратные ссылки в названной границе полномочий.
- **Freshness** — происхождение и момент снимка, а не обещание глобальной полноты.

## Требования

- `REQ-4301`: Versioned estimator работает только над проверенными локальными
  artifact bytes. Профиль `ai-stp:utf8-bytes/1` точно считает UTF-8 bytes как
  собственные единицы; `ai-stp:unicode-chars-div4/1` детерминированно оценивает
  tokens как округлённое вверх число Unicode codepoints, делённое на четыре.
- `REQ-4302`: В бюджет входят текстовые `instruction`, `skill`, `agent` и
  `command`. `instruction` считается always-loaded, остальные три вида —
  conditionally-loaded. Нечитаемый UTF-8 помечается `unavailable`, а не нулём.
- `REQ-4303`: Отчёт выбора содержит абсолютный бюджет и снимок возможностей
  кандидата; при точной основе — её абсолютные значения и знаковую разницу.
  Поверхность возможностей перечисляет tools, MCP servers, hooks, внешние точки,
  требования учётных данных и три категории permissions без общего risk score.
  Основа задаётся явно либо выводится для проекта сначала из последней проверенной
  установки, затем из текущего выбора; источник остаётся видимым в ответе.
- `REQ-4304`: Цена появляется только из явно переданного строгого price profile с
  model, source, `fetched_at` и `expires_at`. Просроченный профиль помечается
  `stale` и не выдаёт amount; отсутствие цены не влияет на eligibility.
- `REQ-4305`: Запрос blast radius ищет точные обратные ссылки только внутри
  локального registry: версии сетапов, выбранные проекты, проверенные установленные
  цели и локальное устройство. Граница полномочий и freshness возвращаются явно.
- `REQ-4306`: Сценарии `update`, `deprecation`, `blocked`, `expired_evidence` и
  `advisory` имеют одно read-only поведение. `action=none` запрещает трактовать
  отчёт как автоматическое обновление или удаление.
- `REQ-4307`: Missing component, неверный passport digest, повреждённые bytes или
  неполный exact setup graph закрывают весь отчёт типизированным отказом.
- `REQ-4308`: Machine CLI и другие потребители используют одни строгие shared
  schemas `SelectionImpactReport` и `BlastRadiusReport`; private bytes никогда не
  отправляются во внешний tokenizer или API. Server/Web не публикуют
  `BlastRadiusReport` и account blast-radius resource.

## Состояния и ошибки

Измерение имеет состояние `exact`, `estimated` или `unavailable`; цена —
`available`, `stale` или `unavailable`. Неподдерживаемый профиль и неполная пара
основы дают ошибку проверки. Несовпадение точного digest, отсутствующая ссылка
или повреждённый artifact дают conflict до формирования ответа.

## Безопасность и приватность

Estimator не имеет сетевого транспорта. Price profile содержит только публичную
ставку и ссылку на источник, но не ключ API. Blast radius не читает иной registry,
не раскрывает content bytes и сообщает только локальные identifiers, уже доступные
владельцу файла registry.

## Совместимость и миграция

Добавление estimator, валюты, состояния или поля отчёта требует новой версии
контракта и обновления shared schema. Таблицы SQLite не меняются: обратные ссылки
вычисляются из существующих неизменяемых версий, выборов и журнала операций.

## Критерии приёмки

| Требование | Исполнимое доказательство |
|---|---|
| `REQ-4301` | Unit tests фиксируют оба estimator profile и повторяемый результат. |
| `REQ-4302` | Текстовый и нечитаемый artifact различаются как measured и unavailable. |
| `REQ-4303` | Shared-component fixtures проверяют absolute values и signed delta. |
| `REQ-4304` | Отсутствующий и stale price profile не возвращают amount. |
| `REQ-4305` | Reverse-reference test возвращает несколько setup и не выходит за local registry. |
| `REQ-4306` | Machine help объявляет read-only команды, а schema фиксирует `action=none`. |
| `REQ-4307` | Изменённый exact digest отказывает без частичного отчёта. |
| `REQ-4308` | Schema generation и command registry ссылаются на одни модели contracts. |
