---
type: article
slug: kind-skill
locale: en
title: "skill"
description: "A reusable workflow with a SKILL.md entry point."
published_at: 2026-09-04
tags: [component, skill]
draft: false
---

# skill

![Component type: skill](/content/illustrations/kind-skill.jpg)

Put the workflow in `SKILL.md`. Keep referenced scripts and assets in the same component so the exact version includes everything the procedure needs.

Inspect the accepted authoring inputs before starting:

```sh
ai-stp task input-schema --intent author --json
```

A published component version is immutable. Review the exact version and
its evidence before adding it to a setup.

[CLI reference](https://docs.nddev.asia/en/cli/) ·
[Security checks](https://docs.nddev.asia/en/security-checks/)
