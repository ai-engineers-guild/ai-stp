---
description: "Обязательная актуализация документации вместе с поведением, схемами и эксплуатацией."
last_verified: "2026-08-03"
---

# Актуализация документации

Документация является частью изменения, а не последующей задачей. PR, который меняет поведение, контракт, схему, конфигурацию, зависимость, команду, provider, migration, deployment или recovery, одновременно обновляет всех канонических владельцев затронутой информации.

## Матрица обновления

| Изменение | Обязательные владельцы |
|---|---|
| Пользовательское поведение или scope | `docs/product/`, active spec, README при необходимости |
| Доменный объект или invariant | `docs/architecture/domain-model.md`, contract/schema, active spec |
| CLI/API/wire format | `docs/contracts/`, schema/OpenAPI, compatibility и tests |
| Хранилище или migration | `SPEC-009`, migration plan, rollback и runbook |
| Provider contract или pin | `docs/contracts/provider-protocol.md`, `docs/operations/provider-integration-state.md`, release evidence и cross-repo issue |
| Security/privacy | `SECURITY.md`, `SPEC-013` и negative tests |
| Команда разработки или dependency | QUICKSTART, engineering docs, lock и CI |
| Failure/recovery path | operation contract, observability и runbook |

## Правила

- один нормативный факт имеет одного канонического владельца;
- остальные документы ссылаются на владельца, а не копируют большой блок;
- `index.md` сохраняется в каждом долгоживущем разделе и обновляется генератором;
- `last_verified` меняется только после фактической проверки содержимого;
- `last_verified` берётся по UTC, а не по локальному времени: восточнее нулевого меридиана локальная дата опережает UTC на несколько часов в сутки, и такая дата проходит локально, но отклоняется в CI как будущая;
- активная спецификация обновляется до реализации либо заменяется новой версией;
- принятое архитектурное решение не переписывается задним числом: создаётся новый ADR;
- устаревшая команда удаляется из всех примеров в том же PR;
- generated output не правится отдельно от source;
- `just gen` и `just check` запускаются после последней правки документации.

## Completion gate

PR не готов, пока итоговый diff не подтверждает согласованность кода, tests, schemas, документации, runbooks, generated indexes и release notes по затронутому поведению. Если документ не нужно менять, PR body кратко объясняет почему.
