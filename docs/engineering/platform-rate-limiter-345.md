---
description: "План реализации вытеснения ключей HTTP rate limiter."
last_verified: "2026-08-16"
---

# Rate limiter: план реализации #345

Статус: выполнено. `#345` закрыт слиянием `#366` 2026-08-16, и ниже — план,
по которому это делалось, а не оставшаяся работа. Запись сохраняется как
нормативная трассировка требований к коду, который уже в основной линии.

## Нормативная база

Уже принято: `SPEC-010` `REQ-1015`, раздел «Ограничение частоты» в
`docs/contracts/http-api.md`. Отдельный ADR не нужен: это дефект политики
одного узла, а не смена источника истины или публичного контракта.

## Владельцы

- код: `apps/api/src/ai_stp_api/rate_limit.py`, вызов в `app.py`;
- тесты: `tests/unit/platform/test_production_operations.py`, узкий API-тест
  в `tests/api/platform/test_health_system.py`;
- правило теста: `docs/engineering/testing.md`.

CLI, Redis и распределённый лимитер не входят.

## Реализация

1. `SlidingWindowLimiter.allow` вытесняет ключ с пустым окном. При наборе
   `max_keys` и новом ключе вытесняется LRU, а не общая корзина `overflow`.
   Часы по-прежнему инжектируются аргументом `now`.
2. Ключ middleware: метод + шаблон совпавшего маршрута + адрес клиента.
   `BaseHTTPMiddleware` выполняется до `scope["route"]`, поэтому шаблон
   снимается сопоставлением `request.app.router.routes`. Несовпавший путь
   не несёт конкретный URL: иначе пробы 404 раздувают таблицу.
3. Существующий
   `test_sliding_window_limiter_bounds_origin_key_churn` удаляется: он
   закрепляет дефект.

## Тесты

Имена ломают заявленное поведение, если оно пропадёт:

- `test_sliding_window_limiter_admits_unrelated_key_past_max_keys`;
- `test_sliding_window_limiter_releases_idle_key_after_window`;
- `test_rate_limit_key_uses_route_template_not_concrete_path`.

Тесты вызывают настоящий `SlidingWindowLimiter` и middleware, без копии
алгоритма в тесте.

## Проверка

`uv run --locked pytest tests/unit/platform/test_production_operations.py tests/api/platform/test_health_system.py -q`.
Генераторы не нужны: схема не меняется.
