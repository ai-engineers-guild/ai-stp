---
description: "Как отличать provider build/conformance от exact real-product lifecycle."
last_verified: "2026-08-31"
---

# Evidence выпущенных provider systems

Нормативные требования принадлежат `SPEC-008`, форма release gate —
`release-evidence.md`. Этот runbook не закрепляет текущий tag.

## Два последовательных среза

`just evidence-providers <tag>` загружает exact release assets семи systems,
проверяет attestation/policy, provider-info, vendored provider-kit schemas,
conformance и достижимость projection routes. Это доказательство контракта и
байтов, но не mutation target.

Real-product lifecycle выполняется отдельно через установленный `ai-stp` и
exact fetched manifests:

```text
provider fetch
→ plan
→ apply
→ status/backups
→ replace/update
→ recovery/rollback/remove
```

Каждый вызов использует одноразовый target, точные CLI/provider release digests и
сохраняет typed outcomes. Direct provider invocation может диагностировать
producer, но не заменяет consumer path.

## Platform matrix

Matrix содержит Linux, Windows и macOS на `x86_64` и `arm64`. На каждой строке
отдельно записываются:

- provider binary availability;
- availability конкретной operation;
- network launcher evidence/refusal;
- фактически выполненные lifecycle stages.

Software lifecycle у всех семи систем проверяется на шести строках. Cursor и
Antigravity не объявляют complete launch; launch проверяется у остальных пяти.

Evidence предыдущего tag не переносится. Текущий снимок незакрытых строк живёт
в `implementation-roadmap.md`, а не в этом runbook.

## Postures и corpus

Provider sources публикуют четыре postures каждого харнесса: `minimal`,
`baseline`, `full-auto`, `nddev-builder`. Corpus/evidence выбирает posture явно;
одинаковые bytes разных posture не сливаются в одну identity, а изменение
HEAD репозитория provider вне payload не меняет неизменяемый passport.

`just corpus-drift` и `just evidence-citations` читают внешнее состояние и
поэтому не входят в repository gate. Их `inconclusive` не выдаётся за clean.

## Credentials

GitHub attestation read использует текущий authenticated `gh` account или
job-scoped token. Значение token не пишется в команды evidence, logs или
artifacts. Отсутствие auth — недоступная зависимость, а не вердикт о байтах.
