---
description: "План реализации проверки Ed25519 авторского подтверждения."
last_verified: "2026-08-16"
---

# Attestation verify: план реализации #300

Статус: выполнено. `#300` закрыт слиянием `#366` 2026-08-16, и ниже — план,
по которому это делалось, а не оставшаяся работа. Запись сохраняется как
нормативная трассировка требований к коду, который уже в основной линии.

## Нормативная база

Уже принято: `SPEC-026` `REQ-2605`, `docs/contracts/validation-policy.md`,
`ADR-0092`. Единственный payload - закрытая запись
`ai_stp_assurance.AuthorAttestation`. Сервер не восстанавливает поля.

## Владельцы

- провод: `packages/contracts` `AuthorAttestation`, затем `just back-gen`;
- проверка: `apps/platform/.../publication_logic.py::bind_author_attestations`;
- ключ устройства: уже в `Device.public_key`, сверка как в
  `ai_stp_api.slices.devices.crypto.verify_ed25519`;
- digest: `attestation_digest` из assurance;
- тесты: `tests/unit/platform/test_publication_*.py`, при наличии базы -
  `tests/api/platform/test_publication_grants_reports.py`.

`apps/cli/commands/publication.py` только перестаёт урезать уже подписанную
запись: иначе репозиторий не типизируется после смены провода. Новой CLI-логики
подписания нет.

## Реализация

1. Проводная модель получает те же поля и `SIGNATURE_PATTERN`, что assurance.
   `created_at` на attestation больше нет.
2. `bind_author_attestations` принимает каноническую запись, публичный ключ
   активного устройства, координаты плана (digest, subject, policy, account,
   device). Сверяет координаты, запрещает секретные имена инструментов,
   проверяет Ed25519 над `attestation_digest.encode("utf-8")`.
3. `"s" * 16` не проходит схему и не проходит bind.
4. Отозванное устройство отсекается до bind вызывающим кодом, как и сейчас
   на device-bound путях.

## Тесты

- `test_bind_author_attestation_accepts_device_signed_record`;
- `test_bind_author_attestation_rejects_sixteen_s_signature`;
- `test_bind_author_attestation_rejects_revoked_or_foreign_device`;
- `test_bind_author_attestation_rejects_shifted_digest`.

Подпись в тесте ставит настоящий Ed25519, не копия алгоритма bind. Ожидаемый
digest берётся из `attestation_digest`.

## Проверка

`uv run --locked pytest tests/unit/platform/test_publication_support.py tests/unit/platform/test_publication_logic.py tests/unit/test_attestation.py -q`.
После смены провода: `just back-gen`.
