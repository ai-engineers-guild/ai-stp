---
description: "План реализации plan-scoped upload байт публикации."
last_verified: "2026-08-16"
---

# Artifact bind: план реализации #312

Статус: выполнено. `#312` закрыт слиянием `#366` 2026-08-16, и ниже — план,
по которому это делалось, а не оставшаяся работа. Запись сохраняется как
нормативная трассировка требований к коду, который уже в основной линии.

## Нормативная база

Уже принято: `SPEC-026` `REQ-2627`, `docs/contracts/http-api.md`, `ADR-0093`.
Один маршрут - `PUT /v1/publications/plans/{plan_id}/artifact`. Съём с Git
не делается.

## Владельцы

- провод: `packages/contracts` OpenAPI `Operation` с
  `application/octet-stream` request;
- проверка и запись: `apps/platform` inspect +
  `ImmutableObjectStore.put_immutable`;
- HTTP: `apps/api` publish router/service;
- publish: `execute_publish` создаёт `ObjectLocation`;
- тесты: unit на inspect/bind/confirm-refuse; API при наличии БД.

`apps/cli/**` не меняется.

## Реализация

1. `inspect_publication_artifact` отклоняет размер выше
   `MAX_ARTIFACT_BYTES`, zip-пути с `..`/абсолютом, symlink и device/special
   file. Не-zip тело допускается как непрозрачный blob.
2. `bind_plan_artifact` сверяет digest/size с планом, пишет store, идемпотентна
   для тех же байт.
3. `confirm_plan` читает store по `plan.content_digest` и отказывает, если байт
   нет.
4. `execute_publish` после создания `CatalogMetadata` пишет `ObjectLocation`
   purpose `artifact`.
5. OpenAPI: расширить `Operation` для бинарного request body без JSON-модели.

## Тесты

- `test_inspect_publication_artifact_rejects_traversal_and_symlink`;
- `test_bind_plan_artifact_rejects_digest_mismatch`;
- `test_confirm_refuses_until_bytes_are_durable`;
- при БД: план, bind настоящих байт, confirm, анонимное чтение совпадает;
  второе тело под тем же `X.Y` отклоняется.

Digest в тесте считается `digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)`, не
литералом.

## Проверка

`uv run --locked pytest tests/unit/platform/test_publication_logic.py tests/unit/platform/test_publication_support.py -q`.
После OpenAPI: `just back-gen`.
