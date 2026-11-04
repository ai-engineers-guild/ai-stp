---
type: article
slug: kind-mcp
locale: en
title: "mcp"
description: "An MCP server package or harness client configuration."
published_at: 2026-09-04
tags: [component, mcp]
draft: false
---

# mcp

![Component type: mcp](/content/illustrations/kind-mcp.jpg)

Discovery distinguishes `mcp_server` packages from `mcp_client_config` entries. Review the server or endpoint, its transport and the requested access. Keep credentials in the chosen store and record only required environment variable names.

Inspect the accepted authoring inputs before starting:

```sh
ai-stp task input-schema --intent author --json
```

A published component version is immutable. Review the exact version and
its evidence before adding it to a setup.

[CLI reference](https://docs.nddev.asia/en/cli/) ·
[Security checks](https://docs.nddev.asia/en/security-checks/)
