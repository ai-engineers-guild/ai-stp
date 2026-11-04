---
type: article
slug: kind-agent
locale: en
title: "agent"
description: "A harness role with its own instructions and tool access."
published_at: 2026-09-04
tags: [component, agent]
draft: false
---

# agent

![Component type: agent](/content/illustrations/kind-agent.jpg)

Use an agent component for a role the harness can delegate to. Review the role's instructions and the tools it can invoke in the intended scope.

Inspect the accepted authoring inputs before starting:

```sh
ai-stp task input-schema --intent author --json
```

A published component version is immutable. Review the exact version and
its evidence before adding it to a setup.

[CLI reference](https://docs.nddev.asia/en/cli/) ·
[Security checks](https://docs.nddev.asia/en/security-checks/)
