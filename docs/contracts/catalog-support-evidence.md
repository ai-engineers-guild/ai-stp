---
description: "Безопасная публичная проекция evidence поддержки харнесса в каталоге."
last_verified: "2026-08-09"
---

# Evidence поддержки каталога

Точные поля и enum принадлежат моделям `packages/contracts` и сгенерированным
схемам. Этот документ фиксирует смысл публичной проекции по `SPEC-033` и
`ADR-0072`.

`support.tier` показывает продуктовый уровень поддержки харнесса: `primary` или
`beta`. `support.state` показывает состояние обязательных доказательств:
`verified`, `stale`, `missing` или `not_verified`. Эти оси не являются
`trust_lane`, `author_verified` или `component_verified`.

Публичная запись evidence содержит только безопасное резюме проверки: `check_id`,
результат, источник, идентификаторы provider и version, точную release reference
(commit или digest),
операционную систему, архитектуру, обязательность проверки и timestamps. Сырые
отчёты, подпись, storage key, credentials, приватный URL и байты объекта не
публикуются. `policy_version` сохраняет версию применённой support policy.

Сервер вычисляет state по сохранённым timestamps и своему текущему времени.
Web не пересчитывает freshness. Полный свежий набор обязательных `passed` даёт
`verified`; истёкший набор даёт `stale`; отсутствие обязательной записи даёт
`missing`; неуспешный, повреждённый или противоречивый evidence даёт
`not_verified` и не меняет trust axes.

Строки без evidence сохраняются как `missing`, поэтому добавление проекции
аддитивно и не переписывает исторические публикации. Фильтры
`support_tier`/`support_state` принимаются на публичных catalog routes и не
изменяют согласие на `experimental` lane.
