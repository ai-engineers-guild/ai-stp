---
description: "Решение связать provider plan и применение с одними точными байтами HarnessBundle."
last_verified: "2026-08-09"
---

# ADR-0050: Точная привязка HarnessBundle к provider plan

Статус: принято.

## Контекст

`ADR-0049` сделал HarnessBundle настоящим каноническим ZIP с логической и
побайтовой идентичностью, но installation consumer продолжал вызывать
`apply-bundle` с digest внутреннего плана `ai_stp`. Он не передавал ZIP,
`validate-bundle` и `plan-bundle` не участвовали в установке, а provider plan
вообще не сохранялся. Пользователь мог подтвердить описание, не связанное с
байтами, которые должен получить единственный writer цели.

Хэш плана `ai_stp` и хэш provider plan отвечают на разные вопросы. Первый
идентифицирует решение пользователя вместе с release, target и сроком. Второй
идентифицирует программу изменений, которую построил владелец нативной цели.
Подмена одного другим не проверяет ни один из них.

## Решение

`install plan` компилирует полный `ai-stp-bundle/1`, атомарно сохраняет точные
ZIP-байты под их raw SHA-256 и передаёт один абсолютный content-addressed путь
последовательно в `validate-bundle` и `plan-bundle`. Оба вызова получают формат,
логический `bundle_digest`, raw `artifact_digest` и размер. `plan-bundle`
дополнительно получает текущий target digest.

Consumer принимает ответы только когда provider возвращает точные значения тех
же полей. Validation требует `valid=true`. Provider plan требует `state=planned`,
канонический `plan_digest`, тот же target digest и непустой перечень эффектов.

Immutable plan schema v5 связывает:

- `bundle_format`;
- `bundle_digest`;
- `bundle_artifact_digest`;
- `bundle_size`;
- `provider_plan_digest`.

Все пять полей входят в digest, который подтверждает пользователь. Локальный
абсолютный cache path не входит: он является производным расположением байтов,
может отличаться на другом устройстве и не является их идентичностью.

Перед `apply-bundle` consumer повторно хэширует cached artifact и проверяет его
размер. Provider получает те же bundle bindings, исходный target digest и exact
provider plan digest. Его ответ обязан повторить все привязки. Несовпадение после
вызова не называется обычным отказом: эффект уже мог произойти, поэтому операция
становится `partial`. `resume` не передаёт пакет и не повторяет apply; он вызывает
только `provider-info` и `status`.

## Совместимость

Набор команд protocol v1 не меняется, сетевые поля не добавляются и frozen
network semantics остаётся прежней. Это решение специфицирует ранее отсутствующий
обязательный argv/response contract уже объявленных `validate-bundle`,
`plan-bundle` и `apply-bundle`. Provider, который отвечал на имена команд, но не
принимал HarnessBundle, не был исполнимой реализацией installation contract.

Старые планы schema v1–v4 сохраняют исторический digest. Они могут быть осмотрены
и завершены observe-only recovery, но новый effect по ним не применяется:
отсутствующие exact bytes и provider plan нельзя восстановить догадкой.

## Последствия

Подтверждение пользователя, кэш байтов, проверка провайдера, его план и применение
теперь образуют одну проверяемую цепочку. Повторный `install plan` может
повторить read-only provider calls, но одинаковые ответы дают один idempotency key
и существующую операцию. Цена — один локальный cache artifact и более строгий
provider adapter; реальные Claude Code и Codex providers обязаны реализовать этот
wire contract до E2E.

## Условия пересмотра

Решение пересматривается при появлении потокового bundle protocol, при котором
provider не получает локальный путь. Новая транспортная форма обязана сохранить
обе идентичности, размер, provider plan digest и семантику `partial` после вызова.
