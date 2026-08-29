---
description: "Как прогнать полный жизненный цикл против выпущенных провайдеров и что при этом проверяется."
last_verified: "2026-08-29"
---

# Доказательство против выпущенных провайдеров

Владелец требований — `#408`. `just evidence-providers <tag>` проверяет
метаданные релиза и согласие проекций, и сам называет то, чего проверить не
может:

```json
"not_verified": {
  "install_update_backup_remove_rollback": "the cross-repository tests in
   tests/unit/test_cli_install_commands.py; they need AI_STP_<HARNESS>_PROVIDER_V3
   and _MANIFEST pointed at a fetched artifact and its release.json"
}
```

Это та половина, которую закрывает прогон ниже.

## Как прогнать

```bash
for h in claude-code codex grok-build opencode pi; do
  uv run ai-stp provider fetch --harness "$h" --json >/dev/null
done

export GH_TOKEN="$(gh auth token)"
for pair in CLAUDE:claude-code CODEX:codex GROK_BUILD:grok-build \
            OPENCODE:opencode PI:pi; do
  v=${pair%%:*}; h=${pair##*:}; d=~/.local/share/ai-stp/providers/$h/<tag>
  export AI_STP_${v}_PROVIDER_V3="$(find "$d" -maxdepth 1 -type f -perm -u+x | head -1)"
  export AI_STP_${v}_PROVIDER_V3_MANIFEST="$d/release.json"
done
export AI_STP_PROVIDER_V3_READONLY="$AI_STP_CLAUDE_PROVIDER_V3"

uv run pytest tests/unit/test_cli_install_commands.py -k "real_ or backups_reaches"
```

`GH_TOKEN` обязателен, и причина не косметическая: тесты подменяют `HOME`, а
`gh` держит учётные данные там. Без токена проверка аттестации отказывает —
раньше она отказывала словами «у артефакта нет приемлемой аттестации», то есть
обвиняла байты за то, что на машине нет входа. Теперь неаутентифицированный
`gh` (код выхода 4) отличается от настоящего вердикта (код 1) и сообщается как
недоступная зависимость.

## Что проверено против `0.0.33`

```text
базовый сетап, полный цикл бандла     claude-code codex grok-build opencode pi
полный цикл v3 одним точным бандлом   claude-code codex grok-build opencode pi
чтение резервных копий у провайдера   claude-code
```

Одиннадцать прогонов, все зелёные. Каждый берёт выпущенный подписанный артефакт,
проверяет аттестацию GitHub против закреплённой политики, собирает бандл,
планирует, применяет, читает состояние и откатывается.

## Чего в корпусе нет

`test_real_role_setup_install_status_remove_and_rollback` спрашивает роли
`backend`, `frontend`, `full-stack`, `code-review`, `security`, `research`.
Корпус первого лица несёт по одному сетапу на харнесс — `ai-harness-engineer`.

Это не регрессия, а несобранное содержимое: корпус пересобран из семи живых
setup-систем, и каждая публикует один сетап. Тест теперь называет и роль,
которую искал, и те, что есть, вместо пустого `StopIteration`.

## Что этим не доказывается

Чистая установка с сайта — отдельный срез, здесь его нет. И роли из списка выше
не проверены, потому что их не существует; см. предыдущий раздел.
