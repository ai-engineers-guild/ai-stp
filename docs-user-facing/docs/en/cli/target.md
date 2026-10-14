---
title: "Target"
description: "Daily status, diff, backups, and the named previous version. Restores nothing."
---

# Target

Targets are explicit scope roots in a configuration plan. Active-agent changes require a staged handoff and restart. There is no generic backup or rollback command.

```bash
ai-stp help --path configuration --json
```

Inspect the returned parameters before a mutation. Plans bind exact inputs and digests; repeat an admitted operation with its original plan for recovery.

[Native CLI reference and platform support](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli-v2/README.md).
