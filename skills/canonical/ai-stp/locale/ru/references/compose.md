# Compose

Намерения: выбрать сетап, проверить eligibility, подтвердить proposal.

Берите из machine help: `ai-stp select eligibility`,
`ai-stp select eligibility-matrix`, `ai-stp select impact`,
`ai-stp select propose`, `ai-stp select confirm`, `ai-stp select cancel`,
`ai-stp select graph`, `ai-stp select reports`, `ai-stp setup compose plan`,
`ai-stp setup compose apply`, `ai-stp setup recast plan`,
`ai-stp setup recast apply`, `ai-stp component materialize plan`,
`ai-stp component materialize apply`, `ai-stp component portability plan`,
`ai-stp component portability apply`.

Читайте eligibility и отчёты до propose. Подтверждайте только только что
возвращённый proposal, не старую строку из списка. Члены `experimental` или с
непроверенным автором входят по полномочию задачи и остаются помеченными;
они не становятся `authoritative`. Проверяйте `ai-stp select graph`
после confirm.

Полный сетап на другой харнесс — `setup recast plan` и `setup recast apply` из
machine help. Apply только полного плана. Заблокированный член — не сетап.
MCP-файлы и host-file contributions выводятся; settings, не-MCP contributions
и MCP plugin packages остаются заблокированными.

Одна недостающая адаптация pinned-компонента — `component materialize plan` и
`apply`. Явный claimed-portable путь без опубликованной адаптации —
`component portability plan` / `apply`: частный overlay, исходная публичная
версия не меняется.
