---
description: "Машинный контракт локального бюджета контекста, capability delta и blast radius."
last_verified: "2026-08-15"
---

# Selection impact

## Команды и граница

`select impact` читает точный сетап-кандидат и необязательную точную основу из
локального registry. `select blast-radius` читает обратные ссылки на exact
component. Обе команды имеют mutability `read`, возвращают
`freshness=local_snapshot`, не используют сеть и не меняют selection, lifecycle,
operation или target.

Параметры команд принадлежат генерируемому `help --agent`, а поля ответов —
схемам `cli-selection-impact-report` и `cli-blast-radius-report`; здесь они не
дублируются.

Основа может быть названа точной парой идентификатора и версии. Если вместо неё
назван проект, CLI сначала использует последний проверенный установленный сетап
этого проекта и харнесса, а при его отсутствии — текущий выбранный сетап. Поле
`baseline_source` различает эти случаи; отсутствие обоих источников оставляет
разницу недоступной, не выдумывая нулевую основу.

## Измерение контекста

Estimator — отдельный версионированный контракт. Точный byte-профиль полезен для
воспроизводимой верхней границы собственной единицы, но не заявляет совпадение с
tokenizer модели. Профиль codepoints/4 всегда называется оценкой. Оба работают
локально и не передают private content наружу.

В отчёте always-loaded и conditionally-loaded разделены. Для baseline возвращается
signed delta: отрицательное число означает уменьшение. Binary/не-UTF-8 содержимое
имеет статус `unavailable`; отсутствие измерения не подменяется нулевой оценкой.

## Цена и capabilities

Price profile передаётся отдельным JSON-файлом и связывается с estimator profile.
Он содержит цену input tokens за миллион, валюту USD, model, HTTPS source,
`fetched_at` и `expires_at`. Без файла стоимость недоступна; после `expires_at`
она stale и amount отсутствует. Price profile не является входом eligibility.

Capability snapshot и delta сохраняют конкретные добавленные и удалённые native
IDs, endpoints, component coordinates с credential requirements и permissions.
Единого score нет: разные последствия нельзя скрывать одним числом.

## Blast radius

Обратный индекс вычисляется из проверенных локальных setup passports, active
активного выбора и журнала проверенных операций. Он не утверждает полноту аккаунта или организации:
`authority_boundary=local_registry` ограничивает смысл ответа текущим файлом
registry и его device. Все lifecycle-сценарии только называют затронутые ссылки;
`action=none` исключает автоматический update/uninstall.

## Server account projection

Локальный v1 контракт не меняется. `GET /v1/selection/blast-radius` снят:
blast radius остаётся CLI-only (`SPEC-049`). Web показывает абсолютный
context budget видимой exact setup в правом рельсе карточки после Author и
перед установкой CLI и Version history: свёрнутый итог и вложенную команду
`select impact` отдельно от блока установки CLI. Web не
показывает account blast radius и не установленную основу, угаданную сервером.
