# Account

Намерения: вход, выход, grants, sync, жалоба, открыть сайт.

Берите из machine help: `ai-stp auth login`, `ai-stp auth status`,
`ai-stp auth logout`, `ai-stp grant list`, `ai-stp owner objects`,
`ai-stp sync preview`, `ai-stp report preview`, `ai-stp link web`.

Никогда не передавайте пароль, токен или секрет в argv, окружении или логах.
В browser device flow покажите verification URL и user code; не завершайте
grant за пользователя.

Проверяйте `ai-stp auth status`.
