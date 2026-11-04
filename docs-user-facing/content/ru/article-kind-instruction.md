---
type: article
slug: kind-instruction
locale: ru
title: "instruction"
description: "Постоянные правила для агента в выбранной области."
published_at: 2026-09-04
tags: [component, instruction]
draft: false
---

# instruction

![Component type: instruction](/content/illustrations/kind-instruction.jpg)

Используйте инструкцию для постоянных правил. Например, Codex обнаруживает `AGENTS.md`. Повторяемую процедуру вынесите в skill, а правила привяжите к нужному проекту или пользователю.

Перед авторингом прочитайте схему входных данных:

```sh
ai-stp task input-schema --intent author --json
```

Опубликованная версия компонента неизменяема. Перед добавлением в сетап
проверьте точную версию и результаты проверок.

[Справка CLI](https://docs.nddev.asia/cli/) ·
[Проверки безопасности](https://docs.nddev.asia/security-checks/)
