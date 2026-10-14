---
title: "Quickstart"
description: "Choose the human first-run path or the AI-agent session path."
---

# Quickstart

Download the native archive for your OS from the [latest release](https://github.com/ai-engineers-guild/ai-stp/releases/tag/cli-v0.1.0).
Verify its checksum and GitHub attestation, then follow the release installation steps.
No Python runtime is required. Linux supports provider execution; macOS and Windows
support the other native operations advertised by their capabilities.

Retire an existing Python launcher through its owning package manager before
adding the native executable to PATH. Existing state requires explicit migration;
never initialize another owner over it.

```bash
ai-stp version --json
ai-stp capabilities --json
ai-stp doctor --json
```

For a new state directory:

```bash
ai-stp init --credential-store os_keyring --json
ai-stp task intents --json
```

[Agent workflow](agent.md). [Migration and installation reference](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli-v2/README.md).
