---
title: "CLI"
description: "Discover native commands, configuration and state."
---

# Rust CLI

```sh
ai-stp help --agent --json
ai-stp help --path "configuration native" --json
ai-stp capabilities --json
```

The installed executable describes command arguments and platform support.
Machine output is one JSON envelope. Read the operation status and receipt
before retrying a write.

`--config` selects a YAML file with `catalog.enabled`, `catalog.url` and
`sync.enabled`. State uses `--state-dir`, then `AI_STP_STATE_DIR`, then the
XDG data directory. Credentials use the selected credential store.

[Installation, migration and native setup](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli/README.md).
