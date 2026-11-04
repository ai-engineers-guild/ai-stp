---
title: "Quickstart for people"
description: "Install a verified native client and prepare local state."
---

# Quickstart for people

Choose the archive for your OS, verify its checksum and attestation, and install
it using the [CLI installation guide](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli/README.md#install-and-update).
The [Desktop installer](https://github.com/ai-engineers-guild/ai-stp/releases/tag/desktop-v0.4.0)
bundles the CLI.

For new local state:

```sh
ai-stp version --json
ai-stp init --credential-store os_keyring --json
ai-stp capabilities --json
```

Use [state migration](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli/README.md#state-and-first-run) for a Python registry.
Continue with the [agent workflow](agent.md) to review or install a setup.
