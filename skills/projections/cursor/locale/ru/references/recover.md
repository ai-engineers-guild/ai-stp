# Recover

Намерения: timeout, частичная установка, зависшая операция.

Первая команда: `ai-stp task intents --json`. Не выгружайте machine help.
Не набирайте `ai-stp help` или `help --json`. Не набирайте `ai-stp capabilities`.
Не изобретайте `task get` или `task status`.

Если задача install ещё `planned`, `blocked` или `running`, продолжайте её.
Не стартуйте второй intent `install`. Не выгружайте весь registry.

Expert recovery после уже failed задачи: `ai-stp install recover` или
`ai-stp install resume`, если CLI их назвал. Сначала установите фактический
эффект. Не повторяйте `ai-stp install apply` «для синхронизации». Используйте
recovery или resume, которые ещё предлагает envelope.

Не набирайте `setup preserve recover`. Возврат сохранённого native setup —
intent `switch`. `ai-stp install recover` или `ai-stp install resume` остаются
expert recovery после already failed install, если CLI их назвал.

Удержанный child `operation_…` на открытой задаче install возобновляется
через continue, а не вторым start.
