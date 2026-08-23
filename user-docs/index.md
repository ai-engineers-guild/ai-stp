---
description: "Пользовательская документация ai_stp."
---

<!--
THESIS: public docs explain ai_stp from the user's daily path, while internal docs keep architecture and requirements out of the help center.
OWN-WORLD: restrained MkDocs Material reading surface, Russian prose, narrow pages, explicit navigation, code examples only where they help action.
STORY: a developer and their agent understand what ai_stp does, install the CLI, read catalog evidence, assemble a setup, and recover safely.
FIRST VIEWPORT: search, left navigation, concise product definition, and direct links to quickstart and trust guidance before deeper reference.
FORM: MVP documentation site, category-standard static docs chosen deliberately for reliability; FINISH: unreviewed and undocumented is unfinished.
-->

# ai_stp

`ai_stp` помогает разработчику и его coding agent подобрать, проверить и
безопасно установить полный сетап для AI-харнесса.

Сетап включает инструкции, навыки, MCP, хуки, команды, агентов, плагины и
настройки. `ai_stp` хранит происхождение, совместимость, точные версии и
решения доверия так, чтобы агент не угадывал конфигурацию вслепую.

## С чего начать

- [Быстрый старт](quickstart.md): установить CLI, проверить окружение и увидеть
  первые команды.
- [Харнессы](harnesses.md): понять, что поддерживается в MVP, что находится в
  beta и что означает режим `undefined`.
- [Понятия](concepts/index.md): понять харнесс, сетап, компонент, паспорт и
  линию доверия.
- [Компоненты](components/index.md): разобраться, чем отличаются `skill`,
  `mcp`, `hook`, `command`, `agent`, `plugin`, `instruction` и `setting`.
- [Доверие и безопасность](trust-and-safety/index.md): разобраться, почему
  verified-автор не равен безопасному содержимому.
- [Диагностика](troubleshooting/index.md): восстановиться, если установка или
  проверка не прошла.

## Что умеет MVP

MVP поддерживает Claude Code, Codex и Grok Build как основные харнессы. Pi и
OpenCode доступны как beta-линии, а неизвестный харнесс попадает в
ограниченный режим `undefined`.

Основной путь выглядит так:

```text
CLI → паспорта → индекс проекта → поиск → сборка сетапа → проверки
→ план установки → резервная копия → применение через provider → status
```

Веб показывает публичный каталог и аккаунт. Сборку, проверки и установку
выполняют CLI, agent и provider конкретного харнесса.

??? question "Как читать эту документацию"
    Если вы впервые видите `ai_stp`, начните с быстрого старта и страницы про
    харнессы. Если вы уже собираете сетап, переходите сразу к компонентам:
    каждая страница объясняет назначение, границы и риск конкретного вида.
