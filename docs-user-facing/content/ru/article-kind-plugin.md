---
type: article
slug: kind-plugin
locale: ru
title: "plugin"
description: "Пакет расширения харнесса с нативным манифестом."
published_at: 2026-09-04
tags: [component, plugin]
draft: false
---

# plugin

![Component type: plugin](/content/illustrations/kind-plugin.jpg)

Храните нативный манифест вместе с ресурсами, на которые он ссылается. Перед применением плана проверьте хуки, подключения и исполняемые точки входа.

Перед авторингом прочитайте схему входных данных:

```sh
ai-stp task input-schema --intent author --json
```

Опубликованная версия компонента неизменяема. Перед добавлением в сетап
проверьте точную версию и результаты проверок.

[Справка CLI](https://docs.nddev.asia/cli/) ·
[Проверки безопасности](https://docs.nddev.asia/security-checks/)
