---
title: "CLI"
description: "Как человек и агент работают с ai_stp CLI: JSON-конверт, mutability и группы команд."
---

# CLI

Посмотрите доступные intent’ы; для прямых операций используйте справку нужной группы.

```bash
ai-stp help --path task --json
```

Перед изменением проверьте параметры в справке. План фиксирует точные входные данные и digest; для восстановления повторяйте принятую операцию с исходным планом.

[Справка Rust CLI и поддержка платформ](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli-v2/README.md).
