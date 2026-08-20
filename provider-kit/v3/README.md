# Public provider conformance kit v3

Этот каталог является порождённым переносимым контрактом provider protocol v3.
Публичный provider может проверять свою реализацию по этим JSON-файлам без доступа к
закрытым репозиториям `ai_stp` или `nddev-harnesses` и без зависимости от них во время
исполнения.

- `manifest.json` фиксирует команды, operations, native vocabularies, provenance и
  network phases.
- `provider-info.schema.json` является закрытой JSON Schema ответа `provider-info`.
- `conformance-cases.json` перечисляет обязательные fail-closed классы.
- `SHA256SUMS` привязывает точные bytes остальных артефактов.
- `KIT-IDENTITY.json` называет ровно одну ревизию комплекта: агрегатный digest
  от канонических байт `SHA256SUMS` плюс `kit_version`. Закреплять следует
  агрегат — он неподделываем; `kit_version` является читаемой меткой, и версия
  `0.1.0` неоднозначна и ссылкой быть не может (`ADR-0085`).

Файлы создаются `python release_scripts/provider_kit.py provider-kit/v3` и
проверяются той же командой с `--check`. Редактировать generated JSON вручную нельзя.
