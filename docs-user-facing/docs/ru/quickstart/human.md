---
title: "Быстрый старт для человека"
description: "Установить ai_stp CLI, проверить окружение и дойти до первого чтения каталога."
---

# Быстрый старт для человека

Скачайте нативный архив вашей ОС из [последнего релиза](https://github.com/ai-engineers-guild/ai-stp/releases/latest).
Проверьте контрольную сумму и аттестацию GitHub, затем выполните шаги установки из релиза.
Python не нужен. Провайдеры выполняются на Linux; macOS и Windows поддерживают
остальные нативные операции, указанные в capabilities.

Удалите прежний Python launcher через его пакетный менеджер перед добавлением
нового исполняемого файла в PATH. Существующее состояние переносится явно;
не создавайте поверх него другого владельца.

```bash
ai-stp version --json
ai-stp capabilities --json
ai-stp doctor --json
```

Для нового каталога состояния:

```bash
ai-stp init --credential-store os_keyring --json
ai-stp task intents --json
```

[Работа агента](agent.md). [Перенос состояния и установка](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli-v2/README.md).
