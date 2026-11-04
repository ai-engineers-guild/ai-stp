---
type: article
slug: kind-mcp
locale: ru
title: "mcp"
description: "Пакет MCP-сервера или клиентская конфигурация харнесса."
published_at: 2026-09-04
tags: [component, mcp]
draft: false
---

# mcp

![Component type: mcp](/content/illustrations/kind-mcp.jpg)

Обнаружение различает пакет `mcp_server` и запись `mcp_client_config`. Проверьте сервер или адрес, транспорт и запрошенный доступ. Храните учётные данные в выбранном хранилище, а в паспорте указывайте только имена переменных.

Перед авторингом прочитайте схему входных данных:

```sh
ai-stp task input-schema --intent author --json
```

Опубликованная версия компонента неизменяема. Перед добавлением в сетап
проверьте точную версию и результаты проверок.

[Справка CLI](https://docs.nddev.asia/cli/) ·
[Проверки безопасности](https://docs.nddev.asia/security-checks/)
