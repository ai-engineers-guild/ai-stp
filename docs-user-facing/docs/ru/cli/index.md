---
title: "CLI"
description: "Команды, конфигурация и локальное состояние нативного CLI."
---

# Rust CLI

```sh
ai-stp help --agent --json
ai-stp help --path "configuration native" --json
ai-stp capabilities --json
```

Установленный CLI описывает аргументы команд и доступные возможности. Машинный
вывод содержит один JSON-конверт. Перед повтором записи прочитайте статус и
квитанцию исходной операции.

`--config` выбирает YAML с `catalog.enabled`, `catalog.url` и `sync.enabled`.
Каталог состояния задаётся через `--state-dir`, затем `AI_STP_STATE_DIR`,
затем XDG. Учётные данные находятся в выбранном хранилище.

[Установка, перенос состояния и настройка харнесса](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli/README.md).
