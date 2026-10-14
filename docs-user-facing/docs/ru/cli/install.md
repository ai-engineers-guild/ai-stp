---
title: "Установка"
description: "Запустить intent install. Expert plan, approve, apply, recover и resume остаются для recovery."
---

# Установка

Установка требует точных setup/provider/source и корней областей. Все корни подготавливаются до записи. Прерванные операции продолжаются по сохранённым данным. Выполнение провайдеров доступно только на Linux.

```bash
ai-stp help --path configuration --json
```

Перед изменением проверьте параметры в справке. План фиксирует точные входные данные и digest; для восстановления повторяйте принятую операцию с исходным планом.

[Справка Rust CLI и поддержка платформ](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli-v2/README.md).
