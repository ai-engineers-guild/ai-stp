---
type: article
slug: kind-command
locale: en
title: "command"
description: "A named prompt or shortcut exposed by a harness."
published_at: 2026-09-04
tags: [component, command]
draft: false
---

# command

![Component type: command](/content/illustrations/kind-command.jpg)

Use a command for an action the user invokes by name. Review its arguments and target scope. These shortcuts are defined by the harness, while ai-stp commands are listed by CLI help.

Inspect the accepted authoring inputs before starting:

```sh
ai-stp task input-schema --intent author --json
```

A published component version is immutable. Review the exact version and
its evidence before adding it to a setup.

[CLI reference](https://docs.nddev.asia/en/cli/) ·
[Security checks](https://docs.nddev.asia/en/security-checks/)
