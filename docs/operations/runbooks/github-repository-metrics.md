---
description: "Runbook: best-effort кэш GitHub stars для публичного каталога."
last_verified: "2026-08-12"
---

# GitHub repository metrics

Worker обновляет `github_stars` из канонического публичного provenance repository
после публикации. Успешное значение считается свежим 12 часов; ошибки сохраняют
предыдущее значение и используют ограниченный backoff до 24 часов. Недоступный
или private repository не отображается как ноль, а метрика не влияет на trust.

Для повышенного rate limit задаётся необязательный
`AI_STP_WORKER_GITHUB_TOKEN`. Fine-grained token должен иметь только публичный
доступ к metadata; права записи и доступ к private repositories не требуются.
Значение токена не пишется в БД, логи, ответы API или fixtures.
