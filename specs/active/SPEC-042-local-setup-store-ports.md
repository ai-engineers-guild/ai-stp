---
description: "SPEC-042: Локальные versioned ports для контролируемого импорта SX и APM."
last_verified: "2026-08-31"
---

# SPEC-042: Local setup-store ports

## Цель

Агент может обнаружить и разобрать локальное состояние совместимого setup store,
увидеть точное преобразование и только после подтверждения зарегистрировать
доступные компоненты. Внешний store остаётся источником snapshot, но не получает
владение registry или итоговым состоянием харнесса.

## Границы

Port читает только `sx.toml` schema 2 или `apm.lock.yaml` версии 1/2 внутри явно
названного корня. Он не запускает SX/APM, не использует сеть и работает при
отсутствии vendor CLI. Import пишет только private local drafts; запись обратно
во внешний store или harness target отсутствует и потребовала бы отдельного
provider-плана.

## Термины

- **Store descriptor** — версия общего порта, adapter и точного snapshot manifest.
- **Mapping** — явное решение о каноническом виде или причина omission одной
  внешней записи.
- **Import key** — адресуемая по содержимому связь adapter, snapshot и external
  identity с уже созданным локальным объектом.

## Требования

- `REQ-4201`: Vendor-neutral `setup-store-port/1` разделяет discovery, inspect,
  content-addressed plan и digest-confirmed import; vendor schema не протекает в
  командный контракт.
- `REQ-4202`: Discovery и inspect не открывают local registry для записи, не
  исполняют vendor CLI и ограничивают manifest размером, количеством записей,
  уникальностью ключей и безопасным корнем.
- `REQ-4203`: SX adapter принимает schema 2 и явно сопоставляет `skill`, `rule`,
  `agent`, `command`, `mcp`, `hook`, `claude-code-plugin`, `app-plugin` с
  каноническими видами. Импортируется только существующий `source-path`;
  HTTP/Git source остаётся omission offline preview.
- `REQ-4204`: APM adapter принимает lock версии 1/2 и строит границы компонентов
  только из безопасных `deployed_files` известных native layouts. Exact version,
  source coordinate и доступный digest сохраняются как наблюдаемое provenance.
- `REQ-4205`: Неизвестный тип, поле, collection, небезопасный путь и
  недоступный source не угадываются. Неизвестные поля входят в bounded report,
  а непредставимая запись получает явную причину omission.
- `REQ-4206`: Plan показывает mapping, omissions, collisions и последствия для
  доверия. Digest связывает весь inspect report, content digest каждого
  доступного local path и отсутствие external/target writes с точными байтами
  manifest.
- `REQ-4207`: Import повторно строит plan и требует exact digest как
  подтверждение локальной записи, атомарно принимает фактические локальные bytes через component adoption и
  сохраняет ключ идемпотентности. Повтор одного snapshot возвращает прежние
  identifiers без новой ревизии.
- `REQ-4208`: Imported passports остаются private, local/imported и не получают
  `author_verified` или `component_verified`. Последующая публикация проходит
  обычное обогащение и validation без исключений для vendor metadata.

## Состояния и ошибки

Mapping имеет состояние `component` или `omitted`. Import возвращает `imported`
или `already_imported`. Collection и remote-only source остаются omission, а не
частичным объектом. Несовместимая версия, неоднозначный manifest, collision,
stale digest, небезопасный или исчезнувший путь дают типизированный отказ до
записи нового объекта.

## Безопасность и приватность

Чтение ограничено regular non-linked manifest и объявленными local paths внутри
root. Значения environment и credentials не читаются отдельно и не попадают в
conversion report. Импорт использует существующие ограничения component adoption
на secrets, объём и безопасный deterministic artifact. Все новые паспорта private.

## Совместимость и миграция

Точные прочитанные контракты закреплены на публичных исходниках SX и APM в
`docs/contracts/setup-store-ports.md`. Более новая несовместимая версия
отклоняется `AI_STP_SCHEMA_UNSUPPORTED`; добавление версии требует fixture,
mapping review и обновления этого SPEC. Наличие бинарника — диагностика, а не
предусловие offline snapshot.

## Критерии приёмки

| Требование | Исполнимое доказательство |
|---|---|
| `REQ-4201` | Строгие общие схемы и machine help описывают четыре отдельные команды. |
| `REQ-4202` | Тест сравнивает manifest и отсутствие registry до/после discovery и inspect; duplicate key и bounds отклоняются. |
| `REQ-4203` | SX fixture содержит importable path, неизвестный тип и collection с явными omissions. |
| `REQ-4204` | APM fixture сводит skill-directory и prompt-file в две точные canonical boundaries. |
| `REQ-4205` | Unknown top-level и dependency fields видны в report, неизвестный тип не импортируется. |
| `REQ-4206` | Изменение manifest или local component bytes меняет digest, а stale apply отказан до записи. |
| `REQ-4207` | Два apply одного плана создают один Component и возвращают `already_imported`. |
| `REQ-4208` | Passport validation не считает imported draft готовым или подтверждённым платформой. |
