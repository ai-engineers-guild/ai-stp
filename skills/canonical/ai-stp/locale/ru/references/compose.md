# Compose

Намерения: выбрать сетап, проверить eligibility, подтвердить proposal.

Берите из machine help: `ai-stp select eligibility`,
`ai-stp select eligibility-matrix`, `ai-stp select impact`,
`ai-stp select propose`, `ai-stp select confirm`, `ai-stp select cancel`,
`ai-stp select graph`, `ai-stp select reports`, `ai-stp setup compose plan`,
`ai-stp setup compose apply`, `ai-stp setup recast plan`,
`ai-stp setup recast apply`.

Читайте eligibility и отчёты до propose. Подтверждайте только только что
возвращённый proposal, не старую строку из списка. Члены `experimental` или с
непроверенным автором входят по полномочию задачи и остаются помеченными;
они не становятся `authoritative`. Проверяйте `ai-stp select graph`
после confirm.

Полный сетап на другой харнесс — `setup recast plan` и `setup recast apply` из
machine help. Apply только полного плана. Заблокированный член — не сетап.
