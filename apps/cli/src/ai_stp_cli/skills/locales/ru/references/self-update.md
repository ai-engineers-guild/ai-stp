# Self-update this CLI

Намерения: обновить сам ai-stp, wheel на PyPI, self-update CLI, обновить
установленную команду `ai-stp`.

Берите из machine help: `ai-stp update check`, `ai-stp update plan`,
`ai-stp update apply`, `ai-stp update status`, `ai-stp update recover`,
`ai-stp update rollback`.

Это семейство заменяет wheel `ai-stp-cli` через installer, которому принадлежит
установка. Оно не обновляет провайдеры, программы харнесса и сетапы.

Не запускайте `uv tool upgrade`, когда есть `update plan`: pin в uv receipt
не сдвинется, а движущийся latest — не запланированный артефакт. Применяйте
сохранённый digest плана. После apply новый процесс должен сообщить целевую
версию.

Уведомление TTY — не согласие. `update apply` требует digest плана. JSON и
каналы оставляют один конверт; они не спрашивают.

Если журнал `recovery_required`, запустите `ai-stp update recover` или читайте
`ai-stp update status`. Не повторяйте `update apply` «для синхронизации».
