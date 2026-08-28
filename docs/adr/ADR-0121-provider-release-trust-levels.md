---
description: "Решение различать verified publisher, подписанный, build-attested и непроверенный выпуск провайдера."
last_verified: "2026-08-24"
---

# ADR-0121: Четыре уровня доверия к выпуску провайдера

Статус: принято. Расширяет `ADR-0011`.

## Контекст

Публичные setup-system провайдеры выпускаются без общего привилегированного ключа, но GitHub связывает artifact attestation с exact bytes, репозиторием, commit и workflow. Существующий boolean `provider_release_trusted` не различает это доказательство, подпись разрешённым ключом и отдельно проверенного платформой издателя.

## Решение

Вводится закрытый уровень `verified_publisher`, `signed`, `build_attested` или `unverified`.

`signed` означает проверенную подпись exact manifest и bytes ключом локальной политики. `build_attested` означает проверенную Sigstore/GitHub attestation exact bytes с repository, source commit и signer workflow локальной политики. `verified_publisher` является надстройкой над одним из этих двух доказательств и требует, чтобы издатель был заранее закреплён в локальной политике как verified.

Уровни не суммируются и выбирается самый сильный применимый. Галочка издателя без проверенных bytes не создаёт доверия. Manifest, attestation predicate, удалённый профиль и downloaded policy не расширяют локальный allowlist.

`provider_release_trusted` сохраняется как совместимая производная: `false` только для `unverified`. Новые решения используют уровень и его evidence.

## Последствия

- build attestation становится самостоятельным якорем доверия с обязательной привязкой к exact workflow и commit;
- verified publisher виден как более сильный уровень, но не обходит проверку supply chain;
- install plan связывает уровень и evidence, поэтому изменение доказательства требует нового подтверждения;
- старые закрепления прежнего эстейта удаляются как вытесненные; семь действующих setup-system разрешаются только отдельными build-attestation rules;
- offline verification требует заранее полученные bundle и trusted roots; их отсутствие не считается успехом.

## Условия пересмотра

Решение пересматривается при смене GitHub OIDC/Sigstore identity contract, появлении platform-owned release transparency log или необходимости сравнивать несколько независимых build attestations одного артефакта.
