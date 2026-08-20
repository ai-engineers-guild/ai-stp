---
description: "План реализации курсора последней непустой страницы sync pull."
last_verified: "2026-08-16"
---

# Sync last-page cursor: план реализации #302

Статус: выполнено. `#302` закрыт слиянием `#366` 2026-08-16, и ниже — план,
по которому это делалось, а не оставшаяся работа. Запись сохраняется как
нормативная трассировка требований к коду, который уже в основной линии.

## Нормативная база

Уже принято: `SPEC-025` `REQ-2504`, `docs/contracts/sync-event.md`,
`ADR-0091`. Правило last-page `null` в `docs/contracts/http-api.md` остаётся
для каталога и списков объектов.

## Владельцы

- сервис: `apps/api/src/ai_stp_api/slices/sync/service.py::pull_events`;
- курсор: `apps/api/src/ai_stp_api/slices/sync/cursor.py`;
- фикстура: `packages/contracts/src/ai_stp_contracts/fixtures/v1/sync.json`;
- тесты: `tests/unit/platform/test_sync_cursor.py`,
  `tests/api/platform/test_sync_ledger.py`;
- комментарий `PageInfo` в `packages/contracts` не должен утверждать, что
  last-page `null` относится к sync pull.

`apps/cli/**` и `tests/unit/test_cli_sync_transport.py` не трогать.

## Реализация

1. Непустая страница всегда кодирует курсор последней выданной
   последовательности, даже когда `has_more` ложно.
2. Пустая страница повторяет входной курсор либо возвращает `null`, если
   входного не было.
3. Подпись, account-binding и отказ подделки не меняются.
4. Фикстура `pullSyncEvents.oneEvent` показывает ненулевой курсор формы
   `CURSOR_PATTERN`. `pullSyncEvents.emptyStream` остаётся с `null`.
5. После правки фикстуры: `just back-gen`, чтобы OpenAPI-пример совпал с
   корпусом.

## Тесты

- `test_pull_one_event_returns_cursor_on_last_page`;
- `test_pull_saved_cursor_immediately_returns_empty_page`;
- `test_pull_saved_cursor_after_append_returns_only_new_event`;
- существующие отказ подделки и чужого account остаются красными, если
  проверка пропадёт.

Без базы: unit на `pull_events` с подставленной сессией недопустим, если он
копирует SQL. Тогда узкий unit на правило выбора курсора из уже прочитанных
строк плюс API-тест при `AI_STP_TEST_DB_URL`. Если URL нет, skip честно
фиксируется.

## Проверка

`uv run --locked pytest tests/unit/platform/test_sync_cursor.py tests/api/platform/test_sync_ledger.py -q`.
`just back-gen` после правки фикстуры; `just back-static` подтверждает
паритет схем.
