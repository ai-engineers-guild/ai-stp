---
title: "ai_stp"
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

Веб владеет аккаунтом и публичным каталогом. Он показывает результаты. Он не
выбирает состав, не собирает сетап и не пишет нативное состояние харнесса.
Эту работу выполняют [CLI](cli/index.md), агент и публичный provider
конкретного харнесса.

## С чего начать

- [Быстрый старт](quickstart.md): установить CLI, проверить окружение и увидеть
  первые команды.
- [CLI](cli/index.md): рабочая поверхность — JSON-конверты, планы и
  подтверждение.
- [Веб](web/index.md): аккаунт, карточки каталога, публикации и жалобы.
- [Харнессы](harnesses.md): основная поддержка, beta-линии и `undefined`.
- [Понятия](concepts/index.md): харнесс, сетап, provider, сборщик, устройство,
  проект и три режима.
- [Компоненты](components/index.md): восемь видов и чем они отличаются.
- [Каталог](catalog/index.md): как читать публичный результат и как CLI его
  ищет.
- [Доверие и безопасность](trust-and-safety/index.md): почему verified-автор
  не равен безопасному содержимому.
- [Диагностика](troubleshooting/index.md): восстановиться, если установка или
  проверка не прошла.

## Что поддерживает MVP

Основная поддержка — **Claude Code**, **Codex** и **Grok Build**.

Beta-линии — **Pi**, **OpenCode**, **Cursor** и **Antigravity**. Каталог и
совместимость работают; provider-путь может требовать дополнительного
подтверждения.

Неизвестный харнесс попадает в ограниченный режим **`undefined`**. Чтение,
импорт и локальные проверки допустимы. Автоматическая установка не считается
безопасной.

Основной путь выглядит так:

```text
CLI → паспорта → индекс проекта → поиск → сборка сетапа → проверки
→ план установки → резервная копия → применение через provider → status
```

??? question "Как читать эту документацию"
    Если вы впервые видите `ai_stp`, начните с быстрого старта и страницы про
    харнессы. Если вы уже собираете сетап, переходите сразу к
    [компонентам](components/index.md): каждая страница объясняет назначение,
    границы и риск конкретного вида. Флаги команд всегда берутся из
    `ai-stp help --agent --json`; этот сайт называет команды, чтобы человек
    нашёл нужную страницу.
