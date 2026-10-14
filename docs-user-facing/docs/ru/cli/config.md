---
title: "Конфигурация"
description: "Создать, показать, проверить и изменить закрытый файл конфигурации CLI, который соблюдает эта установка."
---

# Конфигурация

Поля сетевых настроек: catalog.enabled, catalog.url и sync.enabled. Каталог состояния задаётся через --state-dir или AI_STP_STATE_DIR.

```bash
ai-stp help --path config --json
```

Перед изменением проверьте параметры в справке. План фиксирует точные входные данные и digest; для восстановления повторяйте принятую операцию с исходным планом.

[Справка Rust CLI и поддержка платформ](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli-v2/README.md).
