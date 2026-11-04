---
title: "Быстрый старт для человека"
description: "Установка проверенного нативного клиента и подготовка состояния."
---

# Быстрый старт для человека

Выберите архив для своей ОС, проверьте контрольную сумму и аттестацию и
установите его по [руководству CLI](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli/README.md#install-and-update).
CLI уже входит в [установщик Desktop](https://github.com/ai-engineers-guild/ai-stp/releases/tag/desktop-v0.4.0).

Для нового локального состояния:

```sh
ai-stp version --json
ai-stp init --credential-store os_keyring --json
ai-stp capabilities --json
```

Состояние Python CLI перенесите по [процедуре миграции](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli/README.md#state-and-first-run).
Для проверки или установки сетапа откройте [инструкцию для агента](agent.md).
