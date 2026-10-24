# Recover

Намерения: timeout, частичная установка, зависшая операция.

Если задача install ещё `planned`, `blocked` или `running`, продолжайте её.
Не стартуйте второй intent `install`. Не выгружайте весь registry.

Expert recovery после уже failed задачи: берите из machine help
`ai-stp install status`, `ai-stp install recover`, `ai-stp install resume`.
Сначала установите фактический эффект. Не повторяйте `ai-stp install apply`
«для синхронизации». Используйте recovery или resume, которые назвал CLI.
Проверяйте `ai-stp target status` и `ai-stp install status`.

`ai-stp setup preserve recover` восстанавливает ID сохранённого сетапа по
исходному плану и свежим данным провайдера после потери ответа. Это не повтор
установки и не превращение partial в verified. Новый план возврата выбирает
этот ID. Для окружения используйте восстановление общей операции: оно
сохраняет обратный порядок компенсации между харнессами.

Удержанный child `operation_…` на открытой задаче install возобновляется
через continue, а не вторым start.
