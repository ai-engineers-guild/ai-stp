# Account, grants and sync

Начните с `ai-stp account status`; изменения выполняются через `ai-stp account plan` и точный apply. Повторно используйте pending-код и соблюдайте next_poll_at, не запускайте новый вход в цикле. Если вход выполнен, не заменяйте сессию без причины. Секреты не попадают в чат и планы. Grants/visibility учитывают полномочия пользователя; sync включается явно и использует планы push/pull/merge/recover.
